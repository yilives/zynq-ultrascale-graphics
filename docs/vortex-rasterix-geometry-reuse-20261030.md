# Vortex 计算前端与 RasterIX 后端组合评估

日期：2026-10-30。这里评估的是 `vortexgpgpu/vortex` RISC-V GPGPU。

**后续原型进展：** 已固定官方提交50cb1745，完成几何设备程序的45组/54次SimX对照、四/双执行通道真实综合及双通道独立100MHz布局布线。双通道布线后为24,139 LUT /12 DSP /20 BRAM36等效；尚未完成Linux/游戏和整机集成。详见[原型实测报告](Vortex_图形前端原型实测_20261030.md)。

以下保留试验前的分析与判断，其中“尚未综合”等描述对应当时的评估阶段，不覆盖上述最新实测。

## 试验前结论

**值得作为共享执行架构的候选，但不能直接取一个“几何前端 RTL”接到 RasterIX。当前没有证明裁剪后的 Vortex 能放进本项目的剩余资源。**

Vortex 的可复用价值在于已经提供可编程 SIMT 处理核、编译器和设备内核执行机制。几何程序可以在 FPGA 中的这些处理核上运行，ARM 继续负责游戏逻辑。新增几何代码主要成为指令，而非逐个展开成新的硬件控制路径；这是一种与目前全量 C++ HLS 不同的实现方法。程序长度、执行周期、寄存器及缓存成本仍须核对，不能自动推出它更小或更快。

## 上游实际提供的前端

