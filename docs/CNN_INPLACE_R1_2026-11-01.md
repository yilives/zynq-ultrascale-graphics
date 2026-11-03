# 原网络 CNN 存储优化 r1

2026-11-01。按用户“保留原有网络”的选择，实验保留三层 3×3、3→8→8→3、INT8、160×96 输入，以及原动漫/油画权重。新调度仅改变特征存储和写回时机。**独立核心、整机布局布线、配置审计及临时上板回归均已通过，已恢复原位流和清晰菜单，未采用为默认。** 后续 [实机记录](CNN_INPLACE_R1_BOARD_2026-11-01.md)包含 36 帧 A/B/A、Neverball 的 150 帧 CNN 呈现和 LCD 采样。

## 实现与实际成本

新核只保留一个整帧特征库，将量化输出暂存在两行循环缓冲。完成输出行 y 后，旧输入行 y−1 的所有窗口消费者已经结束，随后把待写结果覆盖回旧行；末尾再写回最后一行。卷积读取与整行写回分阶段执行，共用单端口同步帧 RAM。三层运算、复制边界、舍入、ReLU 和饱和均保持原样。

```mermaid
flowchart LR
    F[单整帧 INT8 特征库] -->|卷积阶段读取| M[原 64 路 MAC]
    M --> Q[原整数舍入与饱和]
    Q --> R[两行待写缓冲]
    R -->|旧行最后一次使用后写回| F
```

| 独立核心，统一 100 MHz 约束 | 原核重新实现 | 新核已路由 | 变化 |
|---|---:|---:|---:|
| LUT | 3,956 | **3,962** | +6 |
| FF | 1,827 | **1,904** | +77 |
| BRAM Tile | 64 | **33** | −31 |
| DSP | 65 | **65** | 0 |
| Setup WNS | +2.559 ns | **+2.382 ns** | 均满足内部约束 |
| Hold WHS | +0.044 ns | **+0.042 ns** | 均满足内部约束 |

这里是同工具、同约束、同芯片的独立 OOC 对照。已有 v23 完整工程内的 CNN 是 **55 BRAM Tile**，不是本次对照的 64。BRAM 级联/深度映射随时序约束和上下文改变，不能把“省 31”直接扣到旧整机。随后完整工程布线得到新 CNN **28.5 Tile**，相对原 55 实际回收 **26.5 Tile**，整机从 216 降到 189.5；完整工程数据如下。

OOC 报告的内部路径 setup、hold、pulse-width 均通过，无不受约束的内部端点；未设置顶层时钟来源位置，也没有覆盖整机接口输入/输出到达时间，不能替代顶层时钟偏斜、跨模块时序和整机验收。

默认尺寸的 RTL 周期为：

```text
原核：27 × W × H + 18        = 414,738 周期
新核：30 × W × H + 21 × H    = 462,816 周期
100 MHz 下：4.14738 → 4.62816 ms，增加 0.48078 ms
```

这包含逐行流水排空和同步行写回，不含输入装载、PIO 输出、ARM 融合或显示等待。它不是游戏 FPS 测试，也未接入 CNN＋FSR 整条链路。本次以少量额外核心时间换取存储余量，后续传输/融合优化可利用该余量。

## 验证

已完成修正版 RTL 测试：

- 7×5、1×1、7×1、1×5、2×2、160×96 六种尺寸，共 **40 帧**。
- 全尺寸含六帧真实游戏输入、重复帧、两套实际权重及极值压力模型。
- 全部三层共 **461,736 个 64-bit 特征向量 / 3,693,888 个 INT8 通道值**与独立 NumPy 参考逐值一致。
- 检查输入间断、输出背压与 TLAST、模型所有权、缺失/提前 TLAST、加载/计算/新复制阶段复位及后续恢复。1×1 不执行无意义的“提前末尾”用例。
- 每次帧 RAM 访问均检查读取与写回不重叠。

新 AXI 适配器另测 7×5 与 160×96：共 **30,860 个 RGB 像素**，原子端口和旧数据端口共享同一退役路径，像素弹出数与读取数匹配；无效读不弹出，R/B 背压期间响应稳定。全尺寸测试包含 567,228 次事务和 50,133 次带背压读取。

