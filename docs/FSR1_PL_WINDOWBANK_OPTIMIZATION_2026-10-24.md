# FPGA FSR 显式缓存窗口优化记录

v19 已完成整机、实际开发板及独立主机验收：400×240→800×480 固定 MC 场景新输出 **36.8317 FPS**，源约 **60.0359 FPS**，FPGA 核心实测约 **15.494 ms**，三组完整黄金图和 LCD 6,000 点零差异。原 RasterIX／CNN 保留，性能测试采用 style0；本轮为 RAM 交付。

本轮从已实机验收的 v16 继续降低 FPGA 核心计算时间。v16 的 MC 输出实测为 30.0300 FPS，COMPUTE 平均约 23.193 ms，400×240 输入放大到 800×480，测试关闭风格化。原始证据见 [上一轮验收记录](FSR1_PL_OPTIMIZATION_2026-10-24.md)。

## 已完成的本地结果

| 候选 | EASU／RCAS 实际 II | HLS 整帧周期 | 100 MHz 计算延迟估算 | HLS LUT | HLS DSP | HLS BRAM18K |
|---|---|---:|---:|---:|---:|---:|
| v16 inlinercas | 6／6 | 2,311,858 | 23.11858 ms | 37,611 | 159 | 124 |
| v17 banked | 6／4 | 2,304,144 | 23.04144 ms | 40,929 | 167 | 132 |
| v18 windowbank | 4／4 | 1,541,298 | 15.41298 ms | 42,497 | 201 | 132 |
| v19 narrowtap | 4／4 | 1,541,333 | 15.41333 ms | 42,455 | 181 | 132 |

这些是 HLS 排程和资源估算，不能作为板上帧率或最终资源占用。v19 已完成整机、板端及独立主机验收，实测新输出 **36.8317 FPS**，详见下文。

v17 只使用缓存分组指令，边界钳位后的动态地址让 HLS 对每组 RAM 都保守安排全部读取，EASU 仍受双端口约束而维持 II6。

v18 把缓存明确组织为四组，每组保存每行 100 个 RGB565 像素。读取四列窗口时，对每个物理分组使用静态编号，再在寄存器中旋转和选取原始 12 个 EASU 样本。窗口起点限制在 0～396，所需坐标分别钳位，保留上下左右边界的原始取样。三组 tap／decode 运算单元和两组 RCAS 除法单元配合后，两个主要像素循环都达到 II4。没有加入忽略真实依赖的指令。

v19 保留 v18 的缓存代码和滤波运算，只将 `fixed_tap` 的两个偏移参数从通用 32 位整数限定为 4 位有符号数。独立检查实际源码的 12 个调用及四种像素奇偶组合，共 48 组、96 个偏移，范围均为 −7～7；源码还原参数类型后与 v18 完全一致。因此可减少通用宽乘法器开销，HLS DSP 从 201 降为 181，核心周期只增加 35 拍。

## 验证范围

- v17、v18、v19 均通过 19 个完整参考帧、7,296,000 像素的逐字节对照，输出与已验收 fixed-v8 参考完全一致。
- v18 在 800×480 全部输出坐标上通过 AddressSanitizer 越界检查，覆盖完整窗口读取。
- v18、v19 各自通过 8×6→16×12 的 C/RTL 联合仿真：两帧、九条命令、16 深度 FIFO；AXI 声明保留输入 96000／输出 384000，包含有效输出之外的 sentinel 检查。
- v18、v19 的新 RTL 协议审核通过，保留 64 字输出预填充、逐块写响应、最后 AXI B 响应后才完成、DATAFLOW 合流及既有 CSR／AXI 适配器语义。
- 缩小 RTL 仿真并非完整分辨率的 RTL 压力或形式证明。既有 FSR AXI 主接口仍未把 BRESP／RRESP 错误传播至返回码或 GPU 错误计数，后续仍需完整板端黄金帧和 LCD 采样。

对应证据在 `build/fsr-pl/fixed-v19-narrowtap/functional/result.json`、`cosim/`、`protocol-audit.json` 和 `tap-domain-audit.json`。v18 的越界证据在 `build/fsr-pl/fixed-v18-windowbank/bounds-asan/result.json`。

## 整机及实机状态

