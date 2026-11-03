# FSR1 的 FPGA PL 实现与验证

后续进展（2026-10-24）：v10 流水线与快照预取已实机达到 **18.52 FPS**，完整 FSR 仍在 FPGA 执行，三组全帧／LCD 核验通过。最新工程、两组四轮 ABBA 及 RAM 边界见 [第二轮优化记录](FSR1_PL_OPTIMIZATION_2026-10-23.md)。下文保留 v8 的独立历史验收。

2026-10-23。FSR1 已在 FPGA PL 实现并完成 fixed-v8 实机验收：400×240 RGB565 经完整 EASU12＋RCAS5 输出 800×480，正常游戏过程中 ARM 只管理帧所有权、寄存器和显示切换。三组全帧与 LCD 6000 点核验通过；ClassiCube 同地图自动游戏对照中，双线性新画面约 60.128 FPS，完整 PL FSR 新画面约 **8.468 FPS**，FSR 运行时的游戏源帧率约 60.133 FPS。当前位流在 RAM 中，SD 的 BOOT 未更新。

## fixed-v8 当前实测

已实际经 Linux FPGA Manager 加载 v8，完成协议自检、静态图和游戏测试。主机验收记录为 [actual-board-acceptance.json](../report/fsr-pl/fixed-v8/actual-board-acceptance.json)，板端原始记录解包在 `report/fsr-pl/fixed-v8/actual-board/`。64 个文件的回读包为 `report/postproc_fsr_pl_v8_evidence.bin`（tar.gz，37,900 B），SHA256 `95f47057bd839a06195f20aebf272e98ade04e4c51b3b33503caf9f2ac663b8a`。归档后主机重新检查了全部成员摘要、整机布线产物身份、金标准及实际 LCD 像素。

| 验证项目 | 实际结果 |
|---|---|
| 三组 MC 完整输出 | 每组 384,000 像素，合计 1,152,000 像素，与 v8 定点金标准逐像素零差异 |
| 额外显示帧与 LCD | 显示前全帧零差异；实际 LCD 6,000 点零差异 |
| 首次无游戏帧的 native→bilinear 恢复 | 初始 GPU frame IDs 均为 0；恢复通过，underflows 保持 0 |
| 静态内核计算 | 三组分别 97.533、97.610、97.678 ms；输入缓存加载约 1.1 ms |
| 游戏与控制程序退出 | 均正常退出，无残留 GPU 客户端；游戏配置恢复，POST requested/active 均为 1，SNP1 无租约、无过期 |
| 现有 GPU 错误计数 | 读、写、超时、欠流、扫描错误均为 0；新 FSR master 的响应错误覆盖限制见下文 |

游戏比较固定世界 64³、视距 32、400×240 源、800×480 输出、style0、自动移动与 120 FPS CPU 提交上限。两次游戏各运行 32 秒，在 `RIX_MEASURE_BEGIN` 后记录约 20 秒窗口；世界哈希均为 `3787233315`。计时窗口不抓图。

| 显示方式 | 游戏源帧率 | 新显示输出帧率 | 新输出计数 / 测量时间 |
|---|---:|---:|---|
| PL 双线性 | 60.128 FPS | 60.128 FPS | 1203 / 20.0074 s |
| PL EASU12＋RCAS5 | 60.133 FPS | **8.468 FPS** | 170 / 20.0767 s |

FSR 游戏实测平均加载 5.640 ms、计算 97.634 ms，SNP1 重试为 0，ARM 未逐像素处理。源帧计数另用 20.1718 s 窗口，不能把两个区间当作完全同步。LCD 在后台计算期间继续扫描最近完成的高分辨率帧，游戏源帧率不代表 FSR 新画面帧率。旧 A53 约 2.32 FPS 是历史结果，本轮没有同位流 CPU FSR 对照，不据此宣称严格加速比。

| 整机布线资源 | 用量 | 占比 |
|---|---:|---:|
| LUT | 61,952 / 70,560 | 87.80% |
| FF | 61,904 / 141,120 | 43.87% |
| BRAM36 等效 | 194.5 / 216 | 90.05% |
| DSP | 271 / 360 | 75.28% |

