# 神经网络风格迁移：油画 / 动漫与 XCZU3EG 硬件化

## 交付边界

本次实现真正的卷积神经网络推理。此前 `poster / sepia / binary` 是固定颜色运算，不属于神经风格迁移。

| 项目 | 当前证据 |
|---|---|
| 完整 Fast Neural Style 油画 / AnimeGANv2 动漫教师网络 | PC 在真实游戏回读帧推理完成，包含固定提交、权重 SHA256 和许可 |
| 轻量学生网络 | 两组独立训练权重；三层 3×3、3→8→8→3，INT8；训练和测试帧按内容哈希去重 |
| A53 定点推理 | 四组张量与 NumPy / RTL 黄金参考逐位一致；160×96 独立推理约 33 ms，四线程 |
| A53 实时游戏→LCD（首版基线） | Neverball，油画 3.82588 FPS、动漫 3.97992 FPS；各 6,000 个真实 LCD 采样全部一致 |
| FPGA CNN 核 | 两组真实权重的整帧仿真、算术压力、AXI 协议和复位测试通过；独立 100 MHz 布线通过 |
| CNN 与 RasterIX 整机镜像 | 已更新实际 SD、正常重启进入 Linux；两组模型真实 FPGA 推理逐位一致，原 RasterIX GLX 检查也通过 |
| FPGA CNN → FPGA 五倍放大 → LCD | 帧复制突发优化后，Neverball 动漫无诊断 62 秒为 28.4367 FPS；含诊断油画 24.6250 FPS、动漫 27.8492 FPS；完整源帧、张量、原生显示缓冲和 LCD 采样全部一致 |
| 单命令入口 | `rix-neural-games` 的 ARM / FPGA 正常时限退出和 SIGTERM 退出均通过，先释放后处理，再 WM_DELETE 关闭游戏 |

工程性验收 **42/42 通过**，另有本轮复制 / 显示检查 **23/23 通过**，见 `report/neural-style/acceptance.json` 和 `copy-pipeline-optimization.json`。上一阶段 21 项硬件流水线检查保留为历史证据。画质仍是原型，`quality_acceptance` 明确为 `false`；不能将逐位一致性解释成完整教师画质或流畅游戏帧率已经达标。本轮完成 SD 文件更新并验证正常重启，未重做整卡 `.img`。

## 真实网络与样张

最新公共帧复制突发缓存、完整 96,000 像素校验和 28.44 FPS 实测见 [帧复制优化记录](NEURAL_STYLE_COPY_BURST_2026-10-20.md)。此前 CNN 流水线、DDR 返回缓存、FPGA 五倍放大和 23.79 FPS 的阶段见 [FPGA 流水线记录](NEURAL_STYLE_FPGA_PIPELINE_2026-10-20.md)。此前四核取帧 / NEON 和约 12 FPS 的阶段见 [并行优化记录](NEURAL_STYLE_PARALLEL_2026-10-20.md)。下文保留首版与单核阶段证据；当前 `pl_live/` 已刷新，旧记录位于 `initial-release-evidence/`、`frame-path-v1/` 和 `hardware-v1/`。

