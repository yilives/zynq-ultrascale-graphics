# MC 神经风格第三轮优化（2026-10-22）

已将板上 `rix-classicube-style` 更新为 v3。对 MC 源渲染的 CPU 提交上限做调度调整，在同一次启动、相同模型与世界的 ABBA 对照中，最终风格输出从 **20.6650 提高到 24.1989 FPS，提升约 17.1%**。两种风格另做各 62 秒长测，均完成显示且无 GPU 错误。

## 调整内容

MC 残差风格路径默认使用 `--source-fps-limit 60`，向私有源游戏启动器传递原生 `--fps-limit 60`。原上限为 120；实际源渲染约 60 FPS，但超过最终约 21 FPS 的风格输出需求，持续占用处理器与传输资源。降低提交上限后，测得快照读取和前台等待减少，最终显示吞吐提高。

这里的 60 是 CPU 提交上限，**不代表最终风格图像达到 60 FPS**。所选配置下源图实际呈现约 55 FPS，最终风格输出约 23～24 FPS；30 上限也做了测试，最终风格性能相近，但源图降至约 30 FPS，因此采用 60。

本轮复用 v2 的同一份 80840 B 神经运行时和相同动漫／油画权重，继续使用 `overlap / 4 workers / neon`。源图 400×240、CNN 160×96、显示 800×480、强度 128、保护矩形和融合像素算法均相同。CNN 仍是 FPGA INT8 3→8→8→3，核心每帧 414738 周期，100 MHz 下约 4.147 ms；本轮没有让卷积核心本身更快。

普通 `rix-classicube` 的原启动器及默认参数保持原样。其他游戏继续使用已有配置；`--source-fps-limit` 只接受 ClassiCube。MC 的纯 `neural` 合成方式默认仍为 120。

## 同模型实测

每个测试都重新启动相同 64³ 世界、视距 32、自动验证路径。CPU 为 userspace / 1066666 kHz。运行时及动漫模型 SHA 相同；对照运行不导出截图。此轮全部记录的 boot ID 为 `e87cfedf-7b81-439d-92a4-1677b88214fa`。

12 秒选择测试：

|CPU 提交上限|最终风格 FPS|源图实际呈现 FPS|
|---|---:|---:|
|120|21.0082|60.1781|
|60|24.4870|55.3885|
|30|24.1241|30.0041|

随后用 20 秒 ABBA 复测 60 上限：

|顺序|CPU 提交上限|最终风格 FPS|源图实际呈现 FPS|
|---|---:|---:|---:|
|A|120|20.6679|60.1010|
|B|60|24.1353|55.4643|
|B|60|24.2624|54.6990|
|A|120|20.6621|60.0039|

旧配置均值 20.6650，新配置均值 24.1989 FPS，提升 17.1007%。这是同一轮板测中的增益，不将前一天的数值直接拼接为对照。数据见 `report/classicube-style/optimization-v3/{select,abba}.json`。

最终包两种风格各运行 62 秒，另用配对诊断帧核验显示：

|风格|完成显示的帧数|实际秒数|最终风格 FPS|
|---|---:|---:|---:|
|MC oil|1431|62.0308|23.0692|
|MC anime|1450|62.0117|23.3827|

长测场景随自动移动而变化，帧率与短测有差异。此处计数为神经处理、显示提交、显示完成三者一致的帧数。该长测期间源图实际呈现约 54.37 FPS。正式安装入口另运行 15 秒，最终风格 24.4335 FPS、源图 55.1232 FPS。

## 验证

汇总 **63／63 项工程验收通过**，见 `report/classicube-style/optimization-v3/acceptance.json`。汇总器读取实际报告、包和哈希，缺失证据按失败处理。