时序 WNS 0.758 ns、WHS 0.011 ns、WPWS 0.124 ns，所有用户约束满足，routing errors=0，无 critical CDC 或 bus-skew 违例。使用过的 CLB 为 8820/8820，表示所有 CLB 都放入了部分逻辑，不等于 LUT 用满。以上含 RasterIX、显示、保留的 CNN 和新增 FSR，不能与 HLS 单核估计混用。

实际 raw 位流为 `build/fsr-pl/fixed-v8/board/fsr.bin`，4,545,260 B，SHA256 `c071227653622f3c17fc8e8947aa3d4557a5283c33878925c303e92b7e1128b4`；source manifest SHA256 `f63180133e8afbcf65bbb205290209112d0743820a535bcdbfb983fd73c9ee70`。控制程序为 `build/fsr-pl/fixed-v8/runtime/rix-fsr-pl`，SHA256 `45309bfe1f5867b47e8bb01b2de40ce529d0f80ef35f2df4861680e82e018611`，绑定上述位流和当前启动 receipt。

本地可只读复核已回读的全部验收证据：

```powershell
python scripts/verify_fsr_v8_board_evidence.py
```

板端静态与动态脚本分别为 `linux/postproc/test_fsr_pl_board_v8.py` 和 `test_fsr_pl_live_v8.py`，后者实际使用 `/tmp/rix-fpga-fsr/rix-fsr-pl --live --seconds 20`，管理游戏启动、独立计时和正常退出。它们拒绝覆盖既有测试目录，完整操作和身份要求见 `report/fsr-pl/fixed-v8/board-qa-plan.md`。不要在未加载配套位流、没有有效 receipt 的启动中直接访问新增寄存器。

本轮验收后已恢复双线性空闲显示。FSR 位流和控制程序在 RAM 中可用，普通游戏入口仍按各自配置启动；没有把 FSR 加到 SD BOOT，也没有把 CNN 风格入口改成 FSR。断电后按 SD 中原有配置启动。

## 实际 v7 上板结果与修复

完整证据在 `report/fsr-pl/fixed-v7/actual-board/`；原始回读包 `report/postproc_fsr_pl_v7_evidence.bin` 为 tar.gz，9826 B，SHA256 `44db70ba83df0f0c33a52ff4f79eae5ee45f27ecd13388b7adb2a602b37aaf9b`。

- 整机实际布线：LUT 62,166/70,560，FF 61,993/141,120，BRAM 193.5/216，DSP 271/360；WNS 1.036 ns、WHS 0.010 ns，全部用户时序约束满足，routing errors=0。原有 RasterIX 和 CNN 保留。
- raw 位流 4,726,784 B，SHA256 `10369dbde0953497ed58567b67789c7da0bbb3d8ac61b7f4fc22e7aeb8db9a2c`，经保留回退镜像的 Linux FPGA Manager RAM 事务实际加载成功。
- 三组 400×240→800×480 实机全帧分别逐像素匹配 fixed-v7 金标准；每组 384,000 像素、零差异，未显示前即完成核对。额外显示一次完整帧也匹配，实际 LCD 6000 点零差异。
- 实测内核单帧约 230 ms，加载缓存约 1.1 ms；静态文件测试还包含输入准备和全帧 CPU 核验，不能将其 `processed_fps` 当作游戏超分帧率。尚未做 v7 游戏 live 吞吐。
- 唯一失败是 native 恢复到 bilinear 后 underflows 从 0 变成 1；其他错误为 0，frame IDs 全为 0。FPGA 重新加载后尚未有任何真实 GPU 呈现，`scan_valid=0`。旧 top 更新 POST，却未对无 LR 源的 scaler prepare；旧 native 状态遗留到 LR，在首像素误报一次缺粮。计数未被清除/忽略，QA 的 passed=false 保留。
- 通过原事务的已验证 rollback 路径实际恢复 atomic-v4，模块/绑定/POST 恢复且错误计数全零。独立恢复报告保留，不改写原加载或失败报告；未写 SD/BOOT。

fixed-v8 隔离复制 scaler/top，增加 `frame_valid`：每个 accepted_prepare 都清理行状态，但无有效源时保持 dropped，不修改累计 underflow 计数。视频回归检查 21 帧、旧四种模式、全分辨率 AXI reader 两帧及两个失败负对照，全部通过；旧门控负对照准确复现此次误报。共享 RTL 和已发布工程不变。