上游主干的图形路径先在设备执行 VS，再运行 `expand_k`、`setup_k`、`binning_k` 等程序。这些程序依赖 Vortex 的 SIMT 核、启动/调度和内存体系。[软件栈说明](https://github.com/vortexgpgpu/vortex/blob/master/docs/designs/graphics_software_stack.md)

特别注意：`expand_k` 接收的已经是 **VS 输出的裁剪空间位置和 varying**，本身不是模型视图/投影变换或固定功能光照实现。单独复制这个函数不能解决目前的 ARM 顶点计算迁移。[设备前端源码](https://github.com/vortexgpgpu/vortex/blob/master/sw/gfx/gfx_frontend_k.h)

处理器的取指/译码前端与图形几何前端也需要分开；只提取处理器前端不会得到完整几何运算功能。[处理核源码](https://github.com/vortexgpgpu/vortex/blob/master/hw/rtl/core/VX_core.sv)

## 与本项目的三种组合

| 方式 | 评估 |
|---|---|
| 直接把 Vortex 现有前端输出接 RasterIX | 不能直接连接：运行依赖、输出 ABI、属性平面和分区约定不同 |
| 裁剪 Vortex 计算核，执行 RasterIX 专用几何程序 | 值得优先做资源与功能原型；可保留原游戏/OpenGL状态层和 RasterIX 后端 |
| 整体替换为 Vortex 图形栈 | 会扩展到 GPU、驱动及图形软件栈迁移，不能当作本项目的直接接入或两周内确定交付方案 |

候选分工如下，尚未实现：

```
ARM：Java游戏逻辑、OpenGL状态、顶点提交
  → PL：裁剪后的Vortex SIMT核执行几何程序
  → 输出RasterIX兼容的三角形描述符/命令
  → 现有PL RasterIX：像素光栅、纹理、深度与混合
  → 显示
```

可选的程序复用途径也不同：复用 Vortex 的几何程序需要改输出格式并补齐目标固定功能语义；将 RasterIX 几何算法编译到 Vortex 核上则需要显式处理并行任务、跨块图元状态和每线程暂存，不能直接假定现有全局工作数组可被多个线程共享。

Vortex 的 `rast_prim_t`/分块缓冲是其自己的硬件契约，RasterIX 使用既有 `TriangleDesc` 和命令流。即使字段含义接近，也不能 `memcpy` 成兼容格式。[Vortex图形ABI](https://github.com/vortexgpgpu/vortex/blob/master/sw/common/vx_gfx_abi.h)

此外，上游 Mesa 设备路径对图元和 VS 翻译有资格检查，某些路径会回退至 llvmpipe。若本项目要求 ARM 不执行几何计算，必须监控并禁止这类静默回退，或自行提供对应 PL 程序。[驱动绘制路径及回退说明](https://github.com/vortexgpgpu/vortex/blob/master/docs/designs/vortexpipe_architecture.md)

## 面积判断：目前未知

上游配置允许设置核数、warp数、线程数及扩展；当前主干基础配置列有一核、四warp、四线程，并将 TEX/RASTER/OM/RTU/TCU 等扩展分别控制。[配置源码](https://github.com/vortexgpgpu/vortex/blob/master/VX_config.toml)

因此可以评估仅保留 RV32、FP32 计算能力与必要运行设施的配置，继续使用 RasterIX 的像素后端。**不能因配置中写着“一核”就断言小于25K LUT**：取指、调度、寄存器文件、LSU、缓存、启动与内存适配均有成本。

上游官方平台列表以 Arria/Stratix、Alveo 和 Versal 平台为主，未列本项目 AXU3EG。这个事实说明缺少即用的官方板级目标，不证明最小配置一定放不下。[项目说明](https://github.com/vortexgpgpu/vortex#specifications)

本项目无 FSR 底座之后剩余 32,510 LUT、203 DSP、145 BRAM36。约25K仍是预算目标，未获得一个完整 Vortex＋接口＋几何程序配置的 ZU3 综合报告。也不能把以前提出的2738 LUT纯算术组代理值当成Vortex核心面积。

## 建议的验证边界

1. 固定一个确有设备端前端路径的提交，不能混用旧论文资源数据和新主干图形实现。
2. 先做裁剪计算核及真实内存/启动适配的 XCZU3EG 独立综合，保留 RasterIX 工程与 PL FSR。
3. 最先运行矩阵变换、裁剪、三角形设置小用例，输出 RasterIX 格式，与冻结 CPU 参考核对。
4. 测每批周期、内存流量、启动开销及 MC 实际负载，再决定是否迁移完整几何功能。

本评估支持“先验证最小 Vortex 计算核＋RasterIX 后端”，不支持“已有现成前端可直接接上”“25K一定够”或“肯定比ARM快”等结论。本轮没有替换当前工程或启动全量移植。

## 补充：完整替换为 Vortex 前后端时，API 与预算如何变化

这是另一条候选路线：使用 Vortex SIMT 核及其 RASTER/TEX/OM 完成图形处理，移除 RasterIX 核。它可消除 Vortex 到 RasterIX 描述符的转换工作，但仍须完成应用 API、驱动、PS/PL 通信和显示集成，不能理解成直接替换一个 RTL 实例。

| 接口层 | 需要处理的工作 |
|---|---|
| Java MC / LWJGL 的桌面 OpenGL 调用 | 以保持游戏调用不变为目标；取决于下层是否提供兼容实现 |
| `libGL` / GLX、固定功能状态 | 替换当前私有 RasterIX 实现；验证上下文、显示列表、四边形、ARB 多纹理与同步/换页语义 |
| GPU 命令与着色器 | 使用 Vortex 的命令、状态与设备程序；此路线不再要求生成 RasterIX 描述符 |
| ARM Linux → PL | 为本板内存、AXI 控制/访存、缓存一致性与任务完成机制适配 Vortex runtime；不是修改游戏 API |
| 帧缓冲 → LCD | 将 Vortex 的颜色缓冲接入显示路径，不能假定原有帧桥输入格式直接兼容 |

当前核对的 Vortex 主干软件图形文档具体描述 Vulkan/lavapipe → vortexpipe 路径。它不足以证明已有适配本板、可直接供旧 LWJGL 使用的 OpenGL/GLX 栈。可评估 Mesa OpenGL 状态跟踪器接入 vortexpipe，或 OpenGL → Zink → Vulkan → Vortex。前者要检查驱动接入与状态/着色器契约，后者要核对 Zink 的 Vulkan 功能要求，两条路径都尚未在本项目验证。[Vortex软件栈](https://github.com/vortexgpgpu/vortex/blob/master/docs/designs/graphics_software_stack.md)、[Mesa驱动说明](https://docs.mesa3d.org/systems.html)、[Zink要求](https://docs.mesa3d.org/drivers/zink.html)

### 替换路线的名义资源账

依据冻结无 FSR 底座 `build/minecraft-java-125/no-fsr-base-r1/board/utilization_hier.rpt`：总计 38,050 LUT /157 DSP /71 BRAM36 等效；其中 RasterIX 核 12,891 LUT /154 DSP /35.5 BRAM36 等效（29 RAMB36＋13 RAMB18）。假设保留其他逻辑、仅扣除 RasterIX 核：

| 新 GPU 与新增适配可使用的名义余额 | 数量 |
|---|---:|
| LUT | 70,560 − (38,050 − 12,891) = **45,401** |
| DSP | 360 − (157 − 154) = **357** |
| BRAM36 等效 | 216 − (71 − 35.5) = **180.5** |

这些是对现有报告的容量扣减，**不是 Vortex 综合结果**。原显示包装中的部分逻辑可能需替换，互连和帧缓冲适配也会改变资源。不能将整个 GPU 包装 17,951 LUT 全部扣除后，又把显示逻辑当作仍然免费存在。若继续使用整片预留10% LUT的筛选假设，新GPU及新增接口预算为38,345 LUT；这仍只是工程目标。

完整替换可用的面积比保留 RasterIX 的组合路线更多，但顶点与片元程序要共享 SIMT 执行资源。面积是否可收敛、MC固定功能是否兼容以及实际吞吐都未证明。合理的验证顺序是：固定配置与提交 → 最小完整图形配置的 ZU3 综合 → 离屏三角形/双纹理/深度混合 → OpenGL/GLX 与 LWJGL 探针 → 实际 MC。本轮仅补充评估，没有启动新构建或改变部署。
