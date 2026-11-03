# MC 风格第四轮：输出接口与全链路优化（2026-10-22）

本轮已完成独立整机 FPGA 构建、RAM 加载和实际游戏 ABBA 对照。固定输入的整次推理由约 18.8 ms 降到 12.38 ms；最终组合配置在同次启动的对照中由 **23.9282 提高到 26.2467 FPS（约 +9.69%）**。这是最终风格画面的完成帧率，不是源游戏帧率或卷积核心的理论吞吐。

## 改动与边界

新增 CNN 输出寄存器 `0x40`，一次 AXI 读取返回 valid、fault、last 和 RGB。仅在读响应真正握手后弹出一个像素；无有效像素时不弹出，CPU 保留轮询。原 `STATUS + DATA(0x18)` 接口保留。新能力值为 7，适配器 ABI 为 `0x00020001`；新运行时仅在能力与 ABI 均匹配时使用新接口，旧固件自动走原接口。

此前每帧至少读取 15360 次状态及 15360 次数据。新接口将有效像素的数据与状态合并，实际固定输入的输出阶段约从 13.35 降到 6.84 ms；输入约 1.39 ms、核心约 4.147 ms。核心仍是相同的 INT8 3→8→8→3，每帧 414738 周期、100 MHz，没有减少网络计算量。

另将本次 MC 风格会话所属的两个 RasterIX `SCHED_RR/2` worker 调整为 `SCHED_OTHER/0`，减少其与普通优先级取帧线程的竞争。调整前验证进程树、PID/TID 启动时间和线程策略；不改变系统全局调度。原普通 MC 入口继续使用原配置。此 helper 的 `/proc` 检查与数字 TID 调度调用不是内核级原子操作，身份复核不能宣称消除了所有极端 PID 复用竞态。

源图 400×240、CNN 160×96、LCD 800×480、强度 128、模型、同帧残差融合、边缘权重及保护矩形保持相同。候选的其他像素融合实现均未采用。此版本没有新增 FSR、学习型超分或更大的风格网络；艺术质量和时间一致性仍未验收。

## 实测对照

每轮重新启动相同 MC 世界、视距 32、提交上限 60，CPU 为 userspace / 1066666 kHz。每个样本约 20 秒，顺序 A/B/B/A。汇总 FPS 使用完成帧数总和除以实际秒数总和。

|对照|A 两轮 FPS|B 两轮 FPS|加权汇总 A→B|
|---|---|---|---|
|同一新运行时，legacy→atomic|23.4541 / 24.0054|25.3027 / 26.0775|23.7297→25.6899，+8.26%|
|原 v3→atomic + normal worker|24.0714 / 23.7853|26.7045 / 25.7883|23.9282→26.2467，+9.69%|

组合对照中的源图实际呈现约 53～56 FPS。源帧计数和最终神经显示完成计数分别记录，不能互换。线程调度独立的 30 秒 ABBA 为 22.7920→24.0268 FPS（+5.42%）；不同实验的百分比不能相加。

证据：`report/classicube-style/exploration-v4/{transport-post,protocol-abba,release-abba,scheduler-abba}.json`。

## 全面探查与取舍

|候选|实际结果|处理|
|---|---|---|
|合并输出状态与数据的 FPGA 接口|固定输入推理约减少 34%；游戏协议对照 +8.26%|采用|
|MC 风格会话取消两个 RR worker|独立长对照 +5.42%；与新接口组合亦有增益|采用，仅本会话|
|CPU affinity / 2 个读取 worker|部分源图变慢；两核/两 worker 风格约 18.85/19.75 FPS|不采用|
|planar、双行及强度 128 专用融合|各有 5568 万像素 A53 差分通过；微基准微增或变慢，planar 游戏 ABBA 无收益|不采用|
|2/4 个显示写线程|1/2/4 线程约 7.93/8.10/8.11 ms，18 次完整回读一致|不采用|
|直接提高 CNN 时钟或复制阵列|当前核心只占约 4.15 ms，新增布线风险而端到端上限有限|未实施，不作提速承诺|