FSR v7 每像素发一笔 AXI 写，384,000 笔 AW/B 放大了实际延迟。v8 新增一行 800×32-bit 缓存和 II=1 连续写循环，生成 RTL 的内部请求长度已变为每行 800 words，由适配器按最大 64 beats 与 4 KiB 边界分割。算术两份头与 v7 逐字节相同，13+6 全尺寸图再次通过，缩小 C/RTL 再次 PASS。v8 HLS 为 31,187 LUT、19,939 FF、112 DSP、117 BRAM18K，估算约 97.196 ms；实际游戏计算 97.634 ms，与估计接近。静态内核由 v7 约 230 ms 降至约 97.6 ms，时间减少约 57.6%；这是内核计算时间改善，不是已测的 v7/v8 游戏 FPS 比较。

HLS 的 AP_DONE 已追踪到最后 B 响应完成后才产生；mode0 的 result_tag_vld 可以提前有效，因此 ARM 一直以 AP_DONE 为缓存所有权边界。适配器未把 BRESP/RRESP 错误码传播到返回码，原 GPU 计数也不覆盖新增 FSR master，不能以 return=0/旧计数零替代完整输出验证。

## 本轮已完成的实现

当前已加载版本为 `fixed-v8`。源码在 `src/hls/fsr1/rix_fsr1_fixed_burst.cpp`、`fsr1_fixed.hpp`、`fsr1_luma_tables.hpp`，冻结副本及 SHA256 清单在 `build/fsr-pl/fixed-v8/`。24 位 Q6.18 用于颜色和主要算术，方向计算保留 33 位 Q3.30 亮度；整数实现官方近似倒数/倒平方根常量，除法用两次商精化，不含 CPU 像素处理或浮点 IP。MIT 版权和许可保留于 `src/hls/fsr1/LICENSE.FSR1.txt`。

内核有三个正常命令：0 将一帧受保护的 XRGB8888 快照加载成片内 RGB565 缓存；1 执行 EASU12 + RCAS5 并写回高分辨率帧；2 作废缓存。加载完成后可释放 SNP1，计算期间源图像已经独立缓存。帧号与缓存绑定；重复计算、非法模式、缺失输入和数值异常均有返回码。ARM 控制程序为 `linux/postproc/rix_fsr_pl.cpp`，使用 `0xA0040000` AXI-Lite，不经 ARM 搬运正常游戏像素。

| 证据 | 当前结果与范围 |
|---|---|
| FP32 HLS 功能模型 | 13 组全尺寸输入共 4,992,000 输出像素，与原 CPU FSR 参考逐位一致，见 `report/fsr-pl/float-v2/` |
| fixed-v8 定点模型 | 同 13 组检查通过，最大 RGB 通道误差为 1/255；其中九组合成图精确一致，见 `report/fsr-pl/fixed-v8/functional.json` |
| 额外数值压力检查 | 随机 RGB565、渐变、彩色块、邻近量化值、等亮度红蓝交换、单点脉冲，共 6 张全尺寸图通过，见 `report/fsr-pl/fixed-v8/stress/result.json`；13+6 共 7,296,000 输出像素，与 v7 定点输出一致 |
| fixed-v8 C/RTL | 8×6→16×12、两帧、9 次顶层调用 PASS，检查缓存输入不再依赖源 DDR、帧标记及写入边界；不是全尺寸 RTL 验证 |
| fixed-v8 HLS 估计 | 31,187 LUT、19,939 FF、112 DSP、117 个 BRAM18K；100 MHz 下计算上界 9,719,570 周期即 97.196 ms，尚不含快照、加载和显示切换 |
| 实际整机资源/板端 FPS | 布线与真实加载、静态及 live 验收全部通过；完整 FSR 新输出 8.468 FPS，详见本文首节及 `actual-board-acceptance.json` |

定点化曾发现罕见边缘最大误差 14/255，未放宽误差门槛。原因是 RGB565 的 FP32 亮度累加舍入产生微小梯度，FSR 的归一化边缘长度会放大这些差异。Q18 亮度及改变累加顺序会抹掉梯度。当前用小型通道 ROM、整数 FP32 舍入以及高精度亮度保留原语义，异常已消除。旧失败版本保留以便追溯。

