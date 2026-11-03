# MC 神经风格第二轮优化（2026-10-21）

本文保留 v2 的历史实现和验收。板上正式入口已于 2026-10-22 更新为 v3，进一步调整源游戏提交调度，最新数据与回退方式见 [第三轮优化](CLASSICUBE_STYLE_OPTIMIZATION_2026-10-22.md)。

已将可选 `rix-classicube-style` 更新为 v2。保持原来的 MC 专用动漫／油画模型、400×240 源图、800×480 输出、强度 128 和保护区域，在相同模型、世界及 CPU 频率的 ABBA 对照中，最终风格输出从 **13.49 FPS 提高到 20.83 FPS，约提升 54.3%**。

普通 `rix-classicube`、原始游戏包、旧神经运行时、BOOT.BIN、设备树和 FPGA bitstream 均保留。本轮没有增加 FPGA 资源或降低输出分辨率。

## 实测

每个配置重新启动相同种子、世界大小、视距、自动转向路径的真实 MC，加载同一份 MC anime 权重。CPU 均为 userspace / 1066666 kHz。20 秒 ABBA 无截图、无诊断文件输出：

|顺序|版本|最终风格 FPS|
|---|---|---:|
|A|v1|13.5153|
|B|v2|20.7622|
|B|v2|20.8886|
|A|v1|13.4705|

最终包另做两风格各 62 秒长测：

|风格|处理并完成显示的帧数|实际秒数|最终风格 FPS|
|---|---:|---:|---:|
|MC oil|1287|62.0416|20.7442|
|MC anime|1331|62.0279|21.4581|

同轮游戏源画面计数约 57.03 FPS；这不是最终风格帧率。没有达到 30 FPS 的结论。数据见 `report/classicube-style/optimization-v2/{select,abba,final-board}.json`。

## 改动及作用

**融合减少重复计算。** 默认保护的完整源图行直接输出原像素，不计算无用的边缘权重／残差；五倍水平插值采用增量生成，避免重复索引；NEON 使用八路 16 位精确除法替代两组 32→64 位乘法。保留原来的双线性残差、边缘权重、RGB 裁剪和半值远离零舍入。

对同一张已捕获 MC 帧做固定输入 ABBA，融合约 **17.5→8.3 ms**，校验值相同。在真实游戏与后台读取共同运行时，融合约 9.3～9.5 ms。没有用主机时间冒充 A53 时间。

**下一帧读取与当前帧推理／融合重叠。** v1 虽提前请求 FPGA 快照，但 CPU 等到上一帧显示写回后才读取下一帧。v2 允许一个后台任务读取候选源缓冲，同时主线程处理当前帧。主线程等待后台完成并获得帧号副本后，才交换两个独立 CPU 缓冲。

后台任务独占 `Snapshot`；主线程不并发读取其 token／frame 字段。所有停止、超时或异常路径先等待后台任务退出，再释放快照租约、导出最后一帧和恢复显示。未提交的预取任务不计入已显示帧。继续使用 SNP1 不可变租约快照，不读取实时 PS 帧槽作为融合底图。

**读取格式转换直接使用 NEON 寄存器。** 保留相同的 32 字节对齐 Device LDP 访问和每核屏障，只把 XRGB→RGB565 标量打包改为 NEON，避免临时栈数据。没有更换为未经验证的缓存映射，也没有改变 FPGA 内存布局。

同模型短测矩阵如下，用于选择配置，不代替 ABBA：

|配置|风格 FPS|
|---|---:|
|v1|13.4336|
|新融合、串行、原四核读取|15.2006|
|新融合、串行、NEON 四核读取|15.4042|
|后台重叠、NEON 四核读取|21.0744|
|后台重叠、NEON 双核读取|20.1179|
|后台重叠、NEON 单核读取|14.5060|

默认采用 `overlap / 4 / neon`。转换优化单独收益很小，主要收益来自融合简化及阶段重叠。重叠时每段计时可以覆盖同一时间区间，**不能把快照、推理、融合的累计秒数相加当作总耗时**。新增 `foreground_snapshot_wait_seconds`、实际读取线程数、未提交预取数和 `phase_times_overlap` 字段。

## 使用和对照

```sh
# 已安装入口，默认采用 v2 优化配置；键鼠操作
rix-classicube-style --style anime --seconds 1800
rix-classicube-style --style oil --seconds 1800

# 同一 v2 程序的串行读取对照
rix-classicube-style --style anime --seconds 30 \
  --frame-pipeline serial --snapshot-copy paired --snapshot-workers 4

# v1 完整包和旧入口仍保留，可单独运行，不切换当前入口
python3 /media/sd-mmcblk1p1/rasterix-mc-style-v1-command.py \
  --style anime --seconds 30
```

`--autoplay` 仅供自动验证，普通运行保留键鼠。原始普通游戏仍通过 `rix-classicube` 启动。

## 验证与部署

本轮 **77／77 项工程验收通过**，结果保存在 `report/classicube-style/optimization-v2/acceptance.json`；首轮 v1 的 87 项历史验收保留。

- A53 融合整数检查 1102730 项、快照 RGB 转换 17353220 项、并发交接 794 项通过。并发测试覆盖写入候选后停止、工作线程异常、析构等待、重复提交和超时丢弃。
- 两种风格的源图到 CNN 输入配对零差异，FPGA INT8 输出与独立整数模型零差异，完整 384000 像素显示输出 SHA 与独立参考一致。
- 两种风格各 6000 点真实 LCD 回读零差异，保护区域保持原像素。
- 后台读取模式下，自然结束、实际出帧后提前停止、坏模型失败清理都已实机验证。坏模型预期 NN 返回 1，但游戏正常排空、显示恢复且无残留租约。
- 已安装公开入口在空 RAM 缓存时从 SD 重新校验、解包并运行，最终状态与完整验收见 `optimization-v2/acceptance.json`。

v2 包为 `build/classicube-style/optimization-v2/mc-style-v2.tar.gz`，107174 B，SHA256：

```text
8c8cd893bd6b7a665e5ad6ea6fbf6d5fd54a31f25aa7708ea11b7f7241293d0a
```

SD 路径 `/media/sd-mmcblk1p1/rasterix-mc-style-v2.tar.gz`。更新器持有游戏、后处理、解包三把锁，在新包所有成员校验、SD 完整回读、旧入口备份之后，才原子替换公开入口。保留 v1 完整包和旧入口；根分区 32 MiB、SD 16 MiB 保护不降低。安装凭据见 `optimization-v2/update.json`。这次没有执行冷启动，不能把空 RAM 缓存恢复称作断电启动验证。

当时的构建与验证命令如下。当前 `package_mc_style.py` 和启动器检查已推进到 v3；重现 v2 应使用 `build/classicube-style/optimization-v2-baseline/` 中保留的原脚本及源文件，v2 完整归档无需重打包。

```powershell
wsl -d Ubuntu --exec bash /mnt/f/1FPGA/Xilinxprj/prj2/rasterix-linux/scripts/build_mc_style.sh v2
python scripts/check_mc_neural_session.py
python scripts/check_mc_style_update.py
python scripts/package_mc_style.py
python scripts/record_mc_style_optimization_v2.py
```

模型、画风及其限制没有因提速而改变：仍是 7×7 感受野的小网络；保守原图矩形不是完整 HUD 分层；没有训练或验收时间一致性；本路径没有接入 FSR／学习型超分。当前 `quality_acceptance=false`、`temporal_acceptance=false`。初始接入与训练依据见 `CLASSICUBE_NEURAL_STYLE_2026-10-21.md`。
