# 无 PL FSR 基座与几何实机参考阶段记录（2026-10-29）

本轮完成独立双 TMU、无 PL FSR、无神经网络 CNN 的整机综合与布局布线，以及实际 ARM 几何数值参考。完整 FPGA 几何内核尚未实现或接入；本轮没有测得新的游戏 FPS。板上保持原 v23 恢复镜像，本轮只在 RAM 中运行纯 CPU 参考测试，没有改写 SD 或编程 PL。

## 1. 已完成的硬件基座

Vivado 工程：[独立 no-FSR 工程](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/build/vivado_java256_nofsr_r1/rix_java256_nofsr_r1.xpr)。

移除 HLS FSR 单元、其 AXI 主端口、控制端点和 `0xA0040000` 地址映射。保留现有双纹理 RasterIX、显示、DMA、触摸、DDR 与神经网络占位控制接口。GPU 设计频率保持 100 MHz，控制互联从五端点缩至四端点。PL 存储互联仍保留三个时钟域，因为 MIG 端口仍使用 200 MHz；没有把 DDR 所需时钟随 FSR 删除。

新控制标识为 `J2N1 / 0x4a324e31`；`0xb4=2`，`0xb8=0`，`0xbc=0`，明确表示双 TMU、FSR/CNN 不可用、几何前端未接入。布局布线结果如下；综合与布局布线是不同阶段，不能混作同一种统计。

| 资源 | 综合使用 | 布线后使用 | 布线后剩余 | 布线后占用率 |
|---|---:|---:|---:|---:|
| LUT | 41008 | 38050 | 32510 | 53.93% |
| 寄存器 | 45052 | 43594 | 97526 | 30.89% |
| DSP | 157 | 157 | 203 | 43.61% |
| BRAM tile | 71 | 71 | 145 | 32.87% |

布线后资源分布：

| 模块组 | LUT | 寄存器 | DSP | BRAM tile |
|---|---:|---:|---:|---:|
| RasterIX_and_display | 17951 | 15772 | 154 | 42.5 |
| AXI_interconnect | 9302 | 14116 | 0 | 0 |
| PL_DDR4 | 7621 | 8960 | 3 | 25.5 |
| DMA | 1541 | 2240 | 0 | 3 |
| other | 1635 | 2506 | 0 | 0 |

最终 WNS **1.252 ns**、WHS **0.010 ns**、脉宽余量 **0.124 ns**，已约束路径对应失败端点均为零。构建脚本还检查黑盒、Critical CDC 和总线偏斜后才导出位流。

报告并非零警告：DRC 有 264 项 Warning，主要为既有 DSP 流水、存储器与调试结构提示；没有 Error 或 Critical Warning。内部无时钟、内部未约束端点、多时钟冲突和环路均为零。外设 I/O 的 no-input-delay／no-output-delay 计数为 4／6，与原 interconnect-r1 候选相同；仍需上板验证外设信号和功能。

候选位流：[java256.bin](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/build/minecraft-java-125/no-fsr-base-r1/board/java256.bin)，SHA-256 `6f8b5437fccbd0a5d8500a88011404deac4866591b702aa4e5b441875721350f`。这是本地构建候选，尚未通过上板像素与游戏验收。

旧 interconnect-r1 双 TMU＋FSR 候选的布线后使用为 59,565 LUT、65,053 寄存器、330 DSP、149 BRAM。新候选相对它减少 21515 LUT、21459 寄存器、173 DSP、78 BRAM；差额包含 FSR 以及随端点减少而变化的互联，不能全算作 FSR 内核自身资源。

## 2. 完整几何是否能继续做

实测剩余 **32510 LUT、203 DSP、145 BRAM**，足以继续做共享浮点单元的前端原型并综合验证。先前给出的 20,000 LUT／30,000 寄存器／120 DSP／48 BRAM 只是“几何＋新增接口”的设计上限，不是已综合的几何面积。按此上限相加会使用 58050 LUT、73594 寄存器、277 DSP、119 BRAM；最终能否容纳、时序与吞吐如何，仍由几何 HLS/RTL 和整机布局布线决定。

本轮删除 FSR 的直接收益是资源空间。之前游戏的对照轮采用最近邻输出，并不能据此推断删除一个未在该像素路径运行的 FSR 就会提升原始游戏帧率。

完整前端仍必须包括模型视图与投影、两套纹理矩阵、图元装配、六面齐次裁剪和属性插值、剔除、透视／视口变换、三角形边函数与属性梯度、既有 W 归一化，以及按三个 80 行分片保持绘制顺序。只实现矩阵乘法不能算完整前端。

## 3. 本轮建立的实际数值参考

参考采用当前工作的冻结 CPU 流水，冻结了 **88 个应用依赖文件**。这些文件与外部 RasterIX 目录存在差异，包括用户裁剪平面状态和光栅参数算法，因此没有直接用外部目录代替板上版本。

