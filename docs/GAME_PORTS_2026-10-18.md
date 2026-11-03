# AXU3EG 追加游戏移植记录（2026-10-18）

本页保留 10 月 18 日的历史版本与测试结果。10 月 19 日已更新六平面裁剪、顶点缓存、Neverputt 完整球场、持久配置和统一入口；当前交付状态见 [五游戏优化记录](GAME_OPTIMIZATION_2026-10-19.md)。

目标是 Neverball / Neverputt、Quake III、Quake I 三组。各组源码均已交叉编译，板测结果按实际关卡与图像证据分别记录；菜单刷新不等于关卡通过。

## 构建与来源

源码锁定记录在 `config/game_ports_sources.json`，下载器为 `scripts/fetch_game_ports.py`，保留原始源码和许可证。WSL Ubuntu 使用资料盘 PetaLinux 2020.1 AArch64 SDK，编译目录 `/var/tmp/rix-game-ports`。先准备现有项目 SDK 和 target-deps，再运行：

```bash
python3 scripts/fetch_game_ports.py
bash scripts/build_port_graphics.sh
bash scripts/build_game_port.sh neverball
bash scripts/build_neverball_maps.sh
bash scripts/build_game_port.sh quakespasm
bash scripts/build_game_port.sh quake3e
bash scripts/build_quake3_game.sh
bash scripts/package_game_runtime.sh
```

素材另用 Windows Python 执行 `scripts/fetch_game_demo_assets.py`、`scripts/extract_game_demo_assets.py`、`scripts/package_port_assets.py`。提取器使用已安装的 7-Zip，地图构建需在前面完成。

原系统 SDL2 没有启用 OpenGL，因此为新游戏另建 SDL2 GLX 和 RasterIX libGL。SDL2_ttf 使用自带 Freetype/HarfBuzz。运行库独立安装在实验目录，不替换现有 Tux Racer 或系统库。

Neverball 地图生成器在 WSL 主机编译，需要主机 libjpeg / libpng 开发包；目标游戏仍使用 AArch64 库。地图全部生成后，实验素材包只选入 Neverball 三个入门关卡和 Neverputt 原始 18 洞，以及所需公共素材。

Quake I 使用 Quakespasm 0.93.2 的固定管线，禁用 GLSL、VBO、多纹理、声音，限制纹理 128×128。共享版未填充 cmdline cvar，补丁回退到原始命令行使 `+map e1m1` 生效；保留原注册检查。光照图集从 256×256 改为 128×128，使图集分配和 UV 使用相同尺寸。

Quake III 使用 RasterIX 作者的 Quake3e。旧 Demo UI API 为 3，与当前引擎不匹配，因此从固定 ioquake3 源码编译 AArch64 UI / cgame / qagame 模块，使用引擎原生模块接口。原始 Demo pak 不修改。

## 图形兼容调整

- GLX 为 SDL 输入窗口选择 Xorg 默认 24 位 visual；物理渲染仍为 400×240 RGB565，经现有 PL 显示链路放大到 800×480 LCD。
- stencil 能力报告为 0，与当前硬件一致。
- 为已实现的 VBO 核心函数登记 ABI 相同的 ARB 名称。
- 修复实验 libGL 的独立 ARRAY_BUFFER / ELEMENT_ARRAY_BUFFER 绑定，上传、查询和索引绘制按各自目标选择缓冲；索引范围越界返回 GL 错误。
- 默认纹理名 0 重复绑定时复用内部槽，避免耗尽纹理对象；公共 glIsTexture(0) 行为保留。
- Neverball 关闭反射、阴影和自动 mipmap；缺少点精灵衰减函数时跳过对应装饰性粒子。

补丁导出为 `patches/game-ports-glx.patch` 和 `patches/*-axu3eg.patch`。硬件、内核模块和 Tux Racer 发布文件不在本次改动范围。

## 素材与部署

Quake 使用 id Software 共享版 `quake106.zip` 中的 pak0.pak。Quake III 使用官方 Linux Demo 安装包中的 demoq3/pak0.pk3，只提取数据，不执行旧 x86 安装程序。下载 URL、SHA256 和提取结果见 `report/game_ports_demo_downloads.json`、`report/game_ports_demo_assets.json`。Demo 素材仍受各自原始许可约束，不能视为 GPL 游戏素材。

开发板不接网络，使用 COM11 控制 Linux，JTAG 在未使用 GPU 时分块写入预留图形资源区 `0x60800000`，Linux 接收后逐块及整包 SHA256 校验，再保存 SD 实验缓存：

```text
/opt/rasterix/experimental/cache/{game-runtime,neverball-data,quake-data,quake3-data}.tar.gz
```

已验证的旧运行包在更新时保留带摘要的备份。工作文件解压在 `/tmp/rasterix-games`；重启后需重新解压，但 SD 缓存保留。传输期间不能运行任何 GPU 游戏。

实验启动器 `linux/rasterix_games.py` 已保存在 SD 的 `/opt/rasterix/experimental/rasterix_games.py`。它检查硬件配置、ABI、模块和无其他 GPU 客户端，验证缓存摘要，检查动态库依赖，然后运行指定游戏。Linux root 终端可直接启动：

```bash
python3 /opt/rasterix/experimental/rasterix_games.py run neverball --seconds 1800
python3 /opt/rasterix/experimental/rasterix_games.py run neverputt --seconds 1800
python3 /opt/rasterix/experimental/rasterix_games.py run quake --seconds 1800
python3 /opt/rasterix/experimental/rasterix_games.py run quake3 --seconds 1800
```

