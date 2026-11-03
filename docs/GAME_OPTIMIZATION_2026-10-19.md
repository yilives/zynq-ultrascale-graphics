# AXU3EG 五游戏优化与实板验收（2026-10-19）

本轮覆盖 Tux Racer、Neverball、Neverputt、Quake I、Quake III。ARM 负责游戏逻辑、OpenGL 状态及顶点处理，RasterIX FPGA 负责像素渲染；400×240 RGB565 经现有 PL 显示桥、2 倍缩放和配色输出到 800×480 RGB LCD。没有新增 bitstream 或改动启动设备树。

## 实测性能

| 游戏 | 优化前实际 FPS | 优化后实际 FPS | 本轮主要收益 |
|---|---:|---:|---|
| Neverball | 21.77 | 28.50 | 约 +31%；补齐六平面裁剪 |
| Neverputt | 30.06 | 30.00 | 保持约 30；完整球场和正确 Par |
| Quake I | 28.38 | 30.04 | 约 +6%；保留配置和存档 |
| Quake III | 28.50 | 28.51 | 保持约 28.5；独立策略及稳定切换 |
| Tux Racer | 30.02 | 30.05 | 保持约 30；纹理预滤波、真实 FPS、正常退出 |

数值来自同一块板、相同 BOOT.BIN/DTB、全新配置目录、相同测试输入的硬件 `presented` 计数。基准对比固定使用 nearest/original；日常入口默认 bilinear/original。比较窗口固定为启动后 12～39 秒；保留所有原始采样，不把 CPU 提交次数或原有 FPS 文本作为实际显示帧率。场景不是确定性录像重放，微小差异不作为性能提升。

Neverputt 的旧测试直接加载单洞，新测试加载完整球场元数据；因此表中性能比较只说明这些实际记录中的场景。旧 Tux Racer 的帧率窗口有效，但测试最后需要强制退出，其整体功能结果未通过；新版单独验证正常退出。

## 已实现的改变

* 独立 GLX 库增加按 draw 清空的 128 项索引顶点读取缓存，变换缓存由 16 项扩至 128 项。保留 `RIX_VERTEX_CACHE=0` 以进行一致性对照；缓存不会跨 draw 重用客户端顶点数据。
* 补齐六个用户裁剪平面的设置、查询、启停，以及三角形、线、点的实际裁剪。Neverball 原有的额外裁剪平面警告已纳入回归检查。
* 根据实测选择呈现策略：Neverball、Neverputt、Quake I 在提交本帧前排空并等待上一帧；Quake III 保留异步上传，并使用 30 Hz 引擎上限；原生 Tux Racer 保留异步流水。所有路径退出前都等待工作线程、上传线程、DMA 及实际呈现完成，再释放命令存储。
* 同步路径按实际硬件 frame ID 等待，使用 300 µs 状态轮询，避免内核 2 ms sleep 被调度 tick 放大。软件提交次数不被当作硬件 fence。
* Neverputt 新增 `--course holes-putt.txt`，读取整套 18 洞的元数据，第一洞正确显示 Par 2；旧 `--hole` 入口保留。
* Tux Racer 的大纹理缩小改为整数面积预滤波，RGB 按 alpha 加权，覆盖奇数尺寸和透明边缘。保持已有尺寸和纹理容量约束。
* Tux Racer HUD 改读硬件实际呈现 FPS，计时使用 monotonic clock；补充 SDL 关闭窗口和退出事件，支持测试及用户正常关闭。
* Quake I 使用持久、可写的 basedir，PAK 通过只读素材位置的符号链接提供；Quake III 使用持久 fs_homepath；其他游戏也保留各自配置目录。Neverball/putt 只强制必要的硬件视频参数，保留按键、鼠标和用户偏好。

全局同步方案曾使部分游戏降至约 15～24 FPS，未作为交付版本。单独把 Quake III 上限降回 30 也未消除其同步退化，因此最终同时恢复该引擎的异步上传。中间失败候选的原始数据仍保留在 `report/postproc_games_serial_evidence.bin`、`report/postproc_games_pipeline02.bin`，不以功能通过代替性能通过。

## 板上使用

统一入口位于 `/usr/bin/rix-games`：

```sh
rix-games neverball --seconds 1800
rix-games neverputt --filter bilinear --style poster
rix-games quake --filter bilinear --style sepia
rix-games quake3 --filter nearest --style original
rix-games tuxracer --filter bilinear --style original
```

可选游戏为 `tuxracer/neverball/neverputt/quake/quake3`，滤波为 `nearest/bilinear`，配色为 `original/poster/sepia/binary`。默认 bilinear、original、最长运行 1800 秒，时间到后通过关闭窗口事件退出。当前保留单次诊断日志 8 MiB 的上限，持续刷屏时可能提前退出，具体原因写入 result.json；30 分钟持续运行尚未验收。一次只允许运行一个 GPU 客户端。`--autoplay` 是测试用的 XTEST 输入；普通游玩无需添加。

