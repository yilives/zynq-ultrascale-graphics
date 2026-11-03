# Java 1.2.5：完整 256×256 纹理支持

本次目标是让 RasterIX 真实上传、寻址和采样完整的 256×256 纹理。游戏仍按现有 400×240 渲染尺寸运行，LCD 为 800×480。原版客户端 JAR 保持不变；纹理探针的上传和像素校验必须通过。原版菜单日志中的上传队列分配失败另列为未解决项，不能用探针通过代替完整游戏兼容验收。

**R4 板测已通过：完整基础层、两种编码及跨边界更新共 196,608 个像素，板上与主机独立复核均为零差异。R8 已取得完整的原版运行时主菜单；尚未验收为可玩世界。**

**R5 又验证了原始 title/mojang.png：未经修改的 256×256 RGBA PNG 在真实硬件上传与采样后，65,536 个像素在当前 RGBA4444 色彩精度下全部匹配。** 空间尺寸保持完整；本轮没有验证 alpha 混合。官方 JAR 中 PNG 的 SHA-256 为 a94396c0758dad0b6daef0ac7f08bb182d54e49d4f431ffd573d494682c91c5d，与板上读入数据一致。

**后续 R15 已修复快速换页握手：原版客户端 544 次 GLX 调用对应 544 个 GPU 完成帧，连续 121 次清屏和完整 96,000 像素红帧检查通过。** R9/R10/R13 的历史失败仍保留。详见 [握手修复、实机对照与双 TMU 资源评估](minecraft_java125_swap_fence_2026-10-26.md)。Java 多纹理能力、显示列表及可玩世界仍未完成。

## 问题与修改

原 v23 使用片内整张纹理存储，最大尺寸为 128。Java 1.2.5 初始化上传 256×256 的 Mojang 图片时，驱动实际返回 GL_INVALID_VALUE (1281)，因此此前只验证了 JVM、AWT、LWJGL 和 GLX。

本次启用 RasterIX 已有的外部纹理存储路径，保留 PS DDR 中完整的资源页，通过纹理 MMU 和片内缓存读取。驱动与硬件共同使用 256 的最大纹理尺寸，现有 DMA、显示缓冲布局以及 CNN/FSR IP 保持原接口。

~~~mermaid
flowchart LR
  J[Java / LWJGL] --> GL[私有 256 配置 libGL]
  GL --> DDR[PS DDR 完整纹理页]
  DDR --> MMU[FPGA 纹理 MMU]
  MMU --> C[片内纹理缓存]
  C --> TMU[FPGA 采样与光栅化]
  TMU --> FB[400×240 帧缓冲]
~~~

修改生成在独立 Vivado 工程 build/vivado_java256_cache/rix_java256_cache.xpr。上游 TextureReader.v 的 FIFO 输出连接含两个常量，严格 Verilog 仿真器不接受；私有副本用两个未使用的 wire 接收这些输出。197 个硬件及配置输入的 SHA-256 记录在 texture256-cache/source-freeze.json。

## 已完成的本地验证

GPU 单独综合的比较如下。这里不能代替整机布局布线结果。

| 项目 | 原 GPU | DDR 纹理缓存 GPU |
|---|---:|---:|
| LUT | 13,366 | 14,039 |
| BRAM Tile | 54.5 | 42.5 |
| DSP | 84 | 84 |

实际 XSim 验证覆盖：

- 全部 65,536 个基础层纹素、全部 21,845 个 mipmap 纹素。
- 四邻域采样、边界回绕、最近邻采样、非连续物理页映射。
- 热缓存后的纹理切换失效、乱序地址、AXI 地址/数据停顿和输出反压。

最近一次实际结果为 **95,575 组请求、13,678 次 AXI burst、1,593,767 周期，PASS，源图无空间重采样**。这是模块仿真的计数，不能换算为游戏帧率。

整机已完成布局布线，保留 CNN 与 FSR：

| 资源 | 实际使用 | 器件总量 | 占用 |
|---|---:|---:|---:|
| LUT | 65,636 | 70,560 | 93.02% |
| FF | 71,940 | 141,120 | 50.98% |
| BRAM Tile | 204 | 216 | 94.44% |
| DSP | 325 | 360 | 90.28% |

建立、保持、脉宽余量分别为 +0.113 ns、+0.010 ns、+0.124 ns，路由错误与 Critical CDC 为零。保留了原 v23 同样的 BD 41-1267 告警：PS 的 PL DDR 访问窗与 FSR 的本地地址视图采用不同偏移；本次没有改变该映射。DRC 中仍有流水线等 Warning，不能表述为无告警。

## 板上验收方法