一次只运行一个游戏；1800 为半小时上限，可调小。终止后再切换其他游戏。默认生成唯一结果目录，不覆盖上次记录。Neverball 关卡介绍点击后进入游戏，方向键控制倾斜；Neverputt 点击进入击球视角，再点击击球。Quake 使用原游戏按键。

记录固定测试编号时可显式指定：

```bash
python3 /tmp/rasterix_games.py run quake --attempt quake01 --seconds 60
python3 /tmp/rasterix_games.py run quake3 --attempt quake3_01 --seconds 60
python3 /tmp/rasterix_games.py run neverball --attempt ball01 --seconds 60
python3 /tmp/rasterix_games.py run neverputt --attempt putt01 --seconds 60
```

显式 attempt 必须唯一。输出保存于 `/tmp/rasterix-games/results/<attempt>/`，包含命令、实际二进制和库摘要、进程退出状态、日志、每秒硬件计数和呈现 FPS。实际客户端日期为 2026-10-18；开发板 RTC 仍为 2020，性能统计使用单调时钟。

## 板测验收边界

首次 GLX 三角形和 Quake 菜单均已实际呈现。Quake 菜单 45.3 秒、1358 帧约 29.97 FPS，仅代表菜单。随后开局测试发现 256×256 光照贴图和 DMA 超时，不能把显示桥错误计数为 0 当作完整渲染通过。DMA 超时后需正常重启恢复，再测试其他游戏；不能沿用故障链路把后续退出都归因于新游戏。

`quake03` 已加载并回读 Quake I e1m1 关卡，90.62 秒 2606 帧，含加载平均 28.76 FPS，无 DMA 超时，显示错误计数为 0。

`quake3_02` 已使用原生模块加载并回读 q3dm1 关卡，70.51 秒 2009 帧，含加载平均 28.49 FPS，无 DMA 超时，显示错误计数为 0。

`putt03` 虽然持续呈现约 30 FPS，但回读是错误几何，伴随纹理槽耗尽，不能算游戏通过；后续 `putt04` 已修复并复测。

`glx02` 已通过独立顶点 / 索引缓冲大小查询、索引绘制和 4096 次默认纹理重复绑定检查，实际呈现 16 帧，退出 0。

`putt04` 修复后显示第一洞、球道和 HUD，XTEST 点击后进入击球视角；100.76 秒 3022 帧，平均 29.99 FPS，显示错误为 0，无 DMA 超时、纹理槽耗尽。单洞命令未提供整套球场元数据，因此 HUD 的 Par 为 0；未宣称完整 18 洞玩法通关。

`ball01` 已从关卡介绍点击进入可操作关卡，并注入 Up 按键。回读能看到球体、金币、场地、天空和倒计时；150.11 秒 3289 帧，平均 21.91 FPS，显示错误为 0，无 DMA 超时。当前硬件只支持一个用户裁剪平面，游戏使用其他裁剪平面时仍有警告，不能视为完整 OpenGL 功能兼容。

最终相同实验 libGL（SHA256 `23333954b87c300b9060f3ee790b6c9b1a7e51a7444a3f4d272a655db17b331d`）复测：

| 游戏 | 实际关卡 / 状态 | 时长 | 帧数 | 平均 FPS（含加载） |
|---|---|---:|---:|---:|
| Neverball | easy；点击开局并注入 Up | 150.11 s | 3289 | 21.91 |
| Neverputt | 第 1 洞；点击进入击球视角 | 100.76 s | 3022 | 29.99 |
| Quake I | e1m1；注入 Up | 70.49 s | 2020 | 28.66 |
| Quake III | q3dm1；场景、武器与 HUD | 90.77 s | 2607 | 28.72 |

上述测试全部进程正常退出、显示错误为 0、无 DMA 超时。Quake III 的一次模拟按键未发送：控制 helper 使用了引擎名，而实际窗口标题为 `Quake 3: Arena`；已修正 helper 的标题映射，但该次测试不计为输入验证。手动 XTEST 是软件输入验证，不等于物理 USB 外设测试。

关卡截图：

![Neverball](../report/board_serial/game_port_ball01_play_readback.png)
![Neverputt](../report/board_serial/game_port_putt04_final_readback.png)
![Quake I](../report/board_serial/game_port_quake04_readback.png)
![Quake III](../report/board_serial/game_port_quake3_03_readback.png)

最终运行包仅在启动器中增加自动编号，渲染库、游戏二进制和上述实测文件摘要逐项一致；整包与 SD 缓存摘要由 `scripts/verify_game_ports_delivery.py` 核验，报告 `report/game_ports_acceptance_2026-10-18.json`。这是追加游戏的独立验收，不修改 Tux Racer 原发布报告。

最终 `game-runtime.tar.gz` 为 3508259 字节，SHA256 `9936c1d0a08d71fa683ff082009fd099866cb22d31dc4de001b300d6493861c4`，SD 缓存整包校验通过。启动器 SHA256 为 `4965ca0c95158c3b65e4b852d49a807bb83051fd382d5a6c9143658693a5179a`，最终使用持久启动器的 prepare 操作也已验证。

五组最终测试（含 GLX 探针）的 game.log、samples.jsonl、result.json、dependencies.log 已保存到 SD `/opt/rasterix/experimental/results-2026-10-18/`，回读日志和采样文件摘要与测试结果一致。原 Tux Racer、smoke、两个内核模块的板上文件摘要与既有版本一致。游戏配置和游玩进度目前使用临时 HOME，重启会清除；SD 缓存、启动脚本及已保存验收日志保留。

机器可读结果见 `report/game_ports_board_trials_2026-10-18.json`，实际回读图片及摘要见 `report/game_ports_images_2026-10-18.json`。声音、物理 USB 输入、miniDP 输出和长时间稳定性未由本次短测确认。
