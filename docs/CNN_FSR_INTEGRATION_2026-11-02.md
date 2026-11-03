# CNN 风格化与 PL FSR 串联验收（2026-11-02）

已将 v8 较强漫画/版画、油画 CNN 与既有 FPGA FSR 串联，并完成静态整图、游戏 ABBA、LCD 采样及恢复验证。**CNN 卷积和 FSR 的 EASU/RCAS 都在 PL，400×240 风格细节融合在 ARM。** 没有在线 CPU FSR 回退，也没有修改网络、原 FSR 算法或构建新的 FPGA 位流。

## 当前链路

```text
ARM 游戏逻辑/几何前端 → RasterIX PL 光栅化 → 400×240 源帧
→ ARM 受保护快照/缩小到 160×96
→ PL 三层 INT8 CNN（v8 较强漫画或油画）
→ ARM 在 400×240 融合同帧亮度细节
→ PL FSR1 EASU12＋RCAS5：400×240 → 800×480
→ PL 显示双缓冲与 POST ACK → RGB LCD
```

现有 FSR 内核输入固定为 400×240，因此将融合从此前的 800×480 改到 400×240，随后用 FSR 完成两倍放大。原始 400×240 图像的亮度细节参与融合，CNN 的风格色调继续保留。输入 FSR 时按既有内核量化为 RGB565；输出为 XRGB8888。

FSR 使用已验收的 v23 Q6.18 定点近似算法，EASU 12 点和 RCAS 5 点。它是 FSR1 空间放大，未接入时间重建或新的神经超分模型。两套 CNN 仍为 **3→8→8→3、三层 3×3、INT8、160×96、1027 参数**，权重与 v8 相同。

## 同帧画面

下图左列为实际生成的 400×240 风格/细节输入，中列为同一输入的双线性两倍结果，右列为 PL FSR 结果。图中整幅数据由主机独立重算，SHA256 与板上完整回读数据逐帧匹配；实际 LCD 另做采样核对。图片为数据重建和缩略排版，非屏幕拍摄。

![同帧双线性与 PL FSR](../report/neural-style/cnn-fsr-r1/board-comparison.png)

![同帧一比一裁剪](../report/neural-style/cnn-fsr-r1/board-crops.png)

FSR 的锐化、轮廓变化可在 1:1 裁剪中比较；本次没有将效果主观认定为更好，也没有重新选择画风。普通菜单继续保留原生清晰显示。

## 实机性能

同一次 Linux 启动、同一个 NGR1 实验位流、Neverball Level00 介绍场景，每轮约 8 秒。漫画按双线性/FSR/FSR/双线性的 ABBA 顺序；油画另作双线性与 FSR 兼容检查。

| 场景/路径 | 完成帧 | 呈现 FPS |
|---|---:|---:|
| 漫画，双线性 A1 | 196 | 24.4581 |
| 漫画，PL FSR B1 | 199 | 24.5942 |
| 漫画，PL FSR B2 | 199 | 24.6739 |
| 漫画，双线性 A2 | 197 | 24.5413 |
| 油画，双线性 | 196 | 24.4381 |
| 油画，PL FSR | 198 | 24.4852 |

漫画按总帧数/总时长汇总为 **24.50→24.63 FPS**，约 +0.55%，属于这组短测中的小幅差异，不认定为明显游戏提速。六轮共呈现 **1185 帧**，其中 FSR 路径 **596 帧**。本场景的供帧仍约为 25 FPS，LCD 刷新率与产生新帧的速度分别记录，不承诺完整游戏稳定 60 FPS。

| 漫画每帧阶段，约值 | 双线性对照 | PL FSR |
|---|---:|---:|
| CNN 推理（含 PIO） | 9.3 ms | 9.3 ms |
| ARM 融合及可选软件双线性 | 15.5 ms | 5.7 ms |
| ARM 显示/中间帧写回 | 8.0 ms | 2.0 ms |
| PL FSR 加载 | — | 0.78 ms |
| PL FSR EASU＋RCAS | — | 8.2 ms |
| ARM 每帧写入字节 | 1,536,000 | 384,000 |

减少的是 ARM 承担的像素阶段及写回量，FSR 计算时间转移到 PL。表中是阶段墙钟耗时，不是整个 ARM 的 CPU 利用率。与旧版 800×480 细节融合相比，融合执行分辨率也发生变化，不能把不同流程的耗时当作同一算法的纯编译加速。

## 缓冲和控制

联合运行时持有共享后处理锁。SNP1 源帧先复制到 ARM 自有缓冲，CNN、融合和 FSR 按同一源帧号配对。融合结果写入原 FSR 静态测试已使用的独立 scratch：PL 地址 `0x21500000`，384000 字节；与 SNP1 的 `0x21400000` 及显示银行分离。

