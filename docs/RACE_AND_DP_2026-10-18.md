# 模拟比赛与 DisplayPort 接入核对

2026-10-18，通过 COM11 登录当前 SD 系统，使用板上已有的 libX11 / libXtst 对 Tuxracer 窗口注入 `Return → p → Return`，进入 Practice 并启动 Frozen River。注入器在 `/tmp`，没有修改已部署游戏、模块或硬件。XTEST 验证的是软件输入路径，尚未覆盖实体 USB 键鼠及转向/刹车控制。

## 一局实际比赛

赛道加载、3D 比赛和正常终点统计均已从真实 GPU RGB565 颜色槽读回并核对 SHA256。该局自然下滑至终点，未发送中止按键。结果画面显示 `Race Over`、Time `02:05.36`、Herring `15`、Score `0`；匹配当前 ELF 摘要的只读进程状态也显示 `g_game.mode = GAME_OVER`、游戏时间 125.35918 秒。

![比赛中的实际 GPU 读回](../report/board_serial/race_running_readback.png)

![终点统计的实际 GPU 读回](../report/board_serial/race_finished_readback.png)

单独按硬件 `presented` 计数测量比赛中间窗口：88.6205 秒呈现 2664 帧，约 **30.0608 FPS**，89 次采样中读错、写错、超时、欠流和扫描错误均为 0。窗口来自启动按键后第 10～100 秒内的原有单调时钟采样；父进程采样原点用游戏子进程的 `/proc` 启动时间近似对齐，避开加载及终点过渡。屏幕 HUD 另显示约 95～106 FPS，不能用它替代硬件实际呈现率。

证据为 `report/race_session_2026-10-18.json`、`report/race_images_2026-10-18.json` 和 `report/board_serial/race_session_samples.jsonl`；采样 JSONL 已以 SHA256 回读校验。运行中截图来自 PS 固定颜色槽两次一致的只读拷贝，可能相对正在扫描的帧滞后一帧。比赛与终点图均由本次实际 GPU 像素生成，未使用 X11 dummy 窗口截图代替。

当前保留终点统计画面；此前启动器仍按原定最长 1800 秒退出，未安装开机自动运行。本次未完成 30 分钟稳定性验收，也没有确认修复后的 LCD 人眼观察结果。

## MiniDP 属于 PS

AXU3EG 用户手册第 35～36 页的 DP 接口说明：视频通道连接 ZU3EG BANK505 的 **PS MGT LANE2 / LANE3**，辅助通道和热插拔信号接 PS MIO。当前 PS 预设已启用 DisplayPort，Linux 5.4 配置包含 `CONFIG_DRM_XLNX=y`、`CONFIG_DRM_ZYNQMP_DPSUB=y`、`CONFIG_XILINX_DPDMA=y`。

板上实际存在 `card0-DP-1`，驱动链接为 `zynqmp-display`；本次查询连接状态为 `disconnected`，没有可用显示模式。原始结果见 `report/board_serial/com11_race_control_verified.log`。这证明当前内核已注册 DP 显示设备，物理显示器上的图像仍需接线后验证。

来源：[ALINX AXU3EG 官方用户手册](https://www.alinx.com/public/upload/file/AXU3EG_User_Manual.pdf)、[AMD ZynqMP DisplayPort Linux 驱动说明](https://xilinx-wiki.atlassian.net/wiki/spaces/A/pages/18842105/ZynqMP)。本地中文手册提取保存在 `report/vendor_axu3eg_manual.txt`。

## 后续游戏输出方案

可以保留 PL RasterIX 渲染，增加 PS 的显示后端，建议优先使用 DDR 帧缓冲路径：

```text
PL RasterIX → PS DDR RGB565 帧 → 转换/缩放到 DRM 帧缓冲
                              → PS DPDMA / DisplayPort → 外接显示器
```

AMD 的 PS DP 驱动支持 DPDMA 从内存帧缓冲输出。结合本项目已有 PS DDR 颜色槽，推断该路径可以先以软件拷贝实现，无需将板上的 DP 高速管脚改接到 PL。实现时需按驱动实际支持格式建立 DRM 双缓冲，协调 GPU 完成、CPU 拷贝和 KMS 换页；随后单独测量 CPU 开销与呈现率。现有 RGB LCD 路径已工作，可用于对照。

当前游戏仍只提交 PL LCD 显示，X11 dummy 只提供输入窗口；插入 DP 线不会自动把 RasterIX 游戏画面输出过去。下一阶段先接显示器读取 EDID/模式并验证 DRM 测试图，再接入游戏帧缓冲。若选择标准 1280×720 模式，可将 400×240 画面整数 3× 放大为 1200×720 并在左右各留 40 像素，保持当前 5:3 比例。显示模式最终以实际显示器提供的 EDID 为准。
