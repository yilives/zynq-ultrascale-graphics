# AXU3EG ClassiCube / RasterIX 移植

后续键鼠版已修正客户区被 Matchbox 压缩的问题，补齐菜单指针、布局、文件名输入和正常退出。当前使用入口与实测见 [键鼠版说明](CLASSICUBE_KEYBOARD_2026-10-21.md)。本页 v4 性能保留为历史基线。

本轮将 ClassiCube 1.3.8 接入现有 AXU3EG Linux + RasterIX 镜像。它提供类似 Minecraft Classic 的方块世界、移动跳跃、挖掘、放置和 `.cw` 地图存档；它是 Classic 创造玩法客户端，不能视为 Minecraft Java 生存版或现代版本的直接移植。

## 使用

在开发板 PS 串口 COM11（115200，8N1，无流控）进入 Linux 后执行：

```sh
rix-classicube --seconds 1800
```

默认生成 64×64×64 地图，种子 314159，视距 32 格。内部绘制为 400×240，FPGA 最近邻放大至 LCD 全屏 800×480，保持像素边缘。可以选择较小地图或视距：

```sh
rix-classicube --world-size 32 --view-distance 16 --seconds 1800
rix-classicube --map /opt/rasterix/classicube/profile/maps/cc_gameplay_v4.cw --seconds 1800
```

USB 键鼠由 SDL2 / X11 接收，标准操作为 WASD 移动、空格跳跃、鼠标转向、左键挖掘、右键放置、数字键选择方块、B 打开方块栏、Esc 打开菜单。板测自动输入通过原引擎输入与拾取处理函数完成；本轮没有人工验证 USB 键鼠手感，也没有增加 ClassiCube 专用触摸摇杆。串口只用于启动和诊断，不直接充当第一人称鼠标。

正常菜单可存档；诊断测试另外自动生成了上述 `.cw`。退出可用游戏菜单或向启动器发送 SIGTERM / Ctrl+C。自动测量用 `--autoplay`，完整挖掘/放置/存档测试需 `--autoplay --gameplay-qa --flat --world-size 32 --seconds 14 --capture`。后者暂时关闭方块物理以便精确校验存档，退出后恢复原设置。普通游戏不执行这些自动操作。

## 实际渲染链路

```text
ARM A53: ClassiCube 世界/物理/输入、区块网格和可见性剔除
  → ARM: 固定功能 GL1/VBO，RasterIX 顶点处理/裁剪/三角形设置
  → AXI DMA: 绘制命令和纹理
  → FPGA RasterIX: 三角形光栅、纹理采样、深度、混合/雾
  → PL DDR 帧缓冲 → FPGA 帧复制/最近邻 2 倍放大 → RGB LCD
```

这是 ARM 游戏逻辑和顶点前端 + FPGA 像素渲染。顶点变换仍在 ARM，并非整条几何流水线全部硬件化。入口会暂时选择最近邻、关闭配色特效，并在游戏退出后恢复之前的后处理模式。本轮没有将 CNN 或 FSR 叠加到 ClassiCube。

本轮复用已有 bitstream，没有新增 FPGA 资源，也没有改动 BOOT.BIN、DTB、CNN 模型或其他游戏的私有 GL 运行库。本版构建关闭了音效和音乐。

## 适配与性能优化

- 固定源码 `33891a4e7e586941240261bc911312f228be57d3`，保留原始源码于 `external/classicube`，补丁在 `patches/classicube-axu3eg.patch`；WSL 单独准备构建副本。
- 使用 GL1 VBO 后端，按实际可用函数初始化；不启用依赖显示列表的 GL11 后端，也不伪造 OpenGL 版本。
- 当前硬件最大纹理为 128×128。地形沿用引擎分页，16×16 方块纹理分为 16×128 页面；部分较大的 GUI/皮肤纹理等比缩小。很长的菜单/调试文字还有清晰度限制，默认关闭帧率 HUD，精确帧率保存在诊断结果中。
- 默认索引缓冲的 `012/230` 方块面可改为 `GL_QUADS` 的等价 `012/023` 三角形，每个面提交 4 个顶点，减少重复顶点处理。仅 RasterIX 且使用默认索引缓冲时启用；自定义索引保留原逻辑。`--triangles` 可切回原始提交路径做同一程序的对照。
- 复用现有私有 SDL2/GLX 运行库、公共游戏锁、GPU 故障隔离和呈现计数，不替换其他游戏运行库。
- 原始地形与 GUI 素材来自官方 `default.zip`，保持下载字节，文件 SHA256 见包清单。CPU 缩小只发生于解码后的纹理。

## 验证方法和证据

硬件 FPS 取 `/dev/plgpu_display` 的实际 `presented` 增量，预热两秒后计时。软件提交数和游戏 HUD 不能作为 LCD 实际帧率。短测是固定种子、按墙钟时间转向/移动的代表场景，长测另外运行 62 秒；视角、可见方块数量会影响性能，单次场景不代表全部地图。

