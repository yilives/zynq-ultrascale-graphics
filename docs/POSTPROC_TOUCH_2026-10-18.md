# 超分、风格化与触摸实验实现

2026-10-19 后续修复已完成：实时 FSR 改用独立 PL 快照及 ARM 对齐向量读取，完整握手、超时、性能和部署摘要见 [CPU 超分的 PL 快照所有权](FRAME_SNAPSHOT_2026-10-19.md)。新版本本地检查 20/20、板端检查 23/23 通过，实际 FSR 为 2.16645 fps。

本次工作以已通过游戏测试的 AXU3EG 启动包为基线。独立硬件工程位于 `build/vivado_postproc_touch`，新增产物位于 `build/postproc-touch`。原启动包及验收报告保存在 `build/postproc-touch/baseline/manifest.json` 所列路径。本文中的 CPU 验证已经完成，新增硬件和触摸的板测结果以同名验收 JSON 为准，不以源码存在作为通过依据。

当前验收见 `report/postproc_touch_local_acceptance.json`、`report/frame_snapshot_board_acceptance.json`，已包含严格快照所有权验证。实体触摸、四角方向和 Arm ASR 实际渲染仍未通过验证。板上已恢复 Neverball，使用 FPGA 双线性和原色；CPU FSR 通过命令开启。此前 19/19、15/15 版本的报告另存于 `build/postproc-touch/pre-snapshot-lease/`。

硬件本地实现已完成。包含快照握手版本的正式 WNS 为 +1.235 ns、WHS +0.011 ns，所有用户时序约束满足，CDC 没有 Unsafe/Unknown 端点，总线偏斜通过。资源为 LUT 40518/70560、FF 45038/141120、BRAM 80/216、DSP 87/360。证据为 `report/postproc_touch_*`，与旧 `board_*` 报告分开保存。

2026-10-19 已将包含快照握手的新包写入实际 SD 启动分区并回读校验、正常重启验证；原始文件保存为 `BOOT.BIN.pre-postproc-20261018`、`system.dtb.pre-postproc-20261018`。当前 BOOT.BIN、system.dtb 摘要分别为 `7a7adaa4f621eba8bb654f2b54524f91353e25392bb2fcb0e9ac04d3028e9f86`、`45e2e11f03be69c663190806a51829c068fbde953827598bc4005a5ed88c1419`。

## 实现范围

| 功能 | 实现方式 | 当前约束 |
|---|---|---|
| FSR1 EASU + RCAS | 官方 FP32 内核的 C++ CPU 适配，A53 四线程，400×240 → 800×480 | 独立快照加 ARM 向量读取下，60.006 秒处理 130 帧，2.16645 fps，快照重试及扫描/读写/超时错误均为零；属于 CPU 实验，尚非流畅游戏方案。隔离单帧滤波计算曾测得约 5.44 fps |
| Arm ASR | 官方 API 静态库交叉编译，实际 A53 执行 API / 抖动序列 / 缺失后端检查 | 尚无可执行的渲染后端；不提供伪装成 ASR 的降级滤波 |
| FPGA 放大 | 最近邻、中心对齐双线性 2×、原生 800×480 读帧 | 四个带行号的行缓存；帧消隐期间切换模式 |
| FPGA 风格 | 原画、8 档色阶、复古棕色、黑白阈值 | 逐像素颜色处理；尚无神经网络、物体轮廓或深度描边 |
| 触摸 | AXI GPIO → i2c-gpio → GT911 / Goodix → evdev → Xorg libinput | 已确认 0x5d / GT911，重启后自动注册与 Xorg 接入通过；实体接触事件和四角方向待用户可操作屏幕时验证 |
| LCD 回读 | 捕获实际后处理后 LCD 像素，100×60 RGB565 缩略图 | 用于核验放大、颜色风格与原生高分辨率读帧；不能用处理前的 PS 帧证明 PL 效果 |

## 两条显示路径