这些滤波和风格化使用现有 FPGA 硬件链路。这个统一入口没有启用 CPU FSR，也没有把 Arm ASR 标记为可用。原有 CPU FSR 实验入口和东方游戏入口继续分别维护。

配置和存档路径为 `/opt/rasterix/experimental/profiles/<游戏>/`。运行包和素材从校验过的 SD 缓存解压到 `/tmp/rasterix-games/`；重启后重建临时目录，用户配置保留。逐次结果、日志、依赖库和关闭方式保存在 `/opt/rasterix/experimental/results-optimization-20261019/<attempt>/`。

## 验收证据

最终汇总 **73 项检查全部通过**。五游戏均通过关闭窗口事件正常退出，无 DMA 传输错误，读写错误、超时、显示下溢、扫描错误均为零。Neverball 索引读取缓存的典型命中率约 68.4%。Tux Racer 完整比赛到达 Race Over，游戏计时约 127 秒、收集 15 个物品。

正常重启后再次校验：公开入口及安装文件摘要一致，五个游戏实际配置文件摘要均保留，系统 Tux Racer 与已测二进制相同；冷启动后的 GLX 六平面像素校验也通过。重启结果见 [原始记录](../report/postproc_games_reboot_qa.bin)，安装收据见 [回读记录](../report/postproc_games_install.bin)。

* 主机裁剪检查：5,000 个随机三角形，16,158 个输出顶点，以及线、点、边界和属性插值检查。
* 主机纹理检查：原尺寸映射、奇数尺寸面积缩小、统一颜色及透明边缘。
* GLX 重复启动：每轮六平面 9,246 个 GPU 像素检查，另检查 VBO/EBO 和默认纹理反复绑定。
* 缓存开启/关闭：4,608 个索引、修改源顶点和变换，96,000 个 GPU RGBA 像素逐字节一致；图像含非黑几何和彩色区域。
* 五游戏真实关卡、帧率计数、正常关闭、PL 租约截图和实际 LCD 采样；截图取得时刻可能相邻，未把二者宣称为同帧逐像素一致。
* 已安装入口的五游戏启动、持久配置、四种配色和两种滤波选择；二值风格另检查 LCD 采样只包含黑白且两者都出现。

![板上真实游戏回读](../report/game-optimization-20261019/games-final.png)

最终摘要和每项布尔判定见 [acceptance.json](../report/game-optimization-20261019/acceptance.json)，原始最终结果见 [原始证据](../report/postproc_games_final_evidence.bin)。源图及 LCD 二进制保存在 `report/game-optimization-20261019/captures/`，每个文件与板上结果中的 SHA-256 核对。

## 构建、交付与回退

已准备好 SDK、源码和各游戏构建目录后：

```sh
bash scripts/build_game_optimizations.sh
```

`scripts/prepare_sources.py` 维护原生 Tux Racer 补丁；`scripts/prepare_port_graphics.py` 维护独立 GLX 补丁；`scripts/prepare_game_port_sources.py` 维护 Neverputt 适配。编译使用 AArch64 SDK，私有 GLX/SDL 不覆盖系统库。

最终包为 `game-runtime.tar.gz`，3,978,156 字节，SHA-256：`0b7aa57090c0b887c943360a7cc24fb0f56bbb8ba25c6d7a85eed8a2caca536d`。连续两次打包摘要一致，JTAG 传输逐块及整包 SHA-256 均已校验。清单见 `report/game_ports_runtime_package.json`，传输记录见 `report/game-ports/game-runtime_board_transfer.json`。

安装器在核对缓存包和已解压文件后备份并原子更新统一入口；只有核心板测验收报告通过、包摘要相同才允许提升原生 Tux Racer 到 `/usr/bin/tuxracer`。安装收据位于 `/opt/rasterix/experimental/optimization-install.json`，旧文件保存在其 `backup_directory`。回退时先正常退出所有 GPU 客户端，再根据收据及摘要恢复对应旧文件。

本轮将 13,548,317 字节的旧实验缓存校验复制到 FAT 分区 `rasterix-game-cache-backup-20261019` 后才删除原副本，保留当前包及基线回退包；归档清单含逐文件摘要。BOOT.BIN、Image、DTB 和整卡分区未被本轮安装器改写。此次交付是板上文件更新，旧的整卡 `.img` 未重新生成。

本轮为短时、固定场景测试及一次完整 Tux Racer 比赛。物理触摸方向/手感、声音、miniDP、所有关卡通关和长时间热稳定性不在本轮验收范围。