FSR LOAD 完成后才使用内部缓存，COMPUTE 仅写当前未显示的银行；AP_DONE、返回码和结果 tag 全部通过后，才提交 POST 银行切换。控制器沿用已验收 FSR 的完成/超时处理，收到退出请求仍排空正在执行的 AXI 事务。

旧 `rix-fsr-pl` 及其旧位流凭据保持原样。联合运行时使用 NGR1 专用、绑定当前 boot ID 和实际整份位流/来源 SHA256 的加载凭据；没有将旧 v23 凭据用于描述 NGR1。

## 正确性与证据

- 原 CNN 八组主机整数黄金向量继续通过；本轮两套权重未改。
- 400×240 融合通过主机 80003 项、A53 NEON **105507 项**直接插值/舍入/边界检查，包含量化舍入的完整有效数值范围。
- 四幅静态 400×240 输入分别验证 ARM 融合、双线性和真实 PL FSR，FSR 完整 **1,536,000 像素**的回读摘要与原 v23 算法黄金输出一致。静态 PL FSR compute 约 8.08–8.12 ms。
- 六次实时末帧共 **737280 个 INT8 值**与独立 NumPy CNN 结果一致；完整源图重算缩小输入也一致。
- 六幅 400×240 融合帧，共 **576000 像素**，独立重算摘要与板上一致。
- 三幅实际 PL FSR 完整输出，共 **1,152,000 像素**，使用未改的 v23 HLS 定点参考独立计算，SHA256 与实际 DDR 回读一致；三幅双线性对照另核对 **1,152,000 像素**。
- 六次实际 LCD RGB565 采样，共 **36000 点**一致；未取得物理 LCD 的全像素抓取。
- GPU 读写错误、超时、下溢、扫描错误、快照过期均为零；游戏与后处理正常退出，原位流和原生菜单恢复。

为缩短 115200 串口传输，验收包保留实际源帧、PL CNN 张量、LCD 样点及日志；可独立重算的中间帧和整幅输出采用实际回读 SHA256 核对。没有把主机生成的参考图描述为物理屏幕照片。

[独立验收 JSON](../report/neural-style/cnn-fsr-r1/acceptance.json)、[验收包](../report/neural-style/cnn-fsr-r1/evidence-thin.tar.gz)。验收包 485183 字节，SHA256 `09e16a5cef19d3018d4b484fc708f0164e251017306eee779936d9a5f8d750c5`。

## 运行入口与保留项

板上 RAM 中新增入口，默认使用 PL FSR：

```sh
python3 /tmp/rix-cnn-group-r1/cnn_fsr_play.py --style comic --seconds 30
python3 /tmp/rix-cnn-group-r1/cnn_fsr_play.py --style oil --seconds 30

# 同样的 400×240 风格/细节帧，改用双线性作对照
python3 /tmp/rix-cnn-group-r1/cnn_fsr_play.py --style comic --upscaler bilinear --seconds 30
```

入口校验既有静态验收和文件索引，正常停止菜单，临时加载 NGR1，运行后恢复原位流与清晰菜单。普通菜单的 CNN 风格选择开关仍未接入，本入口未设为开机默认。主机基础包为 `build/neural-style/cnn-fsr-r1/board/rix-cnn-fsr-r1.tar.gz`；演示附加包为 `build/neural-style/cnn-fsr-r1/demo/rix-cnn-fsr-demo.tar.gz`。

核心代码：`linux/neural_style/experimental/cnn_fsr_r1/native_style400.hpp`、`cnn_fsr_pl.hpp`、`stage_bilinear.hpp`；联合运行时为 `build/neural-style/cnn-fsr-r1/runtime/rix-cnn-fsr`，构建入口为 `scripts/build_cnn_fsr_runtime_r1.sh`。独立检查入口为 `scripts/accept_cnn_fsr_r1.py`。

本轮没有修改 RTL 或新建位流；测试复用此前已验收的 NGR1：**65058 LUT、71711 FF、189.5 BRAM、325 DSP**，其中 FSR 78 BRAM/173 DSP、CNN 28.5 BRAM/65 DSP。Vivado 工程仍为 `build/vcgr1/rix_cgr1.xpr`。旧硬件审计中的“尚未串联”描述其审计时的软件状态，本次软件串联结果以本页与新验收记录为准。

原模型、旧运行时、原 PL FSR 代码和位流均保留。SD BOOT.BIN、system.dtb 未在本轮写入；冷启动、miniDP 输出和其他游戏的完整 CNN＋FSR 连续运行不在本次验收范围。

默认 PL FSR 的简化入口另完成一次 6 秒漫画演示：149 帧、24.4888 FPS，`FSR_enabled=true`，正常恢复原位流与菜单。最终只读检查确认运行时、原模型、SD 启动文件哈希均保持预期。[最终状态与验收](../report/neural-style/cnn-fsr-r1/acceptance-final.json)。