原时序剖析证明输出 PIO 是推理内的主要开销。新接口去掉约 6.6 ms 后，前台等待下一源帧从约 4.2 增到 6.8 ms，后台读取约 28.5 ms、租约等待约 9.1 ms；两者与前台重叠，不能全部相加。最终前台还包含缩小约 1.3 ms、推理 12.6 ms、融合 8.9 ms、显示写回 8.4 ms。

后续优先项是租约保护的 packed RGB565 快照，或 FPGA 上的同帧精确融合/显示路径。前者可将源图读取从 384000 B 降为 192000 B，但需要新增协议、地址和完成语义；后者可消除 ARM 全显示缓冲写回，但必须保留原图细节、保护区域、整数舍入及 bank 所有权。目前没有把这些设想计为已实现。

## FPGA 工程与资源

独立工程：`build/vivado_neural_atomic_v4/rasterix_neural_atomic_v4.xpr`。原工程、发布 RTL、BOOT 和 DT 保留。新工程的创建、构建及布线三个阶段均记录实际 CNN 源路径，OOC 脚本亦绑定候选 RTL。

|资源|使用量|
|---|---:|
|LUT|47216 / 70560|
|寄存器|48671 / 141120|
|BRAM Tile|138 / 216|
|DSP|152 / 360|
|使用过的 CLB|8520 / 8820，约 96.60%|

整机 WNS=0.708 ns、WHS=0.011 ns、WPWS=0.124 ns，无失败端点、路由错误或阻断 CDC。CNN OOC 相比原版增加 71 LUT，寄存器、BRAM、DSP 数量相同。CLB 已高度分散占用，不能由剩余 DSP 数量推断还可直接加入大型网络。

仿真包含两个模型各 15360 个输出，完整张量一致，30720 次实际弹出、30718 次无效读取及 57813 次读响应反压。板上两模型各以 legacy/atomic/atomic/legacy/auto 运行，所有完整输出与独立整数金值相同，旧协议可继续使用。

## 加载与交付状态

已通过 Linux FPGA Manager 从 RAM 加载新逻辑，未重启 Linux。加载前保存并校验新旧整份 raw 镜像，停止 PL 客户端并解除精确驱动绑定；加载后先等 MIG 就绪，再恢复 DMA、显示与触摸 GPIO 驱动。全部原模块及绑定恢复，GPU 错误计数为零。控制器在主机上通过 107 项故障/恢复检查；本次实际加载直接成功，没有把模拟回退称为真实回退测试。

