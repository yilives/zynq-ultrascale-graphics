# CNN 细节融合与实际优化取舍（2026-11-02）

后续已完成 [CNN＋400×240 细节融合＋PL FSR 串联](CNN_FSR_INTEGRATION_2026-11-02.md)。本页保留此前未接 FSR 的 800×480 ARM 融合对照，其数据不包含后续 FSR 阶段。

在已通过验证的 v8 较强漫画/版画、油画 CNN 后加入同帧亮度细节，减轻 160×96 风格图直接五倍放大的模糊。**CNN 的三层 INT8 卷积继续由 FPGA 执行，新融合由 ARM 执行，最后提交原生 800×480 显示缓冲。** 不增加 FPGA 算子或资源，不修改模型、旧位流、FSR 与 SD 启动文件。

本轮采用首版融合 r1。对另外两种加速候选作了同板、同频率实测，均未提速，保留为实验材料。

## 实际效果

![板上同帧数据重建](../report/neural-style/detail-r1/board-comparison.png)

左列是受保护快照的 400×240 源图，中列是对同一 CNN 输出作五倍双线性放大，右列是已实际提交给 LCD 的 ARM 细节融合结果。每行三列对应同一输入；不同风格来自各自运行的末帧。图片为回读数据重建并缩略排版，非屏幕拍摄。右列的文字、地面细线比中列清楚；艺术效果仍待人工评价。

![ClassiCube 与 Neverputt 离线完整整数参考](../report/neural-style/detail-r1/offline-comparison.png)

第二张是既有 ClassiCube 与 Neverputt 数据的同帧本地比较；这两个游戏未在本轮连续上板测试，不能把离线比较解释成它们的实机帧率。

## 算法与链路

```text
ARM 游戏逻辑/几何前端 → RasterIX PL 光栅化 → 400×240 源帧
→ ARM 持有快照并缩小到 160×96
→ PL v8 三层 INT8 CNN
→ ARM 五倍插值 + 同一源帧的亮度细节 → 写 800×480 缓冲
→ PL 原生扫描 → RGB LCD
```

令 `C` 为 CNN 输出五倍插值结果，`L` 为 CNN 输入的同规则插值结果，`S` 为 400×240 源图按二倍复制到屏幕的结果。计算：

```text
d = round_away((77×(S.r−L.r) + 150×(S.g−L.g) + 29×(S.b−L.b)) / 256)
correction = round_away(clamp(d, −48, 48) × gain / 256)
output.rgb = clamp(C.rgb + correction, 0, 255)
```

默认 `gain=192`，即 0.75，单通道变化不超过 36 级；三通道加入同一个亮度修正量。未发生饱和的像素保持 CNN 输出的通道间差值，保留其色调变化。所有输入、CNN 输出及源图按同一快照帧配对。显式保护矩形可以保留原图区域，未实现自动 HUD 检测。

网络仍为 **3→8→8→3，三层 3×3、160×96、INT8、1027 参数**，漫画与油画都使用 v8 已验收权重。新融合不是学习型超分，也不是新增风格网络。当前实验关闭 FSR，CNN 与 FSR 尚未串联。

## 实机吞吐与代价

同一次 Linux 启动、同一 NGR1 位流、同一 Neverball Level00 介绍场景。漫画按原路径/融合/融合/原路径的 ABBA 顺序，每轮 8 秒；油画另作两次兼容与呈现检查。

| 项目 | 纯 CNN 五倍放大 | CNN＋亮度细节 |
|---|---:|---:|
| 漫画两轮呈现 FPS | 24.8335 / 24.8740 | 24.6864 / 24.7762 |
| 漫画按帧数/总时长汇总 | 24.8538 | 24.7313 |
| 油画单轮呈现 FPS | 24.9321 | 24.6529 |
| 每帧 CNN 推理 | 约 9.3 ms | 约 9.3 ms |
| 漫画每帧合成 | 约 0.071 ms（低分辨率打包） | 约 13.80 ms |
| 漫画每帧显示写回 | 约 0.306 ms | 约 7.89 ms |

漫画 ABBA 吞吐变化约 **−0.49%**，本场景基本持平；没有测得游戏 FPS 提升。原路径只写 61,440 字节，融合路径写 1,536,000 字节，增加了 ARM 计算和传输开销。当前场景的源帧供给约为 25 FPS，等待时间吸收了部分新增处理时间；不能由这组结果推断高帧率游戏也无代价。

三次融合末帧上，相对原始亮度梯度的误差分别减少约 51.54%、51.69%、58.58%。这只是这些图上的亮度边缘指标，不是艺术画质提升百分比，也不代表真实运动闪烁评价。

六轮共呈现 **1195 帧**，其中融合路径 **595 帧**。GPU 读写错误、超时、下溢、扫描错误、快照过期均为零，游戏和后处理正常退出，随后原 FPGA 与清晰菜单恢复。

## 两种未采用的提速尝试

