# CPU 超分的 PL 快照所有权

本次修复针对实时 FSR 的输入帧一致性。上一版本直接两次读取 PS 颜色槽，存在渲染器复用该槽的窗口；原始故障证据保留在 `report/postproc_game_ps_snapshot_mismatch/`。新版本将 CPU 输入改为独立的 PL DDR 快照，已完成 SD 更新、正常重启与实际游戏验证。本地检查 20/20、板端检查 23/23 通过，见 `report/postproc_touch_local_acceptance.json`、`report/frame_snapshot_board_acceptance.json`。

当前板上为 Neverball、FPGA 双线性、原色。CPU FSR 按命令启用；实测 60.006 秒处理 130 帧，2.16645 fps，快照重试和硬件错误均为零。它仍是 A53 CPU 实验，尚不满足流畅游戏所需帧率。

## 数据通路

```text
PS RGB565 帧 → 原帧桥（同一次读取与 RGB 扩展）
                ├─ PL 原始显示槽 → FPGA 双线性/最近邻
                └─ 有快照请求时：PL 0x21400000 独立快照
                                  ↓ 完成最后一次 AXI B
                                READY + token + frame_id
                                  ↓ A53 复制到普通内存并释放
                                CPU FSR1 → 双缓冲 HR → PL 风格 → LCD
```

快照是原帧桥实际提交到 PL 的像素，CPU 不再重新读取可能已被复用的 PS 颜色槽。快照区为 400×240 XRGB8888，共 384,000 字节，PS 访问地址 `0xA1400000`。它与两个 HR 槽 `0xA1000000`、`0xA1200000` 不重叠。

CPU 取到快照后转换回等价 RGB565，释放所有权，再执行 EASU/RCAS。持有快照不会等待 FSR 计算完成，也不会阻止后续游戏帧提交；只在申请快照的那一帧增加一份 PL 写入。

实际 A53 Device 内存测量中，384,000 字节的 64 位逐次读取约 0.212 秒，128 位读取约 0.111 秒，成对 128 位 `LDP` 约 0.059 秒，四寄存器 `LD1` 反而约 0.220 秒；四种方式的完整数据均一致。最终采用 32 字节对齐的成对 128 位读取，栈暂存区按 ABI 要求对齐到 16 字节。源地址、长度和步长保证读取不跨 4 KiB 页边界。CPU 图像计算保持原来的官方 FP32 内核。

完整实测由未优化的 99 帧/60.316 秒、1.64135 fps，提高至 130 帧/60.006 秒、2.16645 fps。平均取帧复制耗时由 0.20111 秒降到 0.05652 秒。两个时间窗都运行 Neverball；算子累计计算时间分别为 33.3307 秒和 43.4073 秒，不能把 LCD 刷新率或 GPU 呈现计数当作 FSR 帧率。证据为 `report/postproc_snapshot_performance_serial64.bin`、`report/postproc_snapshot_performance.bin`、`report/board_serial/com11_snapshot_read_bench_final.log`。

## 握手与恢复

状态依次为 IDLE=0、PENDING=1、COPYING=2、READY=3。请求必须使用非零且不同于上次的 token；忙时拒绝新请求。释放必须匹配当前 token，避免旧进程释放新租约。

只有最后一笔快照 AXI 写响应成功后才能发布 READY。READY 期间禁止再次写快照。每个非空闲状态有 2 秒硬件看门狗；进程被强制终止后，租约会自动回收。复制期间取消或超时必须完成已开始的 AXI 事务，不能撤回 VALID 或提前接受另一个写入者。AXI 错误使帧桥进入原有故障恢复路径，不发布有效快照。

CPU 在读完后再次核对 READY 和 token，若读取期间过期则丢弃输入。正常退出和 SIGTERM 会主动释放；SIGKILL 由硬件超时回收。设备树增加 `rasterix-frame-snapshot` 能力节点；缺少此节点时，新程序拒绝实时取帧，避免访问旧硬件中不存在的寄存器。

| GPU 控制偏移 | 用途 |
|---|---|
| `0x74` | 只读能力签名 SNP1=`0x534e5031` |
| `0x78` | 写入请求 token；读当前 token |
| `0x7c` | 状态 bits 1:0；bit 8 表示已取消、等待排空 |
| `0x80` | 写入匹配 token 释放；读当前 token |
| `0x84` | 快照对应的原始 GPU 帧编号 |
| `0x88` | CPU 映射地址 `0xA1400000` |
| `0x8c` | 租约超时计数 |
| `0x90` | 快照字节数 384000 |
| `0x94` | 每阶段看门狗时长 2000 ms |

