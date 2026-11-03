# Java 1.2.5：连续顶点直通路径重新验证与主线采用

2026-10-30，继续 ARM 几何前端＋PL RasterIX 路线。本轮在相同画质下验证已有顺序顶点直通路径，并增加约 1 Hz 的 GPU 状态采样。

**四轮 ABBA 独立验收通过：缓存开启加权 23.5930 FPS，直通变换 25.3751 FPS，观测提升 7.55%。两轮直通结果都高于两轮缓存结果。已将直通开关纳入新的本地主线包 r2，r1 保留。**

这是恢复和验证已有优化，回到此前约 25～26 FPS 的区间，没有刷新此前最好成绩，也没有达到稳定 32／60 FPS。原主线配置的旁路开关为 0，本次有了实际 Tiny、相同画质的新对照后改为 1。没有把上一轮最低画质的 22.89 FPS 当成本轮对照基线。

## 改动与不变量

顺序批次原来逐个经过顶点缓存查询和写入；已有 `pushSequentialVertex()` 路径直接执行同一个变换函数，省去这些缓存操作。本轮采用 `RIX_JAVA_BATCH_CACHE_BYPASS=1`，没有重新实现几何算法，也没有把几何迁入 FPGA。该开关用于已有连续批次分支，不删除普通索引路径的缓存逻辑。

保持原画质：400×240、完整 256×256 纹理、实际 Tiny、Fast、关闭云、AO 开启、全部粒子、行走晃动开启、和平、最近邻呈现。Advanced OpenGL 和红蓝立体关闭，FOV／Gamma 为 0，两组 `fpsLimit=1` 相同。每轮从游戏对象核对十二项设置，玩家位置和朝向固定。

共享库仍为 `8e89c36f66e497f26044c779551e5703fbbb7a1a02ff938c76315d8c99d4a993`，双 TMU 位流仍为 `14fd58da8a1a0348b0033f7efef35dc5498c2f4bd1f2a3c43b77404adc9cd961`。不启用 FSR、CNN、Mali、Vortex 或 FPGA 几何；纹理等待后移开关仍为 0。时钟、SD 和默认启动配置没有更新。

## 实机结果

新编号 R122 缓存／R123 直通／R124 直通／R125 缓存。每轮预热 60 秒，按正式硬件计数与配对时钟测量约 30 秒；每轮完整执行原生回归、原版游戏、正常退出和 v23 恢复。

| 轮次 | 路径 | 完成帧 | 窗口 s | FPS | 命令拍／完成帧 | 百万命令拍／秒 | DMA FINISH 等待比 |
|---|---|---:|---:|---:|---:|---:|---:|
| R122 | 缓存 | 710 | 30.0073 | 23.6609 | 328,727 | 7.778 | 27.33% |
| R123 | 直通 | 765 | 30.0059 | 25.4950 | 327,272 | 8.344 | 29.37% |
| R124 | 直通 | 783 | 30.9989 | 25.2589 | 332,384 | 8.396 | 29.31% |
| R125 | 缓存 | 706 | 30.0105 | 23.5251 | 329,609 | 7.754 | 27.13% |

按帧数和实际秒数加权：缓存 1416／60.01786，直通 1548／61.00479。相邻对照分别为 R122→R123 的 +7.75%、R125→R124 的 +7.37%；对应每帧命令量差异约 −0.44%、+0.84%。它们比上一轮降低画质的结果更一致，支持在当前 Java 主线采用该开关。

![正式完成帧与命令吞吐](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/docs/assets/java-cache-tiny-r121/comparison.png)

四轮最终截图字节完全相同，十二项运行时设置、冻结存档源哈希和原选项备份相同。每轮 48 张原生测试图跨轮逐字节一致，共比较 55,296,000 字节；包括实际双纹理、资源生命周期、可见大批次压力和尾部队列排空检查。

四轮最终位置、朝向、世界类型相同，生命值 20、死亡时间 0。世界时间为 2279／2279／2319／2279 tick，整场批次数也不完全相同；没有声称 JIT、实体与加载工作全部一致。整场提交／消费顶点与批次严格相等，不能把整场统计直接除以中间 30 秒窗口。有效结果全部保留。

![相同画质的实际游戏截图](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/docs/assets/java-cache-tiny-r121/world-frames-comparison.png)

## 新增的采样能力

新增私有采样器保留原有约 0.5 秒 CPU 线程采样，并约每秒调用一次现有显示驱动的 `GET_STATUS`，记录读取前后单调时钟。没有发送 START／XFER／FINISH、清零计数、修改寄存器或改变驱动 ABI。生产入口只使用真实 `DisplayStatus`，测试中的假设备不用于实机。

四轮正式窗口内部各得到 29／29／30／29 个 GPU 读数，独立校验 ABI、配置、状态、错误位、时间跨度和连续计数。最大单次读窗口约 0.102 ms，每轮窗口内读窗口累计约 2.27～2.43 ms。这是读调用的墙钟跨度，不包含所有 Python／文件采样成本；两种路径采用同一采样器。

![GPU 计数的时间变化](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/docs/assets/java-cache-tiny-r121/gpu-timeline.png)

曲线来自完整窗口内部约 1 秒的区间，边界与正式均值不同，不能替代正式 FPS。一秒只有约 23～26 个完成帧，整帧计数边界也会形成起伏，不能把曲线局部极值当作逐帧延迟或卡顿统计。

