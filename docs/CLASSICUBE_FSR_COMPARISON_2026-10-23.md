# MC：FSR1 与插值放大实际对比

2026-10-23，在 AXU3EG 上运行现有 MC、FPGA 最近邻/双线性以及 A53 软件 FSR1。原始渲染 400×240 RGB565，输出 800×480，风格效果关闭。没有新增 FPGA FSR、神经超分、修改固件或替换默认入口。

## 本轮性能

三组分别从相同 64³ 世界、32 格视距、120 FPS CPU 提交上限和自动操作开始。世界哈希均为 3787233315；每组游戏限时 32 秒，等待测量开始后预热 1 秒，再记录约 20 秒的对比窗口。这是一次短测，没有做重复交叉统计或全地图流畅度验收。

|方案|执行位置|20 秒窗口原始帧提交 FPS|实际放大后新画面 FPS|
|---|---|---:|---:|
|最近邻 2×|FPGA|60.19|约 60.19|
|双线性 2×|FPGA|60.15|约 60.15|
|FSR1 EASU + RCAS|A53，FP32 四线程|60.14|**2.32**|

FSR 在 20.2576 秒内生成 47 帧，卷积风格网络未参与。FSR 下的原始游戏帧计数和 LCD 约 60 Hz 刷新都不能代替 2.32 FPS 的新画面生成速度。各组原生约 30 秒硬件窗口均值另为 58.43、58.29、58.34 FPS；与上述 20 秒窗口时间范围不同。

游戏停止后，对同一冻结输入各运行三次 A53 CPU 文件模式，计算中位数为最近邻 19.90 ms、双线性 26.59 ms、FSR1 184.11 ms。这三项都是 **CPU 参考计算时间**，不能将前两项当作 FPGA 插值耗时；FSR 的独立计算约 5.43 FPS 也不是游戏并行时的端到端帧率。

## 同帧图像与实际显示核对

本次新采集的 64³ 世界配对输入使用 SNP1 租约，源图 SHA256 为 `5e40c89a264d3526faea446f357bc0200139cc89ff27e3d4579b2e35737d5915`。FSR 输出保持显示时读取 6,000 个 LCD RGB565 采样，全部与完整 FSR 输出相符。

新帧和两张既有真实 32³ 地形帧，共三组、九张放大结果，均由同一输入分别执行三种算法。图片统一使用已有 CPU 适配器的 RGB565 归一化，排除三种滤波之间的源帧变化。主机最近邻/双线性与独立 NumPy 参考逐通道零差异；新采集帧的三种主机完整输出都与 A53 各三次输出 SHA256 相同；FSR 还与实际显示的完整输出 SHA256 一致，并由主机再次核对 6,000 点 LCD 零差异。

图中插值是共用输入归一化的 CPU 算法参考，不宣称它与 PL 的 RGB565 位复制扩展逐通道完全相同。主机与 A53 使用的 FSR1 是同一官方内核适配，RCAS sharpness 为 0.2；本轮没有修改内核或调节参数挑图。没有原生高分辨率真值、运动视频或人工画质验收，因此不提供 PSNR/SSIM，也不宣称解决运动闪烁。

- [新采集 MC：完整并排图与局部放大](../report/classicube-fsr-comparison-20261023/mc-live64/comparison.png)
- [新采集 MC：局部放大图](../report/classicube-fsr-comparison-20261023/mc-live64/crops.png)
- [开阔草地对比](../report/classicube-fsr-comparison-20261023/mc-terrain32-0/comparison.png)
- [水面与悬崖对比](../report/classicube-fsr-comparison-20261023/mc-terrain32-9/comparison.png)

观察这些静态图：双线性显著柔化纹理和像素图标；FSR 比双线性保留了更强的纹理与边缘对比，但会改变像素块形状，部分边缘出现锐化痕迹。最近邻对物品栏和像素纹理的保真更直接。不能将 FSR 的锐度等同于恢复了真实高分辨率细节。MC 后续采用 FSR 时宜单独保护 HUD，再检验移动场景；当前 A53 实现的 2.32 FPS 不适合作为默认游戏显示路径。

## 工程状态与复核

板端程序 SHA256 为 `ed7a643b0748fffaecdf5d0041a3ef19581dcbfa688b919df5b9978480376b1a`，与本地已构建 AArch64 程序相同；未替换它。主机通过现有纯色和斜边 FSR 自检。

测试完成后恢复了原 `options.txt` 内容和原后处理 mode 1，所有游戏与后处理子进程均结束，快照租约和超时计数为零。最终 GPU status=3，frame/swap/copy/presented/last_presented 均为 26755，读写、超时、欠载、扫描错误均为零。新增板端文件全部位于 `/tmp`，BOOT、设备树、既有模型和默认入口未修改。

证据：`report/classicube-fsr-comparison-20261023/comparison.json`、`board-result.json`；回读原包 `report/postproc_mc_fsr_compare_20261023.bin`，SHA256 `ef7f571785e35e2d3505b3497d48f30a97e760a1fc44ae63b2fc290f82e35806`。

板端实验脚本为 `linux/postproc/compare_mc_fsr.py`；主机同帧生成与核验脚本为 `scripts/compare_mc_fsr.py`。二者拒绝覆盖本轮已有证据，重复实验需要新的输出目录。官方原始代码及生成内核的追溯仍见 `report/fsr1_cpu_kernel_sources.json`。