`float-v2` 的实际 Vivado 单核综合占 29,445 LUT、29,377 FF、58 BRAM、178 DSP，直接叠加既有 47,216 LUT 的整机会超出器件；因此转向定点和共享电路。`fixed-v4` 虽然节约了重复解码逻辑，但共享内存函数引入串行依赖，估算退化到 401 ms；当前将解码改成无状态纯函数，恢复了吞吐。这些候选均未部署。

可在 Vivado 打开 `build/vivado_fsr_fixed_v8/rasterix_fsr_fixed_v8.xpr` 查看当前已布线并实际运行的工程；v7 工程也保留在 `build/vivado_fsr_fixed_v7/rasterix_fsr_fixed_v7.xpr`。两者保留原有 v4 CNN，新增 FSR AXI 控制/DDR 主口；v8 使用独立冻结的视频初始化修复。既有部署工程、SD 启动包和 CPU FSR 二进制没有被覆盖。

## 实现边界

首版针对 FSR1 固定 2×：400×240 RGB565 输入，800×480 RGB 输出，完整 EASU 12-tap 与 RCAS 5-tap 在 PL 执行。ARM 负责游戏逻辑、顶点前端、启动配置与帧调度，不执行逐像素超分。

已验收的数据通路为：

`RasterIX → 已完成帧/受保护快照 → PL EASU → PL RCAS → PL DDR 高分辨率双缓冲 → 现有 native LCD scanout`

EASU 与 RCAS 的完整算术在 PL 独立后台 AXI 主设备中执行，结果发布到高分辨率双缓冲，LCD 通过 native 模式扫描；原有 nearest/bilinear 和 CNN 路径一并保留。当前不支持任意倍率，也没有神经超分、FSR2/3 的历史帧重建或帧生成。

## 现有可复用材料

- 官方来源锁定于 `config/game_ports_sources.json` 的 FSR1 提交 `a21ffb8f6c13233ba336352bdff293894c706575`。
- `external/game-ports/fsr1/ffx-fsr/ffx_fsr1.h` 和 `build/postproc-touch/generated/fsr1_cpu_generated.hpp` 提供当前算法参考；后者保留 EASU/RCAS 的 FP32 算法运算，固定 2× 采样坐标。
- `report/classicube-fsr-comparison-20261023/` 有三组实际 MC 同帧输入及输出。新增帧的主机、A53 完整 FSR 输出一致，6,000 点实际 LCD 采样零差异，可用于定点候选对照。
- 旧工程 `../linestream-rs/docs/easu_rcas_rtl_design.md` 是设计草案，并非已部署硬件。新实现从官方参考建立，未使用旧草案的时钟与资源估计作为整机结果。

## 算法硬件化要点

固定 2× 时输出到输入的坐标是 `(p+0.5)/2-0.5`。两个相位为 1/4、3/4，四角权重只有 1/16、3/16、9/16；边界仍按参考复制像素，不能把第一像素的坐标直接截为零而改变滤波相位。

EASU 采用 4×4 邻域中的 12 个 tap，包含方向/长度估计、方向归一化、各向异性、带负瓣的 tap 权重、加权归一化及最近四点 min/max 去振铃。固定倍率可化简坐标和部分乘法，但图像相关的方向和各向异性不是常数。

EASU 参考每输出点包括八次局部梯度近似倒数、一次方向近似倒平方根、stretch 与 lobe 的两次近似倒数，以及最终权重和的倒数。定点实现应明确近零行为、精度、范围和舍入；不能把这些数值语义全部替换后仍宣称与官方参考逐位相同。

RCAS 是高分辨率五点十字邻域。RGB 每通道有两个 limiter 倒数，另有共享的 medium reciprocal，共七处；当前参考未启用 `FSR_RCAS_DENOISE`，不能照旧草案把每通道运算误计成总共两次 limiter。固定 sharpness 0.2，可预计算 `2^-0.2`。

本轮已经完成软件定点模型及相对 FP32 的误差、边界和极端图案检查，再锁定 LUT/迭代近似与位宽。负 tap 权重、累加器、饱和以及 RCAS 的近零分母均纳入数值检查。主机模型的最大通道误差为 1/255；板端对定点金标准零差异不能改称为对 FP32 每像素完全相同。

