# 当前采用的 Java 游戏配置

2026-10-30，按用户选择采用**原画质＋连续顶点直通**。

| 项目 | 当前选择 |
|---|---|
| 视距／图形／云 | Tiny／Fast／关闭 |
| AO／粒子／行走晃动 | 开启／全部／开启 |
| 原生分辨率／纹理上限 | 400×240／256×256 |
| 渲染 | ARM 几何前端＋PL RasterIX，双 TMU |
| 顶点直通 | 开启 |
| 呈现／FSR／CNN | 最近邻／关闭／关闭 |

选择位于 [主线配置](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/config/java_arm_mainline.json)，其中十二项实际设置与已验收的 R131 一致。

构建入口仍为 `./build.ps1 -Action arm`，输出为 [arm-mainline-r3](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/build/minecraft-java-125/arm-mainline-r3)。包内 `visual-settings.json` 和 `options-profile.txt` 保存所选画质；后者是用于合并的选项片段。库及位流保持原字节身份，所选直通模式的宿主几何回归通过。r1、r2 和全低试验证据保留。

板上 RAM 中的 `/tmp/rix-java125/home/.minecraft/options.txt` 已在 GPU 空闲、隔离守卫和原三把锁保护下更新。原文件已备份到 `/tmp/java-quality-selection-r133/original-options.txt`，其余选项保留；回读确认十二项值匹配。修改前后 GPU／POST 状态与恢复凭据一致，锁已释放，串口关闭。

板端采用证明：[board-adoption.json](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/report/minecraft-java-125/quality-selection-r133/board-adoption.json)，SHA256 `7792265385d0735c716b6b4f348e8647940588aed05b6428054166a6277ba38d`。

本次是配置采用，没有启动游戏或重新测帧率。SD、自启动、时钟、驱动 ABI、RTL 和 PL FSR 保留代码均未修改。RAM 选项会随重启清空；项目默认选择与 r3 包保存在电脑工程中。

2026-10-31 开发板重启后，已恢复 RAM 运行环境并完成独立的 R134 阶段诊断，诊断库没有推广到项目主线。R136 随后重新应用上述十二项原画质选项，回读确认匹配，其余选项保留；GPU／POST 空闲状态未变化，锁与串口均已释放。新采用证明：[board-adoption.json](F:/1FPGA/Xilinxprj/prj2/rasterix-linux/report/minecraft-java-125/quality-selection-r136/board-adoption.json)。
