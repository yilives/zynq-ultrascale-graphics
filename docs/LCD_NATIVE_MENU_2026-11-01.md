# LCD 菜单原生分辨率修复

2026-11-01。**菜单已更新到开发板，用户确认“文字已明显清楚”。** 当前运行 `/tmp/rasterix-launcher-v3-native` 的不限时会话，八个游戏入口就绪。

## 原因和修改

旧菜单虽然生成 800×480 图像，却先取每个 2×2 块的一个像素，变成 400×240，再经 RasterIX 和最近邻放大回 800×480。12 像素小字只剩约 6 像素高，抗锯齿笔画也被抽掉。FSR 开关只作用于游戏，无法修复菜单。

新链路为：

```text
ARM SDL 完整 800×480 菜单
  → RGB565 精确展开为 XRGB8888
  → 现有 PL DDR 的非活动原生帧缓冲
  → 等待 POST mode 2 换帧确认
  → 800×480 RGB LCD
```

- 菜单不再经过 400×240 重采样，也不创建 RasterIX GL 上下文。
- LCD 模式的小字至少使用 16 像素字形，说明文字颜色加深；1:1 输出直接复制，避免额外线性缩放。
- X11 输入窗口仍为 400×240，鼠标按实际窗口尺寸映射到完整菜单；输入尺寸和 LCD 输出尺寸分开处理。
- 只写非活动双缓冲；有序 Device 存储及 `dsb sy` 完成后才发布。上一帧未确认时拒绝复用缓冲。
- 继续持有原三把资源锁。退出前确认 POST 恢复 mode 1，父控制器观察到子进程正常退出后才启动游戏。

复用了已有原生显示通路，**没有修改位流、设备树、游戏画质、FSR 算术、SD 启动文件或开机服务**。Java 双 TMU 配置切换和原 v23 恢复流程保留。

## 图像对照

左图是同一完整 CPU 帧经过旧抽样链路的数值重建；右图来自本轮实际原生 DDR 完成帧回读。左图不是另一次现场拍摄，两图均未使用相机。

![同一菜单帧的抽样与原生输出对照](assets/launcher-native/menu-sampling-comparison.png)

![本轮实际原生菜单完成帧](assets/launcher-native/menu-native.png)

## 验证

| 范围 | 结果 |
|---|---|
| 宿主像素打包 | 384,000 像素精确比对，包含全部 65,536 种 RGB565 值，前后保护区不变 |
| 缓冲协议 | 非活动槽写入、发布前顺序、ACK、恢复，以及 8 项错误/超时拒绝检查通过 |
| UI 与会话 | 48 项 UI、11 组会话/输入检查通过；原纹理适配器的历史 GL 检查保留 |
| 实机 smoke 与 cycle | 两次各 384,000 个原生帧像素、6,000 个 LCD 独立采样点完全一致 |
| 菜单释放 | 6 个菜单呈现进程均正常退出，POST 恢复 mode 1 |
| 三游戏 | 东方、ClassiCube、Java 1.2.5 的正常入口、PL FSR 新帧、evdev 返回和菜单恢复通过 |
| Java 准备中取消 | 未创建原生 Java，原 PL 正常恢复 |
| 当前显示 | mode 2 原生菜单活动、八入口 ready、GPU 五项错误和快照过期计数均为 0 |
| 人眼观察 | 用户确认中文明显清楚；实体 USB 键鼠与 miniDP 未验收 |

三游戏使用普通不限时入口，测试器通过内核虚拟键盘发出返回。本轮未再次进行 FSR 的独立全帧算术金值验证；FSR 程序和游戏渲染代码沿用已验收版本。

独立证据：[acceptance.json](../report/launcher-native-20261101/acceptance.json)。CPU/UART 归档共 **70 个文件**逐一核验，480,463 字节，SHA256 `fa4164586404d1a8f6c50fb436dc6b3f448bd26cf7d67679aecb655b4f3b2a66`。3 个游戏 FSR 完整末帧及部分重复大文件未放入该运输包，文件名/大小/摘要另存于归档的 `omitted-large-artifacts.json`，不冒充这些文件已完整回读。

## 构建、使用与回退

```powershell
./build.ps1 -Action launcher
```

当前产物目录改为 `build/launcher-v3-native`，不会覆盖已验收的 `build/launcher-v3`。包内仍沿用 v3 安装协议和目录前缀。

最终包 `build/launcher-v3-native/rasterix-launcher-v3.tar.gz`：**4,271,276 字节**，SHA256：

```text
b6d8f0c5b8c54818db315147e555694baf050e518d9ea0c38c5e7305dacd9174
```

当前会话已经运行，勿再启动第二套。正常停止并确认释放后，可再次运行：

```sh
python3 -B /tmp/rasterix-launcher-v3-native/session.py --board --lcd-menu
```

方向键/鼠标选择，Enter 启动，游戏中 Ctrl+Alt+M 返回。首页 FSR 开关保存的是下一次游戏启动偏好；浏览菜单时没有运行 FSR 或 CNN。

旧 `/tmp/rasterix-launcher-v3b` 和原包 SHA256 `791f351536bb1e2791107b12f5bddda71f1bb7af335521b98b870b7c99ea0ddc` 保留。需要回退时先正常停止新会话，确认资源释放，再使用旧入口。仍为 RAM 部署，重启需恢复运行环境；miniDP 物理输出和 CNN 串联未在本轮加入。

CNN 本轮离线探索见 [风格质量试验](CNN_STYLE_V6_EXPLORATION_2026-11-01.md)。