额外对照只运行 ARM 微基准，不重新编程 FPGA。四轮顺序均为 r1/候选/候选/r1；CPU 始终为 **1066666 kHz**。

| 候选 | r1 两轮 ms/帧 | 候选两轮 ms/帧 | 处理 |
|---|---:|---:|---|
| r2：分通道连续缓存＋预计算源图亮度 | 14.7099 / 14.6564 | 18.1568 / 16.1712 | 更慢，未采用 |
| r3：相同 r1 源码，A53 调度＋循环展开 | 14.6535 / 14.6866 | 14.8767 / 14.8519 | 无收益，未采用 |

两种候选均通过 129264 项直接插值/舍入/饱和/保护矩形检查，以及四幅完整 800×480 参考图核对；r3 另通过四组 AArch64 CPU CNN 黄金输出。正确性通过与性能提升分开判断，没有把候选编译成功计为优化成功。

r2 额外使用约 192,000 字节 ARM 内存缓存，不占 PL BRAM；其源码与二进制作为对照保留，不进入推荐入口。下一处有明确代价的是融合约 13.8 ms 和整帧写回约 7.9 ms，转到 PL 流式处理值得独立设计与资源核算；本轮没有实施或宣称这部分硬件化。

## 像素核对与证据

- 首版主机直接四邻点整数参考共 129264 项检查；四幅 800×480 图与独立 NumPy 参考逐像素一致。
- A53 NEON 同样通过 129264 项检查和四幅整图摘要，覆盖 **1,536,000 个参考像素**。
- 六次实际显示末帧的 FPGA CNN 共核对 **737,280 个 INT8 值**。三次融合输入还从所保存的完整 RGB565 源图独立重算缩小结果，验证源图、输入与输出配对。
- 主机独立计算六幅显示结果，共 **2,304,000 像素**，与板上生成的整图 SHA256 一致。
- 运行时完整回读显示缓冲并与待显示数组比较，合计检查 **4,792,320 字节 PL DDR**。主机收到纯 CNN 的原生低分辨率缓冲及完整显示参考摘要；融合路径的完整 DDR 比较由已固定源码的运行时在板内执行。
- 六次真实 LCD 采样共 **36,000 个 RGB565 点**均一致；没有物理 LCD 的全像素抓取。

完整验收：[首版独立验收](../report/neural-style/detail-r1/acceptance.json)、[r2 对照与未采用原因](../report/neural-style/detail-r2/acceptance.json)、[r3 对照与未采用原因](../report/neural-style/detail-r3/acceptance.json)。

原始证据：[evidence.tar.gz](../report/neural-style/detail-r1/evidence.tar.gz)，782696 字节，SHA256 `055ea441303cc7457cf36aaedd486b8a31be506b1695d161ee5e9e503f370143`。

## 使用与资源

独立运行时：`build/neural-style/detail-r1/runtime/rix-neural-detail`。新增参数为 `--composition neural-detail --detail-gain 192`，原 `neural` 和 `mc-residual` 路径保留。算法源码为 `linux/neural_style/experimental/detail_r1/luma_detail.hpp`；像素测试与构建入口在同目录及 `scripts/build_cnn_detail_runtime_r1.sh`。

位流继续使用已路由的 NGR1，**65058 LUT、71711 FF、189.5 BRAM、325 DSP**，CNN 核心周期为 462816。没有重新综合或增加硬件；Vivado 工程仍是 `build/vcgr1/rix_cgr1.xpr`。旧网络、FSR 代码、位流和原生菜单保留。

基础叠加包：`build/neural-style/detail-r1/board/rix-cnn-detail-r1.tar.gz`，380011 字节，SHA256 `862ef69a52cba807d4f1c9d0cc84f070dc7cc40b5ecb8544ec67e93c5966489f`。它依赖既有 NGR1 RAM 基包，不写 SD 或设为开机默认。

仅显示融合结果的演示入口位于 RAM：

```sh
python3 /tmp/rix-cnn-group-r1/detail_demo.py --style comic --seconds 30
python3 /tmp/rix-cnn-group-r1/detail_demo.py --style oil --seconds 30
```

入口校验文件、正常停止菜单、临时加载 NGR1、运行游戏与融合，结束后恢复原位流和清晰菜单。普通游戏选择 GUI 尚未加入这个开关。演示附加包为 `build/neural-style/detail-r1/demo/rix-cnn-detail-demo.tar.gz`；完整 ABBA 入口 `detail_r1_demo.py` 继续保留作复测。

只显示融合结果的入口又以漫画版 6 秒完成生命周期复测：149 帧、24.6484 FPS，正常恢复原位流与菜单。最终只读检查确认 SD 的 BOOT.BIN、system.dtb 与原稳定版哈希一致；推荐运行时与全部冻结输入文件的哈希通过。[最终验收](../report/neural-style/detail-r1/acceptance-final.json)。本轮没有改变普通菜单的默认画面处理方式。