- 提出 80 字节、float32、小端设备顶点记录，保留位置、颜色、两套纹理坐标、法线和点大小；它仍是原型定义，未改变正在使用的 GPU 命令 ABI。ARM 虚拟地址和 CPU `sourceIndex` 不能直接当 PL 地址使用。
- 主机 27 用例、两次重复结果一致，独立 126 项格式／有限值／边界／分片顺序检查通过。
- ARM R109 实机在三把共享锁、恢复隔离、空闲与当前 v23 身份检查下运行，27 用例通过，产生 30 个可见三角形和 78 条分片记录；GPU、POST、驱动、启动 ID 与激活凭据保持不变。
- 用例覆盖六面全剔除与越界裁剪、多面裁剪、双纹理矩阵、变化 W、跨三分片四边形、条带、点、线、用户裁剪平面、平面颜色、polygon offset、灯光、剔除和单 TMU 状态。它们是 CPU 数值用例，不是 FPGA 运算或游戏性能测试。

现有描述符为 192 字节，三角形 GPU 命令头为 `0x300000c0`，长度字段按字节。参考 `.bands.bin` 每行是“4 字节目标分片＋4 字节命令头＋192 字节描述符”，其中目标分片是参考元数据，不能整行原样当 GPU 命令流。输出按分片分组，并保持分片内原图元顺序。

主机与 ARM 的 108 条三角形／分片记录整数头全部一致，1842 个浮点字段有差异，最大绝对差 **2.30968e-06**；因此没有宣称两平台逐位相同。跨零附近的 ULP 距离会很大，不能直接作为统一容差。后续 FPGA 使用 [实际 ARM 导出结果](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/report/minecraft-java-125/no-fsr-base-r1/geometry-arm-r109/downloaded/arm-output) 做数值基准，并另做像素验证。

R108 在运行 CPU 测试前被旧 atomic-v4 报告的镜像身份检查中止，记录已保留。R109 使用同一次启动中成功加载当前 v23 的实际报告，核对报告、激活凭据、启动 ID、镜像和来源哈希、CNN 身份、驱动与绑定；16 项主机负例检查通过。没有改写旧报告或跳过恢复隔离。

## 4. 加载与原 FSR 保留

独立加载器 [java_no_fsr_loader_r1.py](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/build/minecraft-java-125/no-fsr-base-r1/java_no_fsr_loader_r1.py) 绑定上述候选位流 SHA，保留原事务锁、空闲、模块、日记和回滚保护。新目标仅允许精确 no-FSR 候选或已知 v23 恢复镜像；no-FSR 分支核对全部能力寄存器，跳过已移除的 `0xA0040000`，并写 `RIX_JAVA_NOFSR_ACTIVE_V1` 凭据，避免被旧 FSR 客户端当成有 FSR 的硬件。76 项主机检查通过；这不能替代上板验收。调用前仍须由受保护事务编排保存上一份报告／凭据，提供与回滚镜像匹配的同启动会话证明，不能直接执行并删除现有凭据。

原 PL FSR 的代码、HLS IP、RTL 集成、脚本、测试、证据、旧镜像与检查点保存在 [独立 FSR 归档说明](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/preserved/pl-fsr-v23-20261029/README.md)。本轮复核归档 SHA-256 仍为 `0009bffd730853ddc8ab60a3ded6239330b9c694b01f5ddbbd2daeb8c6d957e1`，220 个本地冻结源文件哈希也保持一致。归档不在 `build/` 中。

## 5. 下一阶段顺序

1. 用实际 ARM 参考做可综合几何内核，先打通模型视图／投影／纹理变换、六面裁剪和完整三角形参数，再评估资源与吞吐；不能用一个矩阵模块替代整条流水。
2. 定义设备驻留网格、版本化状态、更新和完成 fence、缓冲所有权与背压；补上三分片的有序提交。未经过能力握手和地址验证前，不重用原 FSR 控制地址。
3. 先验收无 FSR 基座的上板原生像素、双 TMU 与恢复路径，再集成几何内核做相同画质、场景和参数的 FPS 对照，区分 CPU 几何、命令等待、片元吞吐和显示限制。
4. 几何通过后再尝试 Mali 的 GLES2 FSR1 EASU／RCAS 适配及帧交接；目前尚无这条超分通路的性能结果。详细限制见 [几何与 Mali 路线分析](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/docs/JAVA125_NOFSR_GEOMETRY_MALI_PLAN_2026-10-29.md)。

主要机器证据：[布线资源审计](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/report/minecraft-java-125/no-fsr-base-r1/resource-routed.json)、[加载器检查](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/report/minecraft-java-125/no-fsr-base-r1/loader-host-tests/r4/host-tests.json)、[参考格式检查](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/report/minecraft-java-125/no-fsr-base-r1/geometry-reference/verification.json)、[ARM 实机参考验收](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/report/minecraft-java-125/no-fsr-base-r1/geometry-arm-r109/acceptance.json)。