运行时全量加载参考 [AMD FPGA Manager 说明](https://docs.amd.com/r/en-US/ug1137-zynq-ultrascale-mpsoc-swdev/FPGA-Manager-Solution)。本工程的加载、状态和恢复证据在 `report/classicube-style/exploration-v4/fpga-load.json`。

两种风格各 62 秒长测、完整像素金值、模拟键鼠及三条生命周期路径均已通过，RAM 板测汇总为 **14/14 项通过**，见 `report/classicube-style/exploration-v4/acceptance-final.json`。

|风格|显示完成帧|实际秒数|最终风格 FPS|
|---|---:|---:|---:|
|油画|1566|62.0202|25.2498|
|动漫|1601|62.0050|25.8205|

每种风格均确认同帧源图与 CNN 输入匹配、实际 FPGA 输出与独立整数参考匹配，完整 384000 显示像素摘要及独立 6000 点 LCD 读取零差异，保护区域零差异。实际 XTEST→X11→SDL→游戏的 12 项输入检查通过，包含移动、跳跃、松开、鼠标视角、栏位、滚轮、菜单指针及恢复游戏；实体 USB 键鼠和手指触摸未在本轮验证。

原全局神经运行时在新 FPGA 上另运行 Neverball，320 个显示完成帧、正常结束，证明旧接口实际兼容；这是兼容性验证，不作为该游戏提速的对照。

## 正式软件入口与回退

已安装 `/usr/bin/rix-classicube-style` 新入口，以及 SD 上 49566 B 的覆盖包。入口每次验证完整 v3 基包、v4 覆盖包及合并后的 12 个载荷，在独立 RAM 目录原子展开。它继承 `PYTHONDONTWRITEBYTECODE=1`，保持严格缓存中没有额外的 Python bytecode 文件。

正式入口已做两次真实启动：第一次从 SD 新展开，第二次验证并复用相同 inode 的缓存，实际自动选择 atomic，分别约 27.07/26.83 FPS。这两次短运行是安装检查，性能结论仍采用前述 ABBA 和长测。

```sh
# 板上正式入口，默认键鼠操作
rix-classicube-style --style anime --seconds 1800
rix-classicube-style --style oil --seconds 1800

# 自动运行仅用于验证
rix-classicube-style --style anime --seconds 30 --autoplay

# 使用保留的完整 v3 和旧入口，不切换当前命令
python3 /media/sd-mmcblk1p1/rasterix-mc-style-v3-command.py \
  --style anime --seconds 30 --autoplay
```

主机覆盖包：`build/classicube-style/exploration-v4/package/mc-style-v4-overlay.tar.gz`，SHA256 `0f13b7fbde903a5d65e05234f2ab29f9bc344fe45fc8ee34411618dade095ab6`。其完整 v3 依赖仍为 `a45fcf150c4a79b5c0014c0667b815fb0f136f1c60760175f48a784b1c521a82`。安装及正式入口报告在 `report/classicube-style/exploration-v4/persistent/`。

原 31 个全局神经文件、9 个 MC 包内文件、原普通 MC 启动器、私有/共享 GL、SD BOOT/DTB、历史启动备份及 v1/v2/v3 回退文件均保留并核对。最终 GPU 各队列计数均为 19974，status=3、错误计数为零，无 GPU 客户端或快照租约。最终 root 可用 34406400 B、SD 可用 16843264 B，保持原 32 MiB/16 MiB 阈值。

另有独立的 **7/7 部署验收**，在保留 14 项 RAM 板测报告的基础上核对安装、正式入口和最终状态，见 `report/classicube-style/exploration-v4/deployment-acceptance.json`。该报告明确区分软件持久化、FPGA RAM 加载及未完成的 FPGA 冷启动。

## FPGA 持久化仍需完成

**软件已持久安装，FPGA 新逻辑目前只在 RAM 中。** SD 原 BOOT.BIN 与 DTB 未改；断电后仍会加载原 cap3 逻辑，新软件会自动回退旧输出接口，不应期待继续保有本轮完整硬件收益。本轮没有进行断电冷启动验收。

已生成结构完整的新启动包：

- `build/classicube-style/exploration-v4/boot/BOOT.BIN`，6498132 B，SHA256 `7a4ff39a9d7f4011dc4abf0670702493851498213222b980cc2fbfcb47d9b68c`。
- 同目录 `system.dtb` 与原版完全相同。
- 新旧 PS 初始化相同；完整 U-Boot 控制 DTB 存在；唯一 PL 段匹配已板测的 bit/raw，其余四个加载段与原 BOOT 逐字节一致。21 项结构/故障检查通过，报告为 `report/classicube-style/exploration-v4/boot-validation.json`。

在线保留 16 MiB 空间阈值后，当前 SD 剩余暂存余量不足以放置约 6.5 MB 的新 BOOT，因而未覆盖启动文件。后续需完成离线 SD 更新或处理启动分区空间，再进行冷启动与输入/显示验收；目前不将主机校验等同于冷启动成功。

主机复核入口：

```powershell
python scripts/check_mc_style_exploration_v4.py --phase final
python scripts/record_mc_style_v4_deployment.py
python scripts/check_mc_atomic_boot_v4.py verify
```