## 可复现检查

`sim/tb_snapshot_bridge.sv` 使用会随游戏帧变化的 PS 内存模型，验证独立快照与原始显示写入完全相同；持有一个快照时继续呈现 25 帧；覆盖 token 释放、重新申请、三种状态超时、复制中取消、独立 AW/W 停顿、延迟 B、写错误和复位。日志为 `report/tb_snapshot_bridge_postproc.log`。AXI-Lite 寄存器回归覆盖部分 WSTRB、忙请求和过期 token 拒绝。

正式部署版本的 12 项所有权板测全部通过：游戏在 CPU 持有数据时继续呈现新帧；700 ms 前后两次实际复制一致；正常结束及 SIGTERM 释放；SIGKILL 后仍保持数据直至硬件看门狗回收；没有新游戏帧时请求超时；恢复生产者后重新取得新帧。完整结果为 `report/postproc_snapshot_check.bin`。每轮测试包含两次预期租约超时，计入独立计数；两轮测试后累计为 4，GPU/显示超时计数始终为零。

新固件下最近邻、双线性、色阶、复古、黑白五组各 6,000 个 LCD 采样点与受保护的颜色测试图一致。第六组使用真实 Neverball 快照：输入 SHA256 为 `33eaf2050cbb47630fc6ddd808189d6201291ff0ba714eac0f37a60140f099f4`，A53 完整输出与主机参考均为 `e1977768734b1bdb0972166c668f51da4cc02f26d4fa169e5f5de04f5071f3b8`，FSR 加色阶后的实际 LCD 6,000 个采样点全部一致。见 `report/postproc_snapshot_lcd_pixel_acceptance.json`。

常规完整综合和布局布线通过，正式 WNS +1.235 ns、WHS +0.011 ns，所有用户时序与总线偏斜约束满足，CDC 无严重跨域问题。资源为 LUT 40518、FF 45038、BRAM 80、DSP 87；比上一版本增加 216 个 LUT、230 个寄存器，BRAM/DSP 不变。

SD 与板端安装摘要：

| 文件 | SHA256 |
|---|---|
| `BOOT.BIN` | `7a7adaa4f621eba8bb654f2b54524f91353e25392bb2fcb0e9ac04d3028e9f86` |
| `system.dtb` | `45e2e11f03be69c663190806a51829c068fbde953827598bc4005a5ed88c1419` |
| `rix-superres` | `ed7a643b0748fffaecdf5d0041a3ef19581dcbfa688b919df5b9978480376b1a` |
| 最终 `postproc-touch.tar.gz` | `3a53ee767b1dcbecd0a0e695605cae236310f4f742704a7f8894a31dc913a8ba` |

前一版本启动产物、验收结果及哈希清单保留在 `build/postproc-touch/pre-snapshot-lease/`；未经向量优化的 SNP1 程序包保留在 `build/postproc-touch/pre-vector-read/`。新的 FPGA 已正常重启验证；实体断电冷启动仍单列为未测。

板端完整 A53 输出、配对输入、性能与验收报告已同步保存到 SD 路径 `/opt/rasterix/experimental/results-20261019/frame-snapshot-snp1/`；验收报告 SHA256 为 `13f7a08b84cc43a6630df45a1c4357ff1447c5917d0dfa74f17e8f6d866518b5`。

板端示例：

```sh
P=/opt/rasterix/postproc-touch/bin
$P/rix-superres --status
# 在游戏持续运行时，保持快照 600 ms，前后两次实际读取必须一致。
$P/rix-superres --snapshot /tmp/postproc-tests/leased.rgb565 --snapshot-hold-ms 600
$P/rix-superres --live --mode fsr1 --seconds 60
# 保存严格配对的最后一组输入/输出，并保持该输出供 LCD 回读。
$P/rix-superres --live --mode fsr1 --seconds 2 --style 1 \
  --source-output /tmp/postproc-tests/leased-source.rgb565 \
  --output /tmp/postproc-tests/leased-output.xrgb --hold-last-seconds 120
```

性能统计只计处理循环，最后保持显示的等待不计入 FPS。FPGA 原始帧提交、LCD 刷新和 CPU 超分的新帧生成速度仍分别统计。触摸实体事件、四角方向和 Arm ASR 着色器后端的待验证状态与本次所有权修复无关，不能由快照测试代替。