Java256TextureProbe 在真实 RasterIX 上分两条 256×128 区域按 1:1 绘制并回读，合成完整图片。采用两种纹素颜色编码，避免现有帧缓冲每通道 5 bit 的颜色精度隐藏某一寻址位的错误；两次编码合起来覆盖全部 16 个地址位。

随后更新跨越 x=128、y=128 的 16×16 区域，并检查其他区域保持原值。三轮累计比较 196,608 个像素，检查 GL 错误，保存原始 PPM。0xffdf 掩码只忽略 RGB565 传输中帧缓冲没有保留的绿色最低位。

试验程序贯穿持有游戏及后处理互斥锁，先验证候选位流，再运行纹理测试及原版客户端，最后用独立事务恢复原 v23 位流并验证。候选驱动必须看到当前启动周期的真实加载凭据和新硬件的纹理能力标记。最终版在 Windows 逻辑测试与 Linux 实际文件锁环境下均完成 8 项故障/控制检查。

R1 因试验脚本重复申请后处理锁而退出，实际恢复成功。R2 保留了像素失败结果及恢复失败记录：回读发生在交换缓冲前，而该驱动读取前缓冲；原光栅器在像素边角计算插值；状态采样对象还持有显示设备，阻止卸载模块。保留证据后执行正常 Linux 重启，没有删除恢复保护记录。随后分别修正为呈现后读取前缓冲、在像素中心计算覆盖/属性，以及恢复前关闭状态设备。

像素中心改动只进入私有 Java 驱动，真实 C++ 描述符回归检查覆盖 65,536 个坐标及分区起点。原 ClassiCube 驱动保持原摘要。当前驱动仍有固定前缓冲读回等接口边界，本轮没有宣称完整桌面 OpenGL 兼容。

R4 的三个实际回读图中，最后一张如下，绿色方块是跨越 128 边界的更新区域：

![256 基础层与跨边界局部更新](../report/minecraft-java-125/texture256-cache/r4-board/attempts/java256-full-r4/texture256.png)

R5 直接从官方 JAR 读取启动 PNG，采用 GL_RGBA 上传和实际硬件的 RGBA4444 存储格式，在不启用混合的条件下逐像素对比原图在该格式下的量化值。回读按纹理坐标顺序拼接，未进行空间插值：

![原始 Mojang 256×256 RGBA 图片的真实回读](../report/minecraft-java-125/texture256-cache/r5-board/attempts/java256-full-r5/mojang256.png)

## 当前结论

完整 RGB565 基础层的上传、GPU 渲染、读回与更新，以及原始 Mojang 图片的 RGBA 上传与采样已上板通过。主机分别复核两组原始回读，共 262,144 个像素比较。mipmap 的完整寻址已通过 RTL 仿真，本轮没有把它列为完整板测通过项。ARM 运行 Java、GL 前端及顶点处理，像素采样与渲染使用 FPGA；编译配置没有启用软件像素渲染。

原版 1.2.5 实际运行约 25.71 秒并正常响应窗口关闭，退出码为零、无 OpenGL 异常和 DMA 错误，完成 36 次呈现。R4 在退出后保存到下面的彩色图。后续源码核对发现 Renderer::deinit 会先切换到默认 COLOR_BUFFER_LOC_0，因此该图属于销毁阶段的默认显示源，不能用于判定运行中的菜单质量。销毁前主菜单的取证缺口已在 R6～R8 补齐；世界与可玩状态仍未验收：

![退出后默认显示缓冲，不能作为运行时菜单图像](../report/minecraft-java-125/texture256-cache/r4-board/attempts/java256-full-r4/minecraft-source.png)

日志明确出现显示列表接口未实现、glFlush 未实现和纹理上传队列分配失败；也缺少可选的 JInput 原生库与 OpenAL，离线资源下载失败。这些缺口仍需逐项处理。R8 已修复静态菜单尺寸，R9 已验证一次真实鼠标输入；接下来需要落实 glFlush/glFinish、显示列表与多纹理语义，再验收小世界，最后测量稳定运行帧率。仅增加缓存大小或隐藏日志不能作为通过依据。

R4 结束后原 v23 已实际重新加载，旧运行凭据按原字节恢复。ClassiCube＋PL FSR 的 12 秒恢复检查完成 598 帧 FPGA 后处理，全部硬件错误为零、快照和进程均正常退出。约 10 秒有效窗的后处理约 59.69 FPS，这只是恢复短测，不替代此前视距 32 的长期稳定性结论。Java 没有有效游戏 FPS。

R5 的 RGBA 追加验证同样完成真实位流恢复，并再次通过 12 秒基线检查、598 帧 FPGA 后处理。最终状态为 v23、POST 模式 1、无快照占用或过期、无遗留游戏进程及硬件错误。两次板测与主机复核的 PNG 均保留原始回读数据，文档中的 PNG 仅作无空间插值的格式转换。

## 工程、复现与证据