## 吞吐与存储预算

800×480 在名义 60 FPS 下需要 23.04 M 个有效输出像素/秒。独立 100 MHz 内核平均预算约 4.34 周期/输出像素，包含一帧内的所有算子调度及访存开销；不能把“12 taps 各用一拍”的单路内核直接称为 60 FPS。

现有 LCD 像素时钟约 33.333 MHz、时序总数 1056×525。如果直接插在扫描路径，活动区要求每像素时钟接收一个像素，平均像素吞吐预算不能代替活动区的实时要求。首版宜用独立计算域、帧缓冲和垂直消隐切换，将计算与扫描解耦。

LR 四行 RGB8 的原始容量为 4,800 B，RCAS 三行 HR RGB8 为 7,200 B；这只是颜色的存储下限。保留 EASU 中间精度、多端口实现、流水级、FIFO 和对齐数据会增加资源，不能将 12,000 B 直接当作最终 BRAM 占用。

若输入为 XRGB8888，按每帧 LR 读一次、最终 HR 写一次、LCD HR 读一次计算，60 FPS 下最低 DDR 有效载荷为约 207.36 MB/s，不含帧桥、快照复制、CNN、AXI 事务损耗。EASU 与 RCAS 若通过 DDR 交换完整 HR 中间图，还会增加一次 HR 写回与读取；优先考虑片上行缓存连接两个算子。

此前 v4 整机基线用量为 LUT 47,216/70,560、BRAM 138/216、DSP 152/360，使用过的 CLB 8,520/8,820。它不含本轮 FSR；当前资源以本文首节的 v8 实际布线结果为准。

## 本轮采用的实现与验收顺序

1. 使用本轮真实帧建立完整 EASU + RCAS 定点参考，记录相对现有 FP32 输出的误差，不改变既有黄金参考。
2. 实现独立算术流水与窗口缓存，仿真覆盖实际 MC 帧、纯色、斜边、棋盘、极暗/极亮、边界、背压和连续帧。
3. 独立综合量化资源、实际时钟和启动间隔；随后接入带所有权的 AXI 读写与高分辨率双缓冲。源帧在最后一次读取前不得被生产者复用，目标 bank 在最后一个写响应完成前不得发布给 LCD。
4. ARM 仅发送地址、帧号和配置，等待硬件完成后切换显示；不通过现有逐像素 CPU PIO 调用模拟硬件加速。不能因当前 SNP1 通路可用就假定其申请/释放成本为零。
5. FSR 独立模式已经验证；HUD 保护与神经风格串联仍待实现。现有神经风格模式在 ARM 融合到 800×480，不能原样串在新的 400×240→800×480 FSR 之前；需要明确低分辨率融合方案后重新对照画质。
6. 整机布线与板端完整像素、LCD 采样、持续新画面 FPS 均已通过，构成本轮 FSR1 PL 接入证据；SD 冷启动持久化、长时间稳定性和人工观感不包含在本轮验收中。

## 后续性能方向

突发写已经消除了 v7 的主要 AXI 事务开销。当前游戏计算 97.634 ms 与 HLS 97.196 ms 接近，约占新输出间隔 118.10 ms 的 82.7%，主要瓶颈已经转为算术调度。每行依次执行 EASU（实际 II=16）、RCAS（II=8）和写回（II=1），下一轮优先评估行流水重叠、窗口复用和倒数运算共享，分别检查缓存端口冲突、精度与资源代价；不能仅提高 AXI burst 长度就期待 60 FPS。

剩余约 8,608 LUT、21.5 个 BRAM36 等效和 89 DSP，简单复制整个核无法按当前规模放入。减少快照加载与显示等待可回收部分时间，但即使不计这两项，当前 97.6 ms 计算本身也只对应约 10.2 FPS。更高帧率需要新的算子结构，并重新通过 19 组数值、C/RTL、整机布线和独立实机测量；当前 8.468 FPS 不外推为这些优化后的结果。

与上一轮对比的关系见 [MC FSR 与插值测试](CLASSICUBE_FSR_COMPARISON_2026-10-23.md)。
