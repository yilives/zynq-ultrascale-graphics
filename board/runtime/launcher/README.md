# RasterIX 游戏库

2026-11-03：新增 v4 十五游戏库，加入 rRootage 和六款原生经典游戏，以及分页、搜索、收藏与最近启动。构建 `./build.ps1 -Action launcher` 输出独立 `build/launcher-v4-library/`；旧 v2/v3 及 CNN/FSR 包保留。[实现、来源和验收范围](../../docs/GAME_LIBRARY_V4_2026-11-03.md)，[TH06 SDL2 候选评估](../../docs/TH06_SDL2_FEASIBILITY_2026-11-03.md)。以下内容是旧 v3 的历史说明。

当前 LCD 后端已改为 **原生 800×480 POST 双缓冲**，不再把菜单抽样到 400×240，也不创建菜单 GL 上下文。LCD 小字至少 16 像素；实机两轮各 384,000 帧像素和 6,000 LCD 点比对通过，用户确认文字明显清楚。三游戏 FSR/返回/Java 恢复已回归。`./build.ps1 -Action launcher` 现在输出独立 `build/launcher-v3-native`，板上正常会话位于 `/tmp/rasterix-launcher-v3-native`；旧 v3 包保留。见 [最新使用与验证](../../docs/LCD_NATIVE_MENU_2026-11-01.md)。以下 v3 纹理后端记录作为历史说明。

v3 增加单命令 `session.py`、evdev `Ctrl+Alt+M` 返回监视器、可选的实验 LCD 呈现，以及“菜单进程正常退出后才能启动游戏”的交接。构建 `./build.ps1 -Action launcher` 输出 `build/launcher-v3`，复用已验收 v2 的同一 Java FSR 二进制。v2 原包和板上代码保留。

v3 已完成本地 48 项 UI、11 组会话／输入及 288,000 像素 GL 检查，并部署到板上 `/tmp/rasterix-launcher-v3b`。东方、ClassiCube、原版 Java 1.2.5 均通过正常入口、PL FSR、新鲜帧、内核虚拟键盘 Ctrl+Alt+M 返回和菜单恢复；Java 准备中取消另行通过。当前 LCD 留在不限时菜单，勿重复启动会话。

LCD 模式采用实测 400×240 的全屏 X11 输入窗口、实际尺寸坐标映射与软件指针、完整原子 CPU 菜单、独立 400×240 RasterIX 呈现和 PL 最近邻 LCD 输出。游戏中 FSR 为 PL EASU12＋RCAS5，退出菜单前恢复 Java 要求的 POST mode 1。XTEST 鼠标移动已对应到 LCD 内部采样；实体 USB 键鼠与 miniDP 未验收，DP 后端尚未实现。部署仍在 RAM，重启需恢复，没有安装 SD 自启动。见 [实现与使用](../../docs/GAME_LAUNCHER_SESSION_V3_2026-11-01.md) 和 [最终实机报告与截图](../../docs/GAME_LAUNCHER_V3_BOARD_FSR_2026-11-01.md)。

以下为 v2 的已验收游戏／FSR 接入与独立运行方法，仍适用于板上旧版本；其中关于全局返回和 LCD 适配器“尚未接入”的说明仅描述 v2。

SDL2 软件绘制的中文游戏库，适配 1920×1080 与 800×480。图像来自项目已有实机回读；菜单本身不打开 DMA、PL 寄存器或 DRM。字体在构建阶段栅格化，运行时无需字体库或浏览器。

v2 已验收产物保留在 `build/launcher-v2`：宿主程序、AArch64 程序、资源、八游戏适配器、Java FSR 运行器、预览和交互检查结果。当前 `./build.ps1 -Action launcher` 构建独立 v3；旧包和验收证据保留。构建依赖已有 SDK、SDL2、Java 客户端与 8e89 主线库。

在 WSL 中预览：

```sh
root=/mnt/f/1FPGA/Xilinxprj/prj2/rasterix-linux
"$root/build/launcher-v2/host/rix-launcher" --assets "$root/build/launcher-v2/assets"
```

可选的交互预览控制服务（不启动真实游戏）：

```sh
python3 "$root/linux/launcher/launcher_control.py" --socket /tmp/rix-menu-demo/control.sock serve
```

另一个终端启动 UI 时加 `--socket /tmp/rix-menu-demo/control.sock`。没有服务时仍可浏览和保存显示偏好，点击启动会说明未连接。

`--board` 是开发板执行模式，需要 root、原有受保护运行环境、当前启动的 v23 凭据与已校验 SD 缓存。统一适配器 `play_game.py` 支持全部八个固定 ID，包括东方、ClassiCube 和原版 Java 1.2.5。Java 还需要当前 RAM 中已校验的 JRE、客户端依赖和双 TMU／回滚位流，重新上电后需重新准备；本次没有安装开机自启动。

首页的 FPGA FSR 开关会保存并传给下一次启动；控制接口也支持 `START minecraft-java fsr`。FSR 为 PL EASU12＋RCAS5 定点实现，固定 400×240 → 800×480。CPU 管理帧所有权与调度，实时放大像素在 FPGA 计算。Java 使用独立的位流／源码／启动凭据，原 v23 FSR 程序与归档保留。

正常入口不限时、不注入输入。自动开局、短时验证和逐像素比对只在显式 QA 选项下启用。Java 普通入口只调用原版游戏并固定物理窗口尺寸，保留选定的原画质配置。退出顺序为排空 FSR、关闭游戏、释放设备句柄、恢复原 v23；无法确认 AXI 排空时拒绝继续切换。

```sh
app=/tmp/rasterix-launcher-v2e
nohup python3 "$app/launcher_control.py" --socket /tmp/rix-menu/control.sock --board serve > /tmp/rix-menu-control.log 2>&1 < /dev/null &
# 在同一串口继续；停止后再启动下一款。
python3 "$app/launcher_control.py" --socket /tmp/rix-menu/control.sock start touhou --fsr
python3 "$app/launcher_control.py" --socket /tmp/rix-menu/control.sock stop
```

方向键选择，Enter 启动，鼠标点选，Tab／Shift+Tab 切换控件，Esc 关闭提示或返回。跨游戏全局返回快捷键尚未接入；UI 当前仅在自身收到快捷键时发出 STOP。真实游戏仍可正常退出回到菜单，管理接口也支持 STOP。

`--snapshot FILE.bmp --headless` 离屏导出完整界面；`--page display|help` 选择页面，`--selected GAME` 选择游戏。`--frame-output` 是调试图像导出，不是已经接入 DP 的实时帧队列。

显示偏好保存目标设备与比例，首页 FSR 开关控制实际游戏适配器。软件菜单本身仍为离屏／X11 界面，尚未接到物理 DP/LCD 菜单呈现；游戏沿用 PL→LCD 路径。1080p 菜单预览与 800×480 FSR 不代表已经完成 miniDP 1080p60 扫描输出。实机记录见 `docs/GAME_LAUNCHER_GAMES_FSR_V2_2026-10-31.md`。