已路由功能网表的全尺寸真实输入仿真已通过，全部 **15,360 个 64-bit 输出向量**与参考一致，周期也是 462,816。[独立核心验收](../report/neural-style/inplace-r1/acceptance.json)已通过并绑定源文件、日志、报告和检查点哈希。此项不带 SDF 时序回标；时序另由 OOC 静态报告检查。

## 失败原型与修正

第一版 RTL 的逐值测试通过，但 Vivado 将整帧数组展开为大量 LUTRAM。该版本不采用，源码保存为 `report/neural-style/inplace-r1/prototype-unmapped.sv`，原综合日志和已生成的检查点保留；确认错误映射后停止了其路由进程。

修正版把帧存储隔离成明确的同步单端口 RAM，并保留明确的状态编码。综合后整帧存储实际映射为 32 BRAM，待写行缓冲 1 BRAM。不能仅凭 `ram_style="block"` 或数组容量认定映射成功。综合的早期常量输出提示也不能替代最终网表检查，因此额外运行完整功能网表仿真。

## 兼容与部署边界

| 项目 | 本实验约定 |
|---|---|
| 核心标识 | `NIP1`，`0x4e495031` |
| 0x38 预期周期 | `30*WIDTH*HEIGHT+21*HEIGHT`，默认 462,816 |
| 适配器 ABI | 3.1，`0x00030001` |
| 默认能力 | 13：流水线、原子输出、原地存储 |
| FPGA 五倍放大能力 | 默认关闭声明，只有完整工程明确配对时才设置 `NEURAL_SCALE5X=1` |
| 权重包 | 继续使用原 `RIXCNN1`，无需换权重格式 |

旧运行时只接受 NNS1/NNS2 及旧周期，**不会直接兼容 NIP1**。本次构建下述独立运行时，显式识别新硬件和周期，不冒用旧硬件标识。生产运行时、设备树、菜单包及默认位流保持原样；只对独立 RAM 候选作临时上板试验，普通菜单未开启 CNN。

配套实验运行时为 `build/neural-style/inplace-r1/runtime/rix-neural-inplace`，已在开发板 `/tmp` 独立执行，未替换生产安装。它同时识别旧 NNS1/NNS2 与新 NIP1，对尺寸、能力、ABI、预期周期进行校验，保留原有传输和像素处理逻辑。21 项硬件描述校验、两风格共 8 个本地整数参考用例通过；六个原像素处理头文件字节保持不变。[运行时构建验收](../report/neural-style/inplace-r1/runtime/acceptance.json)保留构建阶段范围；实际 AArch64 执行见上述实机记录。完整工程的 `NEURAL_SCALE5X=1` 配对通过 7×5 AXI 测试，并在真实 LCD 链路确认能力为 15。

## 文件与重现

- [新核心](../src/rtl/neural/experimental/inplace_r1/rix_cnn_engine.sv)、[新适配器](../src/rtl/neural/experimental/inplace_r1/rix_cnn_axi.sv)。
- [RTL 测试](../sim/tb_cnn_inplace_r1.sv)、[AXI 测试](../sim/tb_cnn_inplace_axi_r1.sv)、[功能网表测试](../sim/tb_cnn_inplace_gate_r1.sv)。
- [向量来源](../report/neural-style/inplace-r1/vector-manifest.json)、[新核心路由资源](../report/neural-style/inplace-r1/candidate-banked/utilization.rpt)、[时序报告](../report/neural-style/inplace-r1/candidate-banked/timing.rpt)。

```powershell
python -B scripts/prepare_cnn_inplace_r1.py
./scripts/run_cnn_inplace_r1.ps1 -Full
./scripts/run_cnn_inplace_axi_r1.ps1 -Full
# 独立 OOC 的输出目录已存在时会拒绝覆盖，须用独立副本重现。
& F:/AMDXilinx/2026.1/Vivado/bin/vivado.bat -mode batch -nolog -nojournal -source scripts/cnn_inplace_r1_ooc.tcl -tclargs baseline
& F:/AMDXilinx/2026.1/Vivado/bin/vivado.bat -mode batch -nolog -nojournal -source scripts/cnn_inplace_r1_ooc.tcl -tclargs candidate-banked
./scripts/run_cnn_inplace_gate_r1.ps1
python -B scripts/accept_cnn_inplace_r1.py
```

旧 CNN 冻结源、默认两套权重、v23 FSR 位流和原生清晰菜单包均保留。当前风格目标仍未通过用户画质认可，本次存储优化不改变其视觉效果。