### R6～R8：实际主菜单与窗口尺寸修复

R6 在 Renderer 销毁前、所有上传及显示队列排空后，直接回读最后一次完成的 GPU 前台帧。其 frame=47，35 次应用换页；销毁后默认缓冲对应 frame=48。此前退出后读到的噪点属于默认缓冲，不能用于判断运行时菜单。新增取帧只用于诊断，不改变渲染计算。

R7 的 AWT、LWJGL、Minecraft 内部尺寸及菜单尺寸在两次采样中均为 **400×174**。原先请求的 Frame 为 400×272，受到 X11 窗口管理器装饰及工作区限制；FPGA 仍输出 400×240，造成顶部 66 行残留和菜单下移。R8 通过标准 AWT 全屏窗口使上述四项尺寸均为 **400×240**，没有修改官方游戏 JAR，也没有跳过纹理或 GL 错误。

| 对照 | R7 窗口模式 | R8 AWT 全屏 |
|---|---:|---:|
| 实际 Canvas / Display | 400×174 | 400×240 |
| 游戏 / GUI 逻辑尺寸 | 400×174 | 400×240 |
| FPGA 前台帧尺寸 | 400×240 | 400×240 |
| 完成帧截图 | 顶部残留、按钮裁切 | 菜单各按钮及底部文字完整 |
| 正常退出并恢复 v23 | 通过 | 通过 |

修复前 R6 的实际帧：

![修复前的真实 GPU 菜单帧](../report/minecraft-java-125/texture256-cache/r6-board/minecraft-front-before-reset.png)

修复后 R8 的实际帧：

![AWT 全屏后的真实 GPU 菜单帧](../report/minecraft-java-125/texture256-cache/r8-board/minecraft-front-before-reset.png)

图像均来自 GPU RGB565 前台缓冲，仅转换为 PNG，没有空间插值。R8 frame=47，原始数据 SHA-256 为 `8cd8e2bb4761f6599959af27cc652dc0164572b40c4446b5092a3529e65b566c`。RGB 与原始 Mojang RGBA 纹理测试再次通过，正常关闭及真实 v23 恢复通过，硬件错误为零。

视觉复核确认主菜单 Logo、五个文字按钮、语言按钮及页脚完整。全景背景边缘仍有轻微条带；400×240 帧缓冲小于原版 256×256 全景拷贝区域，区域外内容及相关 GL 兼容性仍需单独验证，不能称为完整桌面 OpenGL 兼容。25 秒启动窗口也不代表游戏 FPS，尚未验证世界生成和场景渲染。

证据包 `report/postproc_java256_r8_menu_evidence.bin` 为 216,834 字节，SHA-256 为 `316b461ac751b827b7dc680b3d3792f1c1fe30bceb989eeecf9db1a8a485fdd7`。含 R7 两次尺寸诊断、R8 原始帧、全部测试日志及加载/恢复事务。复核命令：

```powershell
python scripts/verify_java256_menu.py --sha256 316b461ac751b827b7dc680b3d3792f1c1fe30bceb989eeecf9db1a8a485fdd7
```

机器检查结果见 [menu-acceptance-r8.json](../report/minecraft-java-125/texture256-cache/menu-acceptance-r8.json)；图像内容的视觉判断以本节为准，机器脚本仅核验尺寸、帧身份、原始字节和恢复事务。

### R9～R10：单人菜单输入与未通过的快速提交检查

R9 通过 Java Robot 发送标准 X11 鼠标移动、按下和释放事件，点击原版 Singleplayer 按钮，没有用反射直接调用游戏的菜单切换函数。反射只读取诊断状态：GUI 从 `xt`（主菜单）切换到 `mw`（选择世界），两次尺寸采样保持 400×240。没有生成世界或改动游戏存档。

![模拟鼠标后真实 GPU 前缓冲中的选择世界界面](../report/minecraft-java-125/texture256-cache/r9-board/minecraft-front-before-reset.png)

输入和截图取得成功，但严格的应用 swap 与 GPU 完成帧逐次对应检查**未通过**。R10 显式使用驱动已有的 `RIX_PRESENT_SYNC=1`、`RIX_PRESENT_STRATEGY=serial` 再测，同样未解决。串行模式保留为可选对照，不作为默认优化采用。

| 检查 | R8 仅主菜单 | R9 点击单人游戏 | R10 串行对照 |
|---|---:|---:|---:|
| 应用 GLX swap 调用 | 35 | 1,072 | 993 |
| 客户端期间完成的 GPU 帧，不含销毁默认帧 | 35 | 551 | 549 |
| 逐次帧对应检查 | 通过 | **未通过** | **未通过** |
| 最终截图对应 GPU 完成编号 | 47 | 563 | 561 |
| 正常关闭、真实恢复 v23、硬件错误为零 | 通过 | 通过 | 通过 |

