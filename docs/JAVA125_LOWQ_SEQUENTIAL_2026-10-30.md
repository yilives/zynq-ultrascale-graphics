# Java 1.2.5：全低画质＋顶点直通实测

2026-10-30。本次全低＋直通两轮为 **26.3633、26.4868 FPS**，加权 **26.4251 FPS**。同组原画质＋直通加权 **24.9424 FPS**，观测差 **+5.94%**。原画质对照自身波动较大，不能据此认定稳定提速。

这是新的一组 ABBA，不能把它与此前缓存开启的全低结果或旧 25.38 FPS 混算。没有达到稳定 32／60 FPS。

## 实际设置

两组都固定顶点直通为 1、ARM 几何前端＋PL RasterIX、400×240、完整 256 纹理、实际 Tiny／Fast／关闭云、和平、最近邻，不启用 FSR／CNN。共享库仍为 `8e89…`，双 TMU 位流仍为 `14fd…`。

| 设置 | 原画质对照 | 全低 |
|---|---|---|
| AO | 开启 | 关闭 |
| 粒子 | 全部（0） | 最少（2） |
| 行走晃动 | 开启 | 关闭 |
| Advanced OpenGL／红蓝立体 | 关闭 | 关闭 |
| FOV／Gamma／fpsLimit | 0／0／1 | 相同 |

每轮从游戏对象读取十二项实际设置，预热、正式开始和结束均检查；原始选项在结束后恢复。这里“全低”指上述画质选项，分辨率和纹理没有进一步降低。

## 四轮实测

| 轮次 | 画质 | 完成帧 | 实际窗口 s | FPS | 命令拍／完成帧 | DMA 等待比 | 整场条带溢出 |
|---|---|---:|---:|---:|---:|---:|---:|
| R128 | 原画质 | 735 | 30.9842 | 23.7217 | 354,123 | 28.72% | 6 |
| R129 | 全低 | 791 | 30.0038 | 26.3633 | 320,746 | 29.88% | 0 |
| R130 | 全低 | 795 | 30.0150 | 26.4868 | 320,379 | 29.99% | 0 |
| R131 | 原画质 | 786 | 29.9962 | 26.2034 | 321,492 | 29.65% | 0 |

原画质两个结果为 23.7217、26.2034 FPS，相差 2.4816 FPS；两组加权均值差为 1.4826 FPS。
原画质自身波动大于组均值差，不能把观测差全部归因于降低画质；组合的实际帧率范围比单一提速百分比更值得采用。

同为原画质，R128 每帧命令量比 R131 高约 10.15%；R128 的整场条带溢出为 6 次，其余三轮均为 0。R128 是通过验收的有效运行，完整保留在均值中。溢出次数是整场累计，不能直接归入中间测量窗口；额外负载的触发原因尚未定位。

每轮预热 60 秒，正式窗口约 30 秒。FPS 为硬件 `presented` 增量除以配对单调时钟时间，加权值按完成帧总和除以实际秒数总和，不取最好一轮。

![正式完成帧与命令量](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/docs/assets/java-lowq-direct-r127/comparison.png)

四轮均通过独立验收：同一启动、同一库和位流，原版 JAR 与冻结存档源未变，最终玩家位置／朝向一致、生命值 20；每轮 48 张原生测试图跨轮比较 55,296,000 字节完全一致。游戏截图允许存在预期的画质差异。

![四轮实际画面](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/docs/assets/java-lowq-direct-r127/world-frames-comparison.png)

![正式窗口内部约1秒GPU计数](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/docs/assets/java-lowq-direct-r127/gpu-timeline.png)

## 解释与边界

两种画质均保留全部有效轮次。静止平地场景、每种两次短测不能替代跑图或逐帧延迟测试；动画、实体、JIT 和命令量仍可能变化。相同截图也不能证明整个窗口负载相同。约 1 秒曲线不是逐帧 P95／P99；DMA 等待不是独占光栅时间。

本次只完成组合测试，没有自动推广全低画质。r2 主线仍采用直通开关，SD、自启动、时钟、驱动 ABI 和 RTL 均未改变。原 PL FSR 代码与保留归档未改。

## 证据与恢复

- 全部回读：`report/minecraft-java-125/pl-lowq-direct-r128-r131-readback.bin`，SHA256 `67a7354856cdb413afa92fa896bc62b550031103d34bdb4af29a3163998b18d6`。
- 每轮完整证据与独立验收：`report/minecraft-java-125/swap-fence/` 中 R128～R131。
- 汇总：`report/minecraft-java-125/swap-fence/lowq-direct-r127-comparison/summary.json`。
- 最终核验：`report/minecraft-java-125/lowq-direct-r127-evidence/final-verification.json`，绑定本轮回读、实际守卫状态、源码与新串口日志。
- 运行脚本：`scripts/run_java_lowq_direct_r127.ps1`；图表：`scripts/plot_java_lowq_direct_r127.py`。PNG／SVG 均由已验收数据生成。
- Windows／POSIX 每轮各 9 项故障检查通过；GPU 采样使用已验证的相同只读采样器。
- 最终原 v23 凭据有效，GPU 空闲、错误及帧计数为 0，POST 恢复 mode 1，无快照过期；接收器退出、锁释放、串口关闭。
- CPU 结束读数：{'scaling_cur_freq': '1066666', 'scaling_governor': 'userspace', 'cpuinfo_cur_freq': '1066666'}。这是时点读数，不是全程频率／温度记录。

以上相对路径均以 `F:/1FPGA/Xilinxprj/prj2/rasterix-linux` 为根。