自动交互使用真实引擎 `Input_SetPressed`、射线拾取和方块操作；存档由引擎 `Cw_Save` 写入。主机独立解压 gzip / 解析 NBT，检查全部 BlockArray，再比较保存前和重载后的 FNV1a32。

| 场景 | LCD 实际 FPS | 测量窗口 |
| --- | ---: | --- |
| 32×64×32 平地，自动挖掘/放置 | 60.04 | 12.01 秒 |
| 64×64×64 真实地形，32 格视距，原三角形路径 | 44.63 | 16.00 秒 |
| 相同配置/路线，四边形路径 | 49.72 | 16.01 秒 |
| 原三角形路径，连续运行 62 秒 | 37.67 | 预热后 60.01 秒 |
| 四边形路径，连续运行 62 秒 | 41.96 | 预热后 60.01 秒 |

同一可执行文件的短测和 62 秒长测均提升约 **11.4%**，默认保留 32 格视距和四边形路径。连续路线后来进入更复杂的视角，因此单列长测结果。各项游戏调用正常退出，重复启动被公共锁拒绝，随后既有 `rix-games glx-probe` 也正常运行。静止存档场景两条提交路径的 96,000 像素中有 1 像素不同，最大单通道差 17；逐项结果见 `primitive-pixels.json`，不声称两路径图像完全逐位相同。

截图从正常呈现后的 front 缓冲以 `GL_RGBA/GL_UNSIGNED_BYTE` 读回，转换 OpenGL 行方向后保存 PPM；LCD 另由硬件诊断器在 800×480 输出端每隔 8 像素采样，独立比对全部 6,000 点。前两版截图用不支持的 RGB 格式得到黑图，保留了失败证据，不作为画面验收。第三版修复后四组画面采样均为零差异；第四版的交互、两次重载、两条地形路径及正常重启六组共 36,000 点也全部一致。

正常重启后 boot ID 已变化，两个 `/tmp` 程序缓存均确认为空；正式入口重新解压、核验源码包内的运行文件和素材并进入地图，之前保存的地图仍在。重启后同样无 GPU / DMA / LCD 错误，无残留游戏进程、快照租约或超时，原有 CNN 全部安装文件校验值一致。

![四边形路径的板上 GPU 原图，LCD 采样核验通过](../report/classicube/cc_terrain_quad_v4/lcd_reference.png)

本页历史数据见 [v4 验收清单](../report/classicube/v4/acceptance.json)；各项原始日志、原图、LCD 采样、结果在 `report/classicube/cc_*`。首版缺失截图的诊断隔离记录已单独归档，最终通过版本不据此忽略硬件错误。

## 本地构建与无网络部署

在项目根目录 PowerShell 运行：

```powershell
.\build.ps1 -Action classicube
```

需要既有 WSL Ubuntu、项目内 `build/sdk-2020.1` AArch64 SDK，以及已构建的 `build/game-ports/runtime` 私有 SDL2/GLX 依赖。脚本下载/校验固定源码及素材，生成 AArch64 可执行文件与带逐文件 SHA256 的 `build/game-ports/packages/classicube.tar.gz`；不构建或烧录 FPGA。

对已安装本工程 Linux 和公共游戏运行库的开发板，可使用现有 JTAG + PS 串口传输：

```powershell
.\tmp\transfer_port_package.ps1 -Package classicube
.\scripts\push_board_file.ps1 -LocalFile linux/classicube/install.py -RemoteFile /tmp/install_classicube.py
```

然后在板上执行 `python3 /tmp/install_classicube.py`。传输和安装均验 SHA256；传输保持根分区至少 32 MiB 余量。旧的已验证 ClassiCube 包会归档到 SD 启动分区 `rasterix-classicube-cache-archive-20261021/`。原启动文件不参与此更新。

入口持久安装在 `/usr/bin/rix-classicube`，用户配置和地图在 `/opt/rasterix/classicube/profile/`。程序和素材每次启动从已验证持久缓存解压到 tmpfs，避免占满根分区；素材软链接会在启动时重建，因此不依赖上次启动的 `/tmp` 内容。

主机验收示例：

```powershell
python scripts/verify_classicube.py cc_gameplay_v4 cc_reload_tri_v4 cc_reload_quad_v4 cc_terrain_tri_v4 cc_terrain_quad_v4 --save cc_gameplay_v4 cc_reload_quad_v4
```

原始程序遵循 ClassiCube 自带许可证；素材仍归各自版权人所有。上游：[ClassiCube](https://github.com/ClassiCube/ClassiCube)，[官方素材](https://static.classicube.net/default.zip)。本轮交付独立软件包，不重新生成整卡 `.img`。