## 独立整机实现

已核对 205 个冻结基线输入，在独立 v23＋FSR 工程 [rix_cni1.xpr](../build/vci1/rix_cni1.xpr) 完成综合和布局布线。原工程未被打开或改写。BD 共 24 个组件，仅神经核参数增加明确的五倍放大配对声明；接口、信号连接和地址映射保持一致，见 [准备来源](../report/neural-style/inplace-r1/board/preparation.json) 和 [BD 复核](../report/neural-style/inplace-r1/board/preflight.json)。

| 完整工程，已布线 | 原 v23＋CNN＋FSR | r1 原网络＋FSR | 变化 |
|---|---:|---:|---:|
| CLB LUT | 64,901 | **64,730** | −171 |
| FF | 71,349 | **71,445** | +96 |
| BRAM Tile | 216 | **189.5** | **−26.5** |
| DSP | 325 | **325** | 0 |
| 其中 CNN BRAM | 55 | **28.5** | **−26.5** |
| Setup WNS | +0.306 ns | **+0.293 ns** | 均通过 |

新整机 hold 余量 **+0.012 ns**，pulse-width 余量 **+0.124 ns**。CNN 完整模块为 4,253 LUT、2,168 FF、28.5 BRAM、65 DSP；FSR 保留 78 BRAM、173 DSP，源代码未改动。当前约有 5,830 LUT、69,675 FF、26.5 BRAM Tile、35 DSP 的名义资源余额；BRAM 回收不等于解除 LUT、DSP、时序与布线限制。

来源：[整机资源](../report/neural-style/inplace-r1/board/utilization.rpt)、[逐模块资源](../report/neural-style/inplace-r1/board/utilization-hier.rpt)、[整机时序](../report/neural-style/inplace-r1/board/timing.rpt)。

完整验收见 [board/acceptance.json](../report/neural-style/inplace-r1/board/acceptance.json)，`whole_board_implementation_passed=true`。独立核心验收文件保留当时的单核范围，整机结果以此新文件为准。审计重新打开保存后的实现，不额外重载源码 CDC 例外，确认时序、CDC 和总线偏斜仍通过；65 个 CNN DSP 所属时钟为 `clk_pl_0`，周期 10 ns。随后分别从保存的实现和导出 DCP 重新生成配置数据，与候选 raw **三份逐字节一致**。

候选产物：

- [Vivado 工程](../build/vci1/rix_cni1.xpr)，已显式绑定新实验 RTL，原工程保持原样。
- [完整位流 .bit](../build/neural-style/inplace-r1/board/cnn_inplace.bit)、[raw .bin](../build/neural-style/inplace-r1/board/cnn_inplace.bin)、[已路由 DCP](../build/neural-style/inplace-r1/board/cnn_inplace_routed.dcp)。
- [独立 ARM 运行时](../build/neural-style/inplace-r1/runtime/rix-neural-inplace)，本地与实机验证通过，仅在开发板 RAM 中运行。

raw 为 **4,728,044 字节**，SHA-256：`37fe0a87465e6a4de9c0516530d8acabdfd415bbf48e8c971af76a477f4f6dde`。验收同时核对两套基准权重、原 v23 raw 与清晰菜单包的哈希，均保持一致。

整机生成与审计脚本为 [准备脚本](../scripts/prepare_cnn_inplace_board_r1.py)、[创建工程](../scripts/create_cnn_inplace_board_r1.tcl)、[整机实现](../scripts/build_cnn_inplace_board_r1.tcl)、[独立审计](../scripts/audit_cnn_inplace_board_r1.tcl)、[最终验收](../scripts/accept_cnn_inplace_board_r1.py)。首次重现应在独立工作副本执行，现有目录保留本次证据。运行时生成、构建和验收分别见 `prepare_cnn_inplace_runtime_r1.py`、`build_cnn_inplace_runtime_r1.sh`、`accept_cnn_inplace_runtime_r1.py`。

本实验已通过 Neverball→CNN→PL 五倍放大→LCD 的独立短测；未将 CNN 打开到普通菜单入口，也未实现 CNN→FSR 串联。24.57–24.93 帧/s 是该说明场景的 CNN 呈现吞吐，未形成稳定游戏 FPS 或新画质结论。原生清晰菜单、原 v23 位流和默认权重保留。