```text
游戏 / PS 顶点处理 → DMA → PL RasterIX → PS DDR RGB565 → 原帧桥
  ├─ PL DDR 400×240 → FPGA 最近邻 / 双线性 ─────────────┐
  └─ 独立 PL 快照 → A53 EASU + RCAS → PL DDR HR 原生读帧 ─┤
                                                   ↓
                                     PL 风格颜色 → 800×480 LCD
                                                   ↓
                                      冻结的 LCD 缩略图回读
```

游戏的 `presented` 计数保持原义，表示原始 GPU 帧提交。CPU FSR 另记录 `processed_frames`、墙钟耗时、滤波耗时和处理帧率。显示刷新率、GPU 提交速度和 FSR 新画面生成速度必须分别报告。

CPU 工具通过 SNP1 token 租约获取独立 PL 快照。原帧桥将同一次读取的像素写入原始显示槽及快照区，最后一次 AXI B 成功后才发布 READY；CPU 读完并确认租约未过期后释放，再从普通内存执行 FSR。该输入不再与游戏复用的 PS 槽共享写入。输出写入当前非显示的 HR 槽，完成 Device 内存写入与 `dsb sy` 后才请求帧切换，等待像素域确认后再使用另一槽。

## 控制与内存

原 GPU 控制地址、配置哈希和旧寄存器布局保留。新增能力签名 `PST1` 位于 `0xA0010050`。

| 偏移 | 用途 |
|---|---|
| `0x54` | 请求配置；bits 1:0 为最近邻 0 / 双线性 1 / HR 原生 2，bits 5:4 为风格 0–3，bit 8 保留底部 48 行原色，bit 9 选择 HR 槽 |
| `0x58` | 已在消隐期应用的配置，经过一致性 CDC 返回 |
| `0x5c` | 最近一次完整颜色帧复制的 PS 源地址 |
| `0x64/0x68` | LCD 捕获请求 / 完成 toggle；未完成时拒绝重复请求 |
| `0x6c/0x70` | 缩略图地址 0–5999 / RGB565 数据 |
| `0x74` | SNP1 独立快照签名；配套设备树节点也必须存在 |
| `0x78/0x7c/0x80` | 请求 token / 租约状态 / 按 token 释放；完整映射见快照修复文档 |

PS 地址 `0xA1000000`、`0xA1200000` 用于两个 HR 槽，对应 PL DDR `0x21000000`、`0x21200000`。此映射已经过下面的实际 LCD 回读核验。

新增独立快照位于 PS `0xA1400000`、PL `0x21400000`，384,000 字节 XRGB8888，与 HR 槽不重叠。每个非空闲阶段的硬件看门狗为 2 秒；复制期间取消会排空事务，旧 token 不能释放新租约。

最终实测已确认 HR 映射：A53 的完整 FSR 输出与主机参考 SHA256 一致，原生扫描后的 LCD 全部 6,000 个采样点与该输出经风格处理后的参考一致。持续测试期间 HR 槽切换正常，欠载和扫描错误为零。

## 触摸接线与启动

SCL 为 F10、SDA 为 G11、INT 为 B10，AXI GPIO 三个位依次为 SCL/SDA/INT。GPIO 地址 `0xA0020000`，PL 连接 GIC SPI 91。初始三线为输入；软件通过 GPIO 方向切换模拟开漏 I²C。没有已确认的复位引脚，使用面板已有配置，禁止编造 reset GPIO。

设备树首选 Goodix `0x5d`。若实际地址为 `0x14`，需先读控制器 ID，再修改设备树。Xorg 桌面为 400×240，LCD 为 800×480；正常的绝对坐标映射由输入驱动完成，不能直接把物理像素坐标当桌面坐标。

`rasterix-touch-start.sh` 仅在新触摸设备树节点存在时加载私有模块，放在 Xorg 启动前。Goodix 模块包含 Linux 5.4 同版本的触摸辅助函数，避免旧内核未启用 INPUT_TOUCHSCREEN 时缺少导出符号。模块已经在原板上实际加载成功。