v19 独立工程为 `build/vivado_fsr_v19/rix_fsr_v19.xpr`，入口为 `scripts/create_fsr_v19_board.tcl`／`scripts/build_fsr_v19_board.tcl`。实际实现为 `build/fsr-v19-runs/impl_short_v19`。整机综合、布局布线、来源校验及板端帧率验证均已完成。v18 独立 OOC 和 v19 重复 OOC 已停止并保留来源记录；实际资源来自整机 FSR 子任务和最终实现报告。

21:47 整机中的 FSR 子任务已完成实际综合：LUT **19,721**、DSP **177**、BRAM Tile **62**、FF **17,701**，证据为 `build/vivado_fsr_v19/rix_fsr_v19.runs/rasterix_system_fsr_0_synth_1/rasterix_system_fsr_0_utilization_synth.rpt`。它与上表 HLS 估算及尚未完成的整机最终利用率分别统计。

22:00 顶层综合及 CNN／CDC 检查完成，综合阶段整机 LUT **72,671／70,560（102.99%）**、BRAM Tile **200／216（92.59%）**、DSP **329／360（91.39%）**。此时 LUT 超出容量，不能据此宣称整机可用；实现优化可能消除冗余逻辑，仍须以实际布局布线和最终时序为准。当前实现已开始，最终结果尚未产生。

22:21 布局完成：整机 LUT 降至 **68,220／70,560（96.68%）**，BRAM Tile **200／216**、DSP **329／360**，容量检查通过；布局阶段估算 WNS **+1.374 ns**。证据为 `build/fsr-v19-runs/impl_short_v19/axu3eg_rasterix_touch_top_utilization_placed.rpt` 及实际实现日志。它仍是布局结果，最终布线、时序及实机验收尚未完成。

22:42 整机布线及原有全部导出门槛通过，最终利用率为 **68,220 LUT／200 BRAM Tile／329 DSP**，最终 `timing.rpt` 的 WNS **+0.812 ns**、WHS **+0.010 ns**、WPWS **+0.124 ns**，所有指定时序约束满足（路由器结束时估算 WNS 为 +0.811 ns）。实际位流和检查点已导出到 `build/fsr-pl/fixed-v19-narrowtap/board/`；`fsr.bin` 为 **4,675,364 字节**，SHA256 `a488264602aaa053ea679def98a322947fad1ae4a71d629fab496efb7eed96a2`。随后进入只读来源校验。

只读来源校验已通过：1,556 个工作区文件，实际实现和导出 DCP 再生成的完整原始配置均与交付位流相同，XPR 与打开前快照逐字节一致。

最终验收曾发现缩小仿真清单的元数据错误：生成器记录了 LF 文本散列，而实际小尺寸源码及其 staged 副本为相同的 CRLF 字节。`prepare_fsr_v19_cosim_metadata_r2.py` 重新推导完整的尺寸／FIFO／AXI 边界替换，确认实际源码、项目、RTL 仿真结果均未改变，保留原清单，另写 `manifest-r2.json` 和修正来源记录。`accept_fsr_v19_cosim_r2_board.py` 保留原有全部门槛并加入修正来源检查，最终验收通过。

v16 RAM 目录及真实加载记录已保留为 `v16_11f7-retained`；v19 的两份压缩载荷通过 JTAG 传入预留 PS RAM，Linux 回读、解压及 SHA256 校验后，真实加载结果为 `new-loaded-and-verified`，未回退。当前启动 `11f7effc-6138-45a4-af2e-f3608360cf5d` 的活动凭据绑定上述 v19 位流及源清单 `1203b18ecf2db7d2bce6bc28579693c2e438e99446741a31b45229a4d4b4db5f`。

板端三组完整 800×480 黄金帧共 **1,152,000 像素零差异**，LCD **6,000 个采样点零差异**，错误及清理错误均为空。本轮没有修改 SD 启动包或默认入口。

## 实机 MC 帧率与剩余瓶颈

四轮均使用同一 64³ 世界、视距 32、帧率上限 120、自动操作、400×240→800×480、style0，每轮游戏运行 32 秒，输出计时窗口 20 秒。顺序为普通／预取／预取／普通，计时期间不传输素材或抓取图像。