这一组正式窗口每帧命令量约 327～332 千拍，上一组约 350 千拍的高负载状态没有重现；没有因此宣称已修复它的触发原因。直通路径的命令吞吐从约 7.75～7.78 增到 8.34～8.40 百万拍／秒，与省去 ARM 缓存工作后更快供数的解释相容。

DMA FINISH 等待比由约 27% 升到约 29%，采样进程中排除 Compiler 名称线程的 CPU 核数由 0.9243 降到 0.9072。两者不能直接相加为独占阶段，也不能证明瓶颈全部在 ARM 或全部在 PL；现有计数仍没有命令输入空泡、光栅反压和有效片段的区分。

## 采用位置与构建验证

主线选择：[config/java_arm_mainline.json](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/config/java_arm_mainline.json)，默认构建尝试为 r2，缓存旁路为 1，FPGA 几何与纹理等待后移仍为 0。

构建入口仍为 `./build.ps1 -Action arm`。构建器现在按配置选择产物目录和实际缓存模式，生成的 `environment.sh` 导出真实值；不会把已选择的 1 固定写回 0，也不会覆盖旧 r1。

新包：[arm-mainline-r2](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/build/minecraft-java-125/arm-mainline-r2)。已重新链接并验证 AArch64 库字节身份，所选直通模式的宿主几何回归覆盖 96 次绘制、11520 顶点、11710 三角形，2,248,320 字节与冻结参考完全相同。旧 r1 的全部输出哈希也重新核对通过。

采纳记录：[selection.json](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/report/minecraft-java-125/swap-fence/cache-tiny-r121-comparison/selection.json)。原始对照汇总在采纳前生成，其 `candidate_promoted=false` 保留原样，最终选择由这份独立记录说明。

这是本地推荐包和真实板测结果；没有更新 SD、自启动或常驻游戏进程。板上最后一次 staging 是 R125，测试结束后处于原 v23 空闲状态。直通实际在 R123、R124 跑过，不能将 r2 的本地构建证明另算一轮游戏测试。

## 接下来值得做的优化

当前平均每帧约 39.41 ms。平均 32 FPS 需要降至 31.25 ms，仍需减少约 8.16 ms；60 FPS 需要 16.67 ms，差距更大。短测与约 1 秒计数都不能证明稳定帧时间。

下一步优先测 ARM 变换／裁剪／三角形参数／命令准备各阶段的独占耗时和批次大小分布，再判断大批次分块并行或减少重复参数准备的收益。新增只读计数是定位手段，不是解决全部根因的证明。

旧日志每场有约 2.2～2.4 万条重复 `GL_CLAMP` 提示，可作为后续单独候选；本次没有修改日志级别或抑制提示，更没有隐藏 GL 错误。其性能收益尚未测试，不承诺靠这一项达到 32 FPS。

## 证据与结束状态

- 四轮整体回读 1,341,440 字节，SHA256 `bd5c4c26c91c12d0934649aa5bc3a722cf2a4b5f63b58ec2ae7b7fd35987cfb5`，文件为 `report/minecraft-java-125/pl-cache-tiny-r122-r125-readback.bin`。
- 各轮独立验收：`report/minecraft-java-125/swap-fence/board-acceptance-r122.json` 至 `board-acceptance-r125.json`；GPU 读数核验结果保存在其中的 `gpu_timeline`。
- 汇总与选择：`report/minecraft-java-125/swap-fence/cache-tiny-r121-comparison/`。两张统计图均有 PNG／SVG；源截图来自 RGB565 回读，没有手工改动游戏画面。
- 新采样器的 3 项进程／失败行为检查、每轮 Windows／POSIX 各 9 项故障检查均通过；模拟设备的测试证明与真实板测证据分开保存。
- 最终当前启动仍为 `83f0dfd6-165c-4d4c-9120-7cb0554a0da9`，原 v23 凭据有效，隔离守卫通过，无活动游戏和 RAM 接收器，错误及帧计数为 0，POST 恢复 mode 1，快照无过期，全部锁释放，串口关闭。
- 最终核验绑定文件：[final-verification.json](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/report/minecraft-java-125/cache-tiny-r121-evidence/final-verification.json)，包含本轮回读、守卫源码、新串口日志和实际空闲状态的哈希。
- CPU 前后读数保持 userspace／1,066,666 kHz；不是全程频率记录。没有可读的 thermal zone 数据，不声称已排除温度因素。
- 原 PL FSR 保留归档哈希仍为 `0009bffd730853ddc8ab60a3ded6239330b9c694b01f5ddbbd2daeb8c6d957e1`，相关源码及旧实验均保留。

主要复现脚本位于项目 `scripts`：`prepare_java_cache_tiny_r121.py`、`run_java_cache_tiny_r121.ps1`、`export_java_cache_tiny_evidence_r126.ps1`、`summarize_java_cache_tiny_r121.py`、`plot_java_cache_tiny_r121.py`。采样及验证源码位于 `linux/java_minecraft/java_cpu_gpu_sampler_r121.py`、`verify_java_gpu_samples_r121.py`。这里的相对路径均以 `F:/1FPGA/Xilinxprj/prj2/rasterix-linux` 为根。