实际 I²C 确认地址为 `0x5d`，ID `911`、固件 `0x1060`、800×480、5 点。Xilinx 2020.1 内核的 `xgpio_set_irq_type` 与中断分发仅支持上升沿，面板初始为下降沿。启动脚本先校验并备份完整 186 字节配置，再通过原配置下载协议只修改中断类型和校验和；回读确认仅偏移 6 和 184 改变，然后加载 Goodix。设备树相应使用上升沿；SDA/SCL GPIO 标志保留实测可用的 0，由 i2c-gpio 模拟开漏。这版旧 GPIO 驱动不接受标志 6，不能套用新版内核的描述。原配置的 SHA256 为 `e73602fb3c633f8d9d6847fd2d55027cb9fe1e09ab5fefd278ac1da9fa506ba4`，板上备份为 `/opt/rasterix/postproc-touch/gt911-factory-config.bin`，本地回读为 `report/postproc_gt911_factory.bin`。修改后已成功注册真实 evdev 设备，实体接触事件及四角方向需另行板测。

## 板端操作

安装后工具目录为 `/opt/rasterix/postproc-touch/bin`。以下硬件控制命令需要新硬件及其设备树已经启动：

FSR 和 PL 模式设置共用互斥锁。运行 FSR 时，另一个模式设置命令会明确拒绝操作；先正常结束 FSR，再切换模式或风格。状态读取和 LCD 捕获可同时进行。

安装包同时注册 `S08rasterix-postproc`：新硬件启动后默认使用 FPGA 双线性、原色风格。CPU FSR 通过命令显式开启，避免在游戏启动前持续占用 A53。恢复旧设备树后，这两个新增启动脚本会自动跳过。

```sh
P=/opt/rasterix/postproc-touch/bin
$P/rix-superres --status
$P/rix-superres --pl-mode bilinear --style 1   # 色阶
$P/rix-superres --pl-mode bilinear --style 2   # 复古
$P/rix-superres --pl-mode bilinear --style 3   # 黑白
$P/rix-superres --pl-mode nearest --style 0    # 还原

# 先启动游戏；FSR 运行期间占用 A53，结束后恢复之前的 PL 配置。
$P/rix-superres --live --mode fsr1 --style 1 --seconds 30
$P/rix-superres --capture /tmp/postproc-tests/lcd.rgb565
$P/rix-touch-monitor --seconds 30 --output /tmp/postproc-tests/touch.json
$P/rix-arm-asr-probe
```

## Arm ASR 的下一阶段接入条件

官方 API 已在 A53 上真实运行，400 → 800 得到 32 相位抖动序列；空后端创建返回 `FFXM_ERROR_INCOMPLETE_INTERFACE`。当前 RasterIX 为 ES 1.1 固定功能链路，不能执行官方 Vulkan/GLES 3.2 着色器。

要运行真正 ASR，需为游戏接入相机 jitter、当前与上一帧变换，并导出 32 位深度及逐像素运动向量；运动物体还需要对应的前帧对象变换，透明材质需正确处理。随后实现可执行官方各 pass 的后端或经过数值验证的 PL 多遍计算模块，并配置历史帧、临时纹理和带宽。单纯对颜色帧锐化或做前后帧混合无法完成这些要求。

## 验证证据

新增 RTL 仿真覆盖三种读帧模式、边界采样、输入空洞、行复用、色阶/复古/黑白与 HUD 边界、LCD 冻结捕获、AXI 全帧长度与 4 KiB 边界、取消排空和非法寄存器操作。原帧桥与控制接口回归另存日志。

首次 800×480 原生扫描板测暴露 16 拍 AXI 突发的吞吐不足，已保存故障记录 `com11_postproc_native_first_failure.log`。读帧器改用最多 256 拍、严格限制在 4 KiB 边界内的突发；增加真实 800×480 时序、四像素串行化、AXI 响应延迟和随机数据空隙的整帧仿真。新读帧器两帧 768,000 像素全部匹配，旧 16 拍参数在相同模型下复现欠载。重新导出前必须检查综合网表中的新计数器，避免 Vivado 模块引用缓存复用旧 RTL。

