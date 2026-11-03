# RGB LCD 游戏界面比例修复

用户于 2026-10-18 确认 800×480 RGB LCD 已出现游戏画面，随后报告比例不对、画面没有完整铺开。已有 GPU 读回图同样显示启动 Logo 与底部文字被裁切，见 `report/board_serial/gpu_game_readback.png`。

## 原因与改动

硬件链路为 400×240 RGB565 → 2× 最近邻 → 800×480 LCD，三者均为 5:3。旧游戏代码却把 UI 布局也设为 400×240；启动画面四块固定 256×256 图案合成 512×512，菜单另有 460×310 的固定布局，因此无法放进旧画布。

现在区分游戏逻辑画布与 GPU 视口：

| 层次 | 尺寸 | 用途 |
|---|---|---|
| 游戏 UI / 投影 | 800×480 | 菜单布局、透视比例、鼠标坐标 |
| GPU / SDL 输入窗口 | 400×240 | 实际绘制、纹理与 DDR 开销 |
| PL RGB LCD | 800×480 | 横纵各重复两次，保持原有硬件时序 |

`winsys.cpp` 保持真实渲染尺寸，向游戏设置 800×480 逻辑分辨率；`render_util.c` 使用 400×240 GPU 视口。鼠标按钮、移动、键盘附带位置和指针移动均转换坐标。启动图四块拼图统一缩为 240×240，完整的 480×480 正方形居中显示；图案自身保留正方形比例，背景覆盖全屏。初始 options 文件同步为 800×480，已有 options 会被窗口初始化的固定配置覆盖分辨率。

实现来源为 `src/ps/rasterix_display_layout.h` 和 `scripts/prepare_sources.py`，完整补丁导出到 `patches/tuxracer-zynqmp.patch`。硬件 bitstream、BOOT.BIN、Linux DT 和 ABI 无需修改。

## 验证

- `report/display_layout.json`：原生 C 断言检查 5:3 比例、四块启动图全部边界和 640 个像素坐标往返；同时核对实际游戏入口、投影和输入连接，并绑定已有 PL 横纵 2× 仿真结果。
- `report/framebuffer_roles.json`：真实 Renderer 前后缓冲地址交替及 400×240 读回尺寸通过；旧 Renderer 的地址别名负向复现保留在报告中。
- `report/dma_initialization.json`：真实连接器、三片区、六个命令槽、独立资源槽、GL 初始化与旧 ABI 拒绝通过。
- `samples/rix_smoke.cpp` 增加四边白框和四角像素断言；板上 1000 帧测试及实际读回已确认完整四边框。
- AArch64 编译完成，27/27 本地发布检查通过；ext4 回读核对 188 个文件和 28 个运行 ELF。最终结果见 `report/release_manifest.json`，打包日志为 `report/lcd_layout_release_package_console.log`。

完整镜像为 `build/sdcard/AXU3EG_RasterIX_Linux_TuxRacer.img`，大小 1,610,612,736 字节，SHA256=`37ac5660b54c01cd280012e84fcf21db5869c3db1df723fa4956e85d44c8581f`；rootfs SHA256=`51577a5c02169af4d59ea9cbc9df83b55b2344d6d2d84009f4b7b1be60764436`。这两项是本地新文件的摘要，未据此认定实际 SD 卡内容已更新。

两个增量包也已放到 `build/sdcard/rasterix-userspace-20261018.tar.gz` 和 `build/sdcard/rasterix-dma-module-20261018.tar.gz`，分别约 721 KiB 和 100 KiB。两个游戏 ELF 保持 AArch64 架构并去除调试信息，内核模块保持完整原文件。程序包来源及部署文件摘要见 `report/framebuffer_userspace_bundle.json`，模块来源见 `report/dma_idle_close_build.json`。

## 上板结果与 SD 持久化

PS 串口最终确认为 COM11（115200、8N1、无流控），COM15 是 PL 串口。JTAG 软复位后通过内核缓冲确认 Linux 已启动，再重启 Windows 上的对应 CP210x 设备恢复串口登录，详见 [串口恢复记录](BOARD_RECOVERY_2026-10-18.md)。

新程序包和 DMA 模块包已通过串口上传，整包 SHA256 与电脑来源一致；证据为 `report/lcd_layout_userspace_serial_upload.json` 和 `report/lcd_layout_dma_serial_upload.json`。临时验证结果如下：

- `rix-smoke 1000` 退出码为 0，DDR TX/RX、三角形、深度、纹理、四角像素与换页断言通过。结束后双向 DMA IRQ 均保持 `0x00017003`，读错、写错、超时、欠流和扫描错误全部为 0。
- 新游戏启动画面运行 60.4376 秒，呈现 1797 帧，约 29.7332 FPS；61 次采样全部错误为 0。这只是启动画面性能，比赛及 30 分钟稳定性尚未验收。完整 JSONL 已按 SHA256 回读，见 `report/board_serial/lcd_layout_game_60s.jsonl`。
- 实际 GPU 像素读回图显示完整 Logo 和底部文字，背景覆盖整个 400×240 渲染区。该区经现有 PL 2× 链路输出 800×480；用户暂时无法观察修复后的 LCD，因此保留人眼确认这一项。

![修复后的实际 GPU 游戏像素读回](../report/board_serial/lcd_layout_game_readback.png)

![四边框和深度/纹理实际读回](../report/board_serial/lcd_layout_smoke_readback.png)

临时验证通过后，同分区硬链接保存旧文件，暂存新文件并 fsync，再原子替换以下三个 SD 根分区文件，逐个回读摘要：

| 文件 | 已部署 SHA256 |
|---|---|
| `/usr/bin/tuxracer` | `b11ab22988520e548de512e3869f5127c9fe2bc9138bd3c914e35557a715dc7c` |
| `/usr/bin/rix-smoke` | `dc9cdb2063df1b9d6a59a2841803b665a4248c0026a977105b01b8f382ae0b18` |
| `/opt/rasterix/modules/rix_dma_proxy.ko` | `e699073ec229208ab2e843ae45e3daa8814140fe281b33a629cdd9460bb8de80` |

旧文件及清单位于板上 `/opt/rasterix/rollback/20261018-lcd-layout`。执行 `sync; reboot` 后，FSBL、BL31、U-Boot 和 Linux 正常启动并进入登录提示，无需再次 JTAG 继续执行。三个永久文件摘要再次一致，临时上传目录已消失；从永久路径加载模块并运行 `rix-smoke 3` 再次通过、双向 DMA IRQ 保持开启。随后从 `/usr/bin/tuxracer` 启动游戏，`/proc/<pid>/exe` 路径与摘要均核对一致，保存的运行状态仍为 3、所有错误为 0。根分区剩余约 214.6 MiB。

本次实际 SD 按三文件增量更新，未重新写入本地完整镜像，不能将卡片认定为与新整卡镜像逐字节相同。部署及正常重启证据分别为 `report/runtime_promotion_2026-10-18.json`、`report/lcd_layout_board_tests_2026-10-18.json`，完整串口日志在 `report/board_serial/`。启动文件未改动；FAT 已重新挂载为只读，原有未正常卸载标记留待离线维护检查。

验收后已启动一次最长 1800 秒的游戏运行，未安装开机自动启动。下次需要运行时，在板上执行 `rasterix-run`。随后已用 X11 注入按键完成 Frozen River 一局练习赛，比赛中间窗口实测约 30.06 呈现 FPS，见 [比赛与 DP 记录](RACE_AND_DP_2026-10-18.md)。修复后 LCD 人眼确认、实体 USB 输入/操控和 30 分钟稳定性仍待验收。