| v19 调度 | 两轮新输出帧数 | 按计时窗口重新加权的新输出 FPS | 源渲染 FPS |
|---|---:|---:|---:|
| 普通 | 1,119 | 27.94496 | 60.11094 |
| 快照预取、LOAD 与 POST ACK 重叠 | **1,474** | **36.83168** | **60.03589** |

同一 v19 位流内的调度提升为 **31.80%**。两轮预取分别约 36.88／36.79 FPS。相较上一轮 v16 的 30.03003 FPS，本轮观测值高 **22.65%**；两轮硬件验证属于分时测试，不是物理位流切换 ABBA。完整帧计数和窗口用于重新加权，没有对四舍五入后的 FPS 直接求平均。

两轮预取按 1,474 个新输出帧加权：

| 运行统计 | 每个新输出帧平均 |
|---|---:|
| FPGA COMPUTE | **15.494 ms** |
| 输入 LOAD | **5.344 ms** |
| 快照等待 | **4.646 ms** |
| 未被 LOAD 隐藏的 POST 等待 | **1.640 ms** |

实际预取平均提前 11.910 ms，1,471 次请求中 711 次在 COMPUTE 完成时已 READY；重复源帧和租约过期均为零。FPGA 核心已从 v16 实测约 23.193 ms 降到 15.494 ms，输入搬运与快照等待合计仍约 9.99 ms。当前未达到 60 FPS，继续提速应针对这些等待和搬运成本。ARM 负责游戏逻辑、所有权和调度，实时 FSR 像素运算仍由 PL 完成。原 RasterIX／CNN 硬件保留，本次性能数字限于 MC、style0，尚无神经风格网络与 FSR 同时运行的性能结论。

## 独立证据核验与输出精度修正

主机实际回读 `report/postproc_fsr_prefetch_v19_11f7_evidence.bin`，**49,848 字节、91 个成员**，SHA256 `0d80a981f4b652d43b2f08d6bd51ffe6b13d78ae8fbaa9cd540bf29544100f30`。最终独立验收为 `report/fsr-pl/fixed-v19-narrowtap/prefetch-11f7-acceptance.json`，验证实际 v4／v19 加载、完整黄金帧摘要、LCD 原始采样、源码与 ELF 身份、场景、源与输出计数、计时窗口、加权统计及清理状态。

原主机校验器曾在第三轮触发固定 0.0001 FPS 容差：原始记录为 736 帧、20.0068 秒、36.7876 FPS，重算差约 0.000108 FPS。运行程序对时间和 FPS 使用 C++ 默认 6 位有效数字输出，两者各自舍入。真实 C++ 格式化例子复现了这组合法记录；14 个检查覆盖实际四轮、帧数偏移、错误 FPS／窗口、非法精度及非正数。新 `verify_fsr_prefetch_v19_rounding_r2_evidence.py` 仅将该浮点容差谓词改为已知输出精度的舍入区间相交检查，保留帧数、日志、窗口、图像、源码、SHA、加载和退出等全部原有门槛；原归档、运行数据和旧校验器均保留。修正来源在 `build/fsr-pl/fixed-v19-narrowtap/runtime-precision-repair-r2.json`。

可用 `scripts/summarize_fsr_v19_board.py` 从已核验的 v16／v19 归档重新推导统计，实际结果在 `report/fsr-pl/fixed-v19-narrowtap/performance-summary.json`。

| AArch64 程序 | SHA256 |
|---|---|
| `build/fsr-pl/fixed-v19-narrowtap/runtime/rix-fsr-pl` | `10f857e1e816534b434481a248e89fb0edce589ee12727a07a0bc11a21de3667` |
| `build/fsr-pl/fixed-v19-narrowtap/runtime-prefetch/rix-fsr-pl` | `5422a441513e75af04960ad9f584a5591a8d94eeb302152c3f3d11024dc1f19e` |

最终开发板仍加载 v19 RAM 位流，游戏与所有测试进程已退出，POST1 双线性空闲、快照空闲，现有五项 GPU 错误计数全零，CNN capabilities7／ABI0x20001／160×96 保留，游戏配置恢复原始字节。根分区 33,596 KiB、SD 16,440 KiB，32／16 MiB 保留检查未降低。SD 启动和默认入口保持现有版本，重启后仍从原 SD 镜像启动。