持续游戏板测还发现源地址元数据不能直接采样上游 `fb_addr`：该值可在复制期间变化为下一帧的分片地址，导致旧 FSR 拒绝处理。现在由帧桥实际读地址导出 `completed_source_base`，在 `copy_done` 时记录。三个 PS 颜色槽均为 1 MiB 对齐且单帧小于 1 MiB，因此最终读地址的高 12 位标识实际复制的源槽。回归测试覆盖复制过程中上游改到另一个分片的情形。前一版本另保存了仅修改 32 个元数据 D 输入的 ECO 脚本、原始检查点和连接清单；当前 SNP1 版本经过常规完整综合、布局布线，CPU 输入不再依赖此 PS 地址字段。

已完成实际 LCD 后处理像素核验：最近邻、双线性、色阶、复古、黑白共五组，每组 6,000 个采样点均与冻结 PS 源帧的参考计算一致。证据为 `report/postproc_lcd_pixel_acceptance.json`，包含源帧和捕获数据 SHA256；该测试帧为游戏退出后保留的颜色块帧。游戏运行时画面另见 `report/postproc_lcd_initial_comparison.png`。这两项证据不能代替原生 HR 修复后的完整上板验收。

前一版本的第六组验证使用实际冻结的 Neverball 游戏帧。输入 SHA256 为 `02c14ce673ca3df3a51211597daf003691a5feed468a5646cbc65c1767859329`，A53 与主机完整输出均为 `376463d69121f4a21807784ff95b221f59c9249f6ce4ad3610c75e29a8b37cab`。新的 SNP1 版本已重新完成六组实际 LCD 核验，全部 36,000 个采样点匹配；新游戏输入、配对输出与采样摘要见快照文档及 `report/postproc_snapshot_lcd_pixel_acceptance.json`。

旧版在暂停游戏后的 PS 快照与此前 PL 原始复制帧之间，曾观察到最近邻 10/6000、双线性 15/6000 个采样点不一致，色阶/复古/黑白也有少量差异。证据保存在 `report/postproc_game_ps_snapshot_mismatch/`。SNP1 修复针对这一问题，改为单独持有不可变的 PL 数据，并通过持续游戏、强制退出、无生产者超时及重新获取的 12 项真实板测；原始故障证据继续保留。

旧版无严格所有权的持续测试曾测得 2.95752 fps、快照重试 65 次，仅作为历史记录。SNP1 最初的 64 位逐次读取测得 1.64135 fps，采用实测最快的成对 128 位向量加载后为 2.16645 fps，重试零次。新报告分别保存输入复制、滤波计算和完整处理耗时；保持最后画面等待 LCD 捕获的时间不计入性能统计。游戏试验中的主动暂停核验也不能用于声称稳态游戏帧率。

2026-10-19 正常重启日志确认 `GOODIX_IRQ_RISING_ALREADY_ACTIVE`、`RASTERIX_PHYSICAL_GOODIX_INPUT_REGISTERED`，Xorg 使用 libinput 注册 TOUCHSCREEN，evdev 的物理坐标为 X=0..799、Y=0..479。用户当前无法操作屏幕，600 秒只读监测没有收到实体接触事件；不能据此判定实体触摸和方向已通过。

FSR1 在主机和实际 A53 上通过纯色与斜边自测。实际板帧输入 SHA256 为 `81f83c7836d1de030bb69978921ce172bc2dba50968470d99f3f80a04d7106b1`；两平台输出均为 `d329392f3e3e058503ce241a44a36b4e86228ac2ce0fb477c6f182b4014e63b9`。

官方源码：[AMD FSR1](https://github.com/GPUOpen-Effects/FidelityFX-FSR)、[Arm ASR generic library](https://github.com/arm/accuracy-super-resolution-generic-library)。精确提交、归档和生成内核校验值见 `config/game_ports_sources.json` 与 `report/fsr1_cpu_kernel_sources.json`。