R9/R10 的 `result.json` 中 `passed=true` 只描述板测运行器的纹理、输入观察、正常退出和恢复范围；独立 `menu-acceptance-r9.json` / `menu-acceptance-r10.json` 将新增的严格帧对应检查保留为 `passed=false`，复核命令返回退出码 2。原始取帧字节、尺寸和恢复仍可独立验证，失败断言没有被移除或转成通过。上述 25 秒窗口含 JVM 启动、慢速全景主菜单和静态选择世界界面，不能计算为游戏帧率。

原版 `es.class` 的初始化把两个纹理单元设为 33984/33985，即 GL_TEXTURE0/GL_TEXTURE1；`lr.class` 的光照贴图相关路径实际选择第二单元。当前硬件 `TMU_COUNT=1`，`glActiveTexture` / `glClientActiveTexture` 又缺少单元边界检查。这是进入世界前必须解决的独立兼容缺口。应先修正越界调用的 GL 错误及状态保持，再评估双 TMU 或等价的 FPGA 多遍处理，不能把第二单元静默映射到第一单元。

R9/R10 当时的后续顺序如下，其中第 1 项已经在后续 R15 完成，最新结果以链接的新记录为准：

1. 对 GPU 提交、命令执行、换页请求、显示桥应答分别计数，定位快速界面的帧数差异；串行对照已经证实单改运行策略不足以解决。
2. 修复上传队列满时的提交/重试，落实 glFlush/glFinish 的提交语义，再处理显示列表；现有原版菜单仍出现这些日志，不隐藏它们。
3. 完成多纹理能力及边界处理后，在 RAM 存档中尝试小世界，先验证图像与输入，再测真正的场景 FPS。

R9 证据包为 188,505 字节，SHA-256：`bf0d7b6b1c475cf712811e2f8e9bc311f85aa5a74bcbb6d47f96f957add647f1`；R10 为 188,315 字节，SHA-256：`445cd22320c35bd7201d6793b5f73929d23a6d86c49735d1f2e315febb3cc0dc`。两次选择世界截图的原始 RGB565 SHA-256 相同：`7b5a9a28f0005f1f4ceaceae304d20a8e9b4513d93c3b765272d70c5eaef7212`。

```powershell
# 两条命令均应返回退出码 2，并保留 swap_accounting_matched=false。
python scripts/verify_java256_menu.py --revision r9 --sha256 bf0d7b6b1c475cf712811e2f8e9bc311f85aa5a74bcbb6d47f96f957add647f1
python scripts/verify_java256_menu.py --revision r10 --sha256 445cd22320c35bd7201d6793b5f73929d23a6d86c49735d1f2e315febb3cc0dc
```

最终开发板恢复原 v23，旧运行凭据按原字节恢复，GPU 五个帧/队列编号归零、错误归零，POST 模式 1、快照占用为零，无遗留游戏进程。试验未更新 SD 启动文件。

- 独立 Vivado 工程：[rix_java256_cache.xpr](../build/vivado_java256_cache/rix_java256_cache.xpr)。
- 候选位流：[java256.bit](../build/minecraft-java-125/texture256-cache/board/java256.bit)，运行期临时加载，测试后恢复 v23。
- [本地报告独立验收](../report/minecraft-java-125/texture256-cache/local-acceptance-r4.json)、[R4 板测独立验收](../report/minecraft-java-125/texture256-cache/board-acceptance.json)。
- [原始 RGBA 启动图片独立验收](../report/minecraft-java-125/texture256-cache/mojang-board-acceptance.json)、[对应复核脚本](../scripts/verify_java256_mojang.py)。
- [硬件生成](../scripts/prepare_java256_cache.py)、[整机实现](../scripts/implement_java256_cache.tcl)、[缓存仿真](../scripts/run_texture256_sim.ps1)、[板测运行器](../linux/java_minecraft/run_java256_trial.py)、[像素中心修正及回归](../scripts/fix_java256_pixelcenter.py)。
- [主机逐像素复核与事务验收](../scripts/verify_java256_board.py)，原始图片、GL 日志、加载与恢复日志均保留在 report/minecraft-java-125/texture256-cache/r4-board。

R4 原始证据包 SHA-256：54638e30b4c5e9b2c03f4cbc0e245698a38243b405bd75ceacc41203dfe1e3ba。R2 失败证据单独保留，SHA-256 为 6895b696e7393f73bc13ca4ac230e196ace03b93daa3b3deaf59830e20cf3435。

R5 原始 RGBA 与恢复证据包 SHA-256：a5482ed9de293204d5221eb89881443f81800f9b9bb6e14dd4f662a158e25af2。复核脚本直接从官方 JAR 解出 PNG 作参考，不使用重新生成的替代素材。