教师分别为 [PyTorch Fast Neural Style / Rain Princess](https://github.com/pytorch/examples/tree/main/fast_neural_style) 和 [AnimeGANv2 PyTorch / Paprika](https://github.com/bryandlee/animegan2-pytorch)。前者使用感知损失训练的前馈变换网络，后者为动漫生成器；没有把随机卷积或颜色 LUT 称作已训练模型。来源固定在 `external/neural-style/sources.json`。

下图为同一张真实 Neverball 原帧、完整油画教师输出、完整动漫教师输出，均在 PC 计算，**不是当前小网络的 FPGA 效果**：

![PC 完整教师网络对照](../report/neural-style/teacher-ball_log01.png)

五游戏总览见 `report/neural-style/teacher-comparison.png`。在 400×240 下统计卷积操作：

| 教师 | 参数 | 卷积 MAC / 帧 | 全局归一化层 |
|---|---:|---:|---:|
| Rain Princess | 1,679,235 | 14,764,032,000 | 15 |
| Paprika | 2,143,552 | 38,502,912,000 | 24 |

这些数值来自实际模型逐层 hook，见 `teacher-report.json`，不含归一化、插值等额外成本。不能把完整教师直接装进当前 FPGA 并保证游戏帧率；也不能把依赖整帧统计的 InstanceNorm / GroupNorm 当成固定仿射参数折叠掉。

## 小网络、训练与量化

首版选择固定画风的蒸馏学生：160×96 RGB → Conv3×3(3,8) → ReLU → Conv3×3(8,8) → ReLU → Conv3×3(8,3)。边界复制；激活为 signed INT8、比例 1/128、零点 0，RGB 对应字节减 128。每输出通道独立的 2 的幂权重比例、INT32 bias / 累加、对称半入舍入及饱和。训练包含量化感知阶段。

学生采用教师真实输出作为训练目标，16 张去重游戏帧用于训练，5 张保留帧用于测试；各 1,200 步，包含裁剪 / 翻转、L1 与局部梯度误差。不是大规模独立数据集验收，测试集也没有覆盖未知游戏域。

| 学生 | 保留帧相对教师的 RGB MAE | 未处理原帧相对教师 MAE |
|---|---:|---:|
| 油画 | 39.31 | 79.31 |
| 动漫 | 12.49 | 25.73 |

训练记录的误差来自量化感知前向评估；硬件 / A53 一致性另用整数参考逐位验证。误差下降不等于感知画质已经合格。7×7 感受野和小数据量限制明显，油画缺少完整教师的大块笔触，动漫也有柔化、细节损失。尚未完成视频时域一致性、HUD 保护或用户主观画质验收；不声称等同完整 CycleGAN / Fast Neural Style 的效果。

## 首版 FPGA 计算核（NNS1 历史记录）

`src/rtl/neural/rix_cnn_engine.sv` 实现三层全部卷积、bias、ReLU、移位量化和饱和。64 路 signed 8×8 乘法共享用于三层、九个核位置；两个同步 BRAM 特征缓存轮换。权重分成 64 个独立小 bank，避免将单个 64 读端口权重 RAM 复制。模型只在空闲期按严格地址顺序完整装载后提交，运算期间禁止接受修改。

160×96 一帧计算计数为 **1,843,200 cycles**。在名义 100 MHz 下等于 18.432 ms，仅为核心计算，不含取帧、PIO 传输、缩放和显示换页。首版实际 PS PL0 为约 99.999001 MHz。不能据此声称整个游戏达到 54 FPS。

最终独立核布线：LUT **3,712**、寄存器 **1,230**、BRAM36 tile **55**、DSP **65**，WNS **+1.827 ns**、WHS **+0.039 ns**。64 个为卷积乘法，另有地址运算；OOC 接口时序不代表整机时序。早期单体权重 RAM / LUT 乘法映射的 37,143 LUT 版本已废弃，报告仅留在 `initial-flat-weight/`，不用于交付验收。

包含 PS、MIG、DMA、RasterIX、触摸和 CNN 的最终整机布线：LUT **45,334 / 70,560（64.25%）**、寄存器 **47,805**、BRAM **135 / 216（62.50%）**、DSP **152 / 360（42.22%）**；WNS **+0.753 ns**、WHS **+0.010 ns**。setup / hold、CDC 和 bus skew 检查均通过，证据为 `report/neural_style_*`。新增核与原 GPU 共存，原 GPU 配置标识仍为 `0x9adb505e`。

`rix_cnn_axi.sv` 是独立 PIO 外设。AXI-Lite 独立捕获 AW / W，保持 B / R 稳定；输出像素只在 R 握手退休。全帧计算完成后供 CPU 读取；不把 AXI 事务 valid 直接接 LCD DE。

| 偏移 | 用途 |
|---|---|
| 0x00 / 0x04 | NNS1 能力 `0x4e4e5331` / 宽高 |
| 0x08 | start=1、soft reset=2、重新装模型=4、提交模型=8 |
| 0x0c | busy、输入 ready、输出 valid、模型有效、fault、完成、last |
| 0x10 / 0x18 | 输入 / 弹出输出 RGB，R 在最低字节 |
| 0x20 / 0x24 | 模型配置地址 / 数据 |
| 0x28 / 0x2c | 核计算 cycles / 完成帧数 |
| 0x30 / 0x34 | 输入 / 输出像素数 |

物理地址为新工程的 `0xA0030000`。只有同时存在配套设备树 `neural-style@a0030000` 和 NNS1 固件才允许探测；旧镜像测试已确认程序在访问新寄存器前拒绝执行。输入 / 输出的文件格式为八通道对齐，首末层只有三个 RGB 通道有效，其余为零填充。每帧有 **15,360 个有效 RGB 像素 / 46,080 个有效通道值**，HWC8 格式总计 122,880 字节。

## 首版显示链路与控制（历史记录）

```text
ARM 游戏逻辑 → RasterIX 光栅 / 纹理 / 深度 / 混合 → GPU RGB565 400×240
  → SNP1 独立完整帧快照 → ARM 只读取所需 192 行、整数缩到 160×96
  → [cpu-int8: A53 三层 CNN | pl-int8: PIO → FPGA 三层 CNN → PIO]
  → ARM 放大到 800×480 → PL HR 双槽 → 帧边界切换 → RGB LCD
```

训练只在电脑进行。`pl-int8` 分工中 CNN 推理全部在 FPGA，ARM 仍负责帧搬运和缩放；该首版 PIO 接口用于接通与验证，尚非直接 PL 视频流 / DMA 高吞吐方案。

新工具与 FSR 共用后处理锁。先启动游戏，等实际产出帧后再启动神经处理，否则会与游戏初始化设置显示模式互斥。神经处理结束会恢复先前显示模式。既有 `rix-games --style poster/sepia/binary` 仍只代表固定配色，不能据此启用神经网络。

当前帧取回并释放租约后，立即异步请求下一帧快照，与当前帧的 CNN 和显示处理重叠。下一次读取仍验证 token、READY 与租约未过期；退出或保持最后一帧之前会取消并释放预取。SIGTERM 在 CNN 帧边界结束，仍保留硬件错误和超时检查。

已经安装并完成 FPGA 板测的单命令入口（时限结束与 SIGTERM 退出均已验证）：

```sh
rix-neural-games neverball --style anime --backend pl-int8 --seconds 60 --autoplay
```

`--style oil` 选择油画，`--backend cpu-int8` 选择 ARM 对照实现，默认后端为 `pl-int8`，没有自动回退到 CPU。入口也支持 `tuxracer / neverputt / quake / quake3`，原游戏启动器保持不变；本轮真实连续神经处理和退出验证使用 Neverball，其余游戏未逐一完成神经画质验收。该入口等待自身游戏完成显示初始化并实际呈现至少三帧，再启动神经处理，结束时先释放后处理，再 WM_DELETE 关闭游戏；旧固件会在启动游戏前拒绝。

需要分开控制时，底层 ARM 实验用法：

```sh
rix-games neverball --autoplay
# 另一个终端：游戏实际开始呈现后运行
/opt/rasterix/neural-style/bin/rix-neural-style \
  --model /opt/rasterix/neural-style/models/anime.cnn \
  --backend cpu-int8 --live --seconds 30
```

`oil.cnn` 对应油画学生。当前 SD 已安装配套 NNS1 镜像，旧镜像会拒绝 `--backend pl-int8`。

PIO 的对照程序为 `bin/rix-neural-style-serialized`。优化版本保持每个输出像素的 valid 握手，仅将逐像素全系统 DSB 改为传输阶段边界屏障；该地址在配套 ARM64 内核中为 Device nGnRnE 映射。真实同板、同模型、同输入，交替两版本、各五个有效样本（排除预热），两种模型均逐位正确：耗时中位数约 **40.62 → 32.89 ms**，降低约 **19%**；这包含 PIO 和 FPGA 计算，不含装载模型。详见 `pio-benchmark.json`。

### 首版整条链路的实际耗时

| FPGA 实时试验 | 油画 | 动漫 |
|---|---:|---:|
| 处理帧数 / 时间窗 | 25 / 6.05422 s | 25 / 6.21764 s |
| 神经显示 FPS | 4.12935 | 4.02082 |
| 平均快照获取及复制 | 103.15 ms | 106.55 ms |
| 平均 PIO + FPGA 推理 | 33.07 ms | 32.98 ms |
| 平均放大、写回及换页 | 97.49 ms | 100.82 ms |

其余时间包括 RGB 转换、缩小、诊断文件写入等。两个时间窗均启用输入 / 输出 / 显示帧落盘取证；与 ARM 窗口不是严格同一时刻的游戏场景，不据此宣称整链固定百分比加速。CNN 核 18.432 ms 也不能当作整条链路帧率。当前仍主要受 A53 Device 内存取帧、放大和 HR 写回限制，尚未达到流畅游戏所需的神经显示帧率。

### 显示链第二轮优化，2026-10-20

同一块板、同一次 Linux 启动，用相同 Neverball 自动操作和两组权重复测。优化前这次重测为油画 4.16060 FPS、动漫 4.13217 FPS；最终部署版为 **8.56057 / 8.52362 FPS**，约为原来的 **2.06 倍**。各自均为独立游戏运行中的六秒窗口，包含诊断落盘，不能把不同瞬间的画面当作严格同帧 A/B。

| 最终 FPGA 显示链 | 油画 | 动漫 |
|---|---:|---:|
| 处理帧数 | 52 | 52 |
| 平均快照读取及剩余等待 | 46.77 ms | 47.13 ms |
| 平均整数输入缩小 | 1.33 ms | 1.31 ms |
| 平均 PIO + FPGA 推理 | 32.84 ms | 32.96 ms |
| 平均整数显示放大 | 9.18 ms | 9.22 ms |
| 平均 PL DDR 写回 | 8.11 ms | 8.10 ms |
| 平均帧边界换页等待 | 15.52 ms | 15.62 ms |

本轮只修改用户态，启动文件、RTL、网络结构和模型权重保持原摘要。缩小的中心坐标恰为四分之一格点，放大为五分之一格点；用预计算系数、带符号整数舍入和可复用行缓冲替代逐像素浮点及重复分配。主机与 A53 上的 14 组随机、全色域和极值图像，约 1,785 万个数值均与原版缩放一致。读取跳过 48 条不参与插值的行，PL 读取量由 384,000 减至 307,200 字节。写回采用显式的成组 Device 内存访问，保持阶段屏障和双槽换页协议。

固定数据的独立读写基准在空闲 GPU、同一非显示 HR 槽上交替执行两版，排除一次预热后各五次，全部写入后都完整回读：1,536,000 字节写入中位数 **15.25 → 7.90 ms**，快照读取 **63.22 → 48.38 ms**。这两个受控结果只代表读写阶段，不包含真实游戏快照等待；记录为 `report/neural-style/frame-io-benchmark.json`。

最终实板证据为 `report/neural-style/cnn_final_vgafsfq/host-verification.json`：主程序 SHA 与实际安装的 `80aae9…20f74` 相符，两种 CNN 输出均与 NumPy 整数参考一致；各自额外完整回读 1,536,000 字节显示缓冲，并核对 6,000 个实际 LCD 采样；快照重试、过期和残留租约均为零。优化汇总见 `report/neural-style/frame-optimization.json`。首版证据另存于 `initial-release-evidence/`。

正式入口关闭诊断落盘后，动漫模式连续运行约 60 秒，共处理 **584 帧，平均 9.72796 FPS**，见 `frame-continuous.json`；该窗口与上表取证窗口的配置、时长不同，分别报告。ARM / FPGA 两种后端的时限结束和 SIGTERM 退出均通过，退出后没有残留游戏、神经进程或快照租约；五类 GPU 错误为零，27 个已安装文件均与当前清单一致。整体工程检查 **38/38**、本轮优化检查 **16/16** 通过。未改变网络容量或训练权重，画质验收仍为 `false`。

## 验证与构建

* `prepare_neural_style.py` 固定上游提交和权重 SHA256；不执行 torch.hub，权重以 `weights_only=True` 装载。
* `neural_style_reference.py samples/train` 运行真正教师并训练两个学生，使用项目内独立 PyTorch CPU 环境。
* `prepare_cnn_vectors.py` / `integer.py` 生成训练权重与独立算术压力向量，规范 RIXCNN1 模型格式。
* `run_cnn_sim.ps1 -Full`：油画、动漫整帧，随机输入停顿、输出背压、重复帧、带符号饱和、错误 TLAST、不完整模型、运算中模型隔离与复位；AXI 分离握手、响应背压和读取退休测试。
* `build_neural_style_cpu.sh`：WSL 主机与 AArch64 编译；主机四组输出逐字节对照黄金参考，并构建缩放兼容性自检与 PL DDR 读写基准。
* `create_neural_style_board.tcl` / `build_neural_style_board.tcl`：独立 `build/vivado_neural_style`；沿用现有 GPU / 快照 / CDC / 时序发布门槛，增加 CNN 源文件一致性与 DSP 数量检查。
* `prepare_neural_style_dtb.py` / `package_neural_style_boot.ps1`：独立产物；PS 初始化必须与可启动版本字节一致，重新检查 U-Boot 控制 DTB 和实际 BOOT.BIN 的 PL payload。

板端 CPU 完整证据为 `report/neural-style/cpu_baseline/host-verification.json`，原始压缩回读 SHA256 为 `fd321bedab827d2bd753009b262c72b1cb0409b149d237ee2de270c365dabf00`。两种处理分别有 122,880 个 INT8 值与 NumPy 独立对照，以及 6,000 个 LCD 采样与实际输出帧对照。Neverball 60 秒正常 WM_DELETE 退出，五类硬件错误为零。首次测试的游戏初始化与后处理锁冲突已修正为等待真实呈现计数；失败日志保留，未当作通过证据。

板端 FPGA 当前完整证据为 `report/neural-style/pl_live/host-verification.json`；压缩回读 SHA256 为 `701715e1ccd54241328e77112810c96a529b157990c03ab9163849fde17ed718`。两种 CNN 均验证 15,360 个有效 RGB 像素（HWC8 含对齐零通道共 122,880 字节）与 NumPy 一致，以及 6,000 个实际 LCD RGB565 采样与完整显示输出帧一致。核心计数每帧均为 1,843,200，无快照重试或过期；Neverball 60 秒正常退出，五类硬件错误均为零。实际 LCD 的 FPGA 神经输出如下，同样是不同时间的场景，非同帧 A/B：

![FPGA 神经网络实际 LCD 采样](../report/neural-style/pl_live/actual-lcd-comparison.png)

## 启动包、实际 SD 与回退

新工程和产物均独立保存在 `build/vivado_neural_style`、`build/neural-style`，原 `build/postproc-touch` 产物未覆盖。PS 的 `psu_init.c/h` 与可启动版本字节一致；实际 BOOT.BIN 中的 U-Boot 控制 DTB、PL payload、XSA 内嵌配置均已核验。

| 实际 SD 文件 | SHA256 |
|---|---|
| BOOT.BIN | `92d8dbb16f3360694eeca87fe0bb0864d672c79ffc92cb67929f49b4d78bbc65` |
| system.dtb | `303cc95130783bc72d2d0249515db3a2b96d08ab49af25737ec55be524a8cb34` |

原配套文件保存在 SD 启动分区的 `rasterix-neural-backup-20261020/`，原 BOOT 摘要为 `7a7adaa4f621eba8bb654f2b54524f91353e25392bb2fcb0e9ac04d3028e9f86`、原 DTB 为 `45e2e11f03be69c663190806a51829c068fbde953827598bc4005a5ed88c1419`。更新前 / 后、回退副本、正常重启后所有已安装程序和模型均完成 SHA256 对照；本次是正常 Linux 重启验证，没有声明物理断电冷启动验证。板端 RTC 仍为旧日期，版本识别使用 boot ID、能力标识和内容摘要。

第一轮单核优化运行包 `neural-style.tar.gz` 为 **264,357 字节**、SHA256 `aec2b38a15ef6bd536e43820ca9ed2ea8c35c032e2c391cd93a929ba8fe541d8`；该轮 AArch64 工具为 `80aae9bf3107e1bdb56361ca3fe6ec5cc8694f267ffdbcf4fe88309985920f74`，已安装至 SD 根文件系统。优化前工具 `6f4144…98576` 随包保留为 `bin/rix-neural-style-pre-frame-opt`，需回退用户态时先停止神经处理并核验该摘要，再原子替换主程序。启动传输包仍为 **2,667,854 字节**、SHA256 `105ef9ae7091259012ebfddc587340ae2df74dbc5f715e0489ba0c3eb64695ed`，均经 JTAG 分块及整包摘要验收；本轮无需更换启动包。

实际板端小网络 LCD 采样如下，两幅来自同一游戏的不同时刻，不能当作严格同帧画风 A/B：

![A53 实际神经处理 LCD 采样](../report/neural-style/cpu_baseline/actual-lcd-comparison.png)

## 后续优化重点

CNN 整机时序、上板逐位对照和入口生命周期已完成，取帧、推理、显示耗时也已分开测量。搬运主导当前帧率，应将输入缩小、CNN 和输出写回逐步迁入 PL / DMA；不能只提高 DSP 数量并推断整条链路变快。

本轮整数化与预取后，取帧仍约 46 ms/帧，PIO + CNN 约 33 ms/帧。下一项硬件优化应优先考虑直接在 PL 缩小输入并传给 CNN、将网络输出送往显示路径，减少 ARM 往返；这些更改尚未实现，当前仍使用已验证的 PIO 运行包。

配套板端向量、真实游戏 / LCD、PIO 对照、入口生命周期及文件完整性脚本一并安装在 `/opt/rasterix/neural-style/bin/neural-*.py`，便于正常重启后复验。最终工程性验收汇总在 `report/neural-style/acceptance.json`；其中 `quality_acceptance: false` 明确保留当前画质原型的边界，不将像素一致性当作画质通过。

画质需扩大感受野、增加游戏帧与连续帧训练，按样张决定容量；保留未见场景测试和文本 / HUD 可读性检查。PC 教师可作为质量上限参考，小学生当前只是可部署的功能原型。

许可：PyTorch 示例保留 BSD 条款；PyTorch AnimeGAN 实现保留 MIT 条款，同时保存 [原始 AnimeGANv2 的非商业使用说明](https://github.com/TachibanaYoshino/AnimeGANv2#license)。当前作为个人非商业实验，不将这些权重描述为无限制商业素材。