- 两种风格的同帧源图→CNN 输入、实际 FPGA INT8 输出→独立整数参考均零差异；各完整 384000 显示像素的 SHA 与参考一致，各 6000 点 LCD 回读零差异，保护区域零差异。
- 实际 XTEST→X11→SDL→MC 输入链路在 CNN 运行时通过 12 项检查，包含移动、跳跃、键盘松开、鼠标视角、数字栏位、滚轮、菜单指针和恢复游戏。此测试关闭 autoplay；实体 USB 键鼠尚未接入验证。
- 真实游戏正常结束、出帧后提前结束、无效模型三个生命周期测试通过。无效模型预期神经进程返回 1，源游戏仍正常排空并恢复显示。
- 包内最终启动器的 51 项主机参数／生命周期检查通过；更新器 45 项检查通过，包括原子提交失败注入和保留旧入口。
- 正式 `/usr/bin/rix-classicube-style` 在移走已校验的 RAM 解包缓存后，重新从 SD 校验、解包全部 11 个载荷并成功运行。v3 本次未做断电冷启动。
- 最终 GPU 的 frame/swap/copy/presented/last_presented 均为 21012，status=3，错误计数均为零；无活动 GPU 客户端、快照租约、过期计数或隔离标记，显示模式恢复为 1。
- 原 31 个全局神经文件、MC 包和原启动器、私有及共享 GL、BOOT.BIN、DTB 与 v2 记录逐字节相同。原 v1／v2 报告与回退包保留。

本轮按已有运行时和权重开展调度验证。艺术质量与时间一致性仍未验收：`quality_acceptance=false`、`temporal_acceptance=false`。模型仍是 7×7 感受野的轻量原型，保护矩形仍为保守原图区域，尚非原生 HUD 分层；此入口仍使用最近邻 2× 基图和神经残差融合，没有接入 FSR 或学习型超分。

## 使用

```sh
# 板上正式入口，默认 source-fps-limit=60；键鼠操作
rix-classicube-style --style anime --seconds 1800
rix-classicube-style --style oil --seconds 1800

# 同一模型与运行时，复测原提交上限
rix-classicube-style --style anime --seconds 30 --autoplay \
  --source-fps-limit 120

# 可显式选择 30／60／120；普通游玩省略 --autoplay
rix-classicube-style --style anime --seconds 30 --autoplay \
  --source-fps-limit 60

# 使用保留的完整 v2 包和旧命令运行对照，不切换当前入口
python3 /media/sd-mmcblk1p1/rasterix-mc-style-v2-command.py \
  --style anime --seconds 30 --autoplay
```

## 包与持久化

主机产物：`build/classicube-style/optimization-v3/mc-style-v3.tar.gz`，55887 B，SHA256：

```text
a45fcf150c4a79b5c0014c0667b815fb0f136f1c60760175f48a784b1c521a82
```

SD 路径 `/media/sd-mmcblk1p1/rasterix-mc-style-v3.tar.gz`。正式启动命令为 1997 B，SHA256 `36cbd4555c33c6a24ebba12fe1fc94e4ea1b066f7d500de42730ab387d6d0a01`。更新器验证 GPU 空闲、所有包成员、完整 SD 回读和旧命令备份后才原子替换入口；更新凭据为 `optimization-v3/update.json`。

v3 包省略 v2 中三个独立测试可执行文件，神经运行时原样复用。三个测试二进制仍保存在 v2 完整回退包；原有 A53 执行证据保留。本轮没有通过删除回退来腾空间。

更新后根分区空余 33615872 B，SD 空余 16894976 B；32 MiB／16 MiB 保护均保留。后续升级须继续核算临时文件空间，所有此次测试与截图保存在 RAM。

复现当前包及主机验证：

```powershell
# 复用已验证 v2 运行时；此轮无需重新编译 FPGA/C++
python scripts/package_mc_style.py
python scripts/check_mc_neural_session.py
python scripts/check_mc_style_update_v3.py
python scripts/record_mc_style_optimization_v3.py --check-only
```

`linux/classicube/update_mc_style_v3.py` 是严格的已知 v2→v3 更新器，已经应用；当前入口为 v3 时再次运行会拒绝，不能当作通用重装器。包与源文件对应关系见 `optimization-v3/package.json`；输入、长测、生命周期、公开入口和最终文件完整性证据均在同目录。

后续提速重点仍是快照读取与 PIO 数据传输；继续减少这些开销需重新测量和验证硬件接口。前两轮实现见 [v2 优化记录](CLASSICUBE_STYLE_OPTIMIZATION_2026-10-21.md) 和 [初始模型与接入](CLASSICUBE_NEURAL_STYLE_2026-10-21.md)。
