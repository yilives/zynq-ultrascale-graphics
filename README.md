# AMD_submission —— 提交材料总入口

> 全国大学生嵌入式芯片与系统设计竞赛'2026 · FPGA 创新设计赛道 · AMD · **3.3 自主选题赛道（初级组）**
> 作品名称：**基于 Zynq UltraScale+ XCZU3EG 的实时渲染、风格化与超分融合系统**
>
> 器件：`xczu3eg-sfvc784-1-i`（初级组白名单内：UltraScale+）
> 工具：Vivado / Vitis 2026.1

---

## 一、这是什么

在单颗 Zynq UltraScale+ XCZU3EG 上跑通的一条完整视觉增强链路：

```
ARM Cortex-A53                     可编程逻辑（PL）
─────────────                     ─────────────────────────────
游戏逻辑 + 全部几何（12 阶段）  →  固定功能像素后端（21 环节）  →  800×480 RGB LCD
顶点解包 / 矩阵变换 / 光照          边漫游光栅 / 双 TMU / 深度混合
视锥裁剪 / 图元装配 / setup         条带帧缓冲 / RGB565 流出
三角形参数 / 三分片 / 命令打包       帧桥 / PL DDR 双槽 / 扫描缩放
        ↓ 唯一交接物：192 字节整数化三角形描述符 ↓
```

**关键事实：PL 里没有任何几何硬件。** 几何的 12 个阶段 100% 在 A53。
这不是妥协，而是在 `32,510 LUT` 余量下做过 27 轮整机面积实测后的结论。

---

## 二、目录结构（对照指南 3.3.5.4）

指南 3.3.5.4 给的推荐结构非强制，但**要求目录名与文件名必须纯英文**
（小写字母、数字、下划线或连字符），并**在 README 中给出对照说明**。本包两者都满足：
已核查 **0 个中文文件名、0 个中文目录名**。

| 指南推荐 | 本包实际位置 | 内容 |
|---|---|---|
| `README.md` | `README.md` | 本文件 |
| `src/` | `src/rtl`（23 文件）+ `src/ps`（7）+ `src/board`（2）+ `src/hls/fsr1`（50） | 自研 RTL / PS 侧 C++ / 板级顶层 / 超分 HLS |
| `sim/` | `sim/`（67 文件） | 12 个 testbench（CNN AXI、帧桥突发、几何数值比对等） |
| `build/` | `build/`（12 文件） | 构建入口 `build.ps1` + 6 个关键脚本 + 4 份实现报告 |
| `board/` | `board/runtime`（394 文件） | 板端运行时：内核模块、DMA 代理、启动器、CNN 调度 |
| `data/` | `data/`（61 文件） | 4 套 CNN 权重、黄金参考 2.25 MB、56 张板上回读图 |
| `skill/` | `skill/README.md` | **技能包（评分项，踩坑清单型，17 条）** |
| `report/` | `report/design-report.docx` + `report/ai-collaboration.md` | 技术文档 + **大模型协作记录（评分项）** |
| — | `poster/poster.pptx` + `poster-preview.png` | 决赛海报（AMD 模板，一页英文） |
| — | `figures/`（7 张） | FPGA 专属配图，均可由脚本重建 |
| — | `docs/`（164 文件） | 全部证据文档，含 107 篇带 `path:line` 的技术记录 |
| — | `external/rasterix/` | 上游 RasterIX（GPLv3）+ **我们的补丁 `0001-board-ports.patch`** |
| — | `ports/`（47 文件） | ARM 侧 GL 实现补丁（几何前端、显示列表、DMA 连接器） |
| — | `config/`（18 文件） | 硬件共同配置与 XDC 约束 |

**中文名文档已全部改名为 ASCII**，对照表见 `docs/_rename-map.json`（10 条）。

---

## 三、五个交付物与其证据

| 交付物 | 内容 | 位置 |
|---|---|---|
| **技术文档** | 五部分：作品概述 / 系统组成 / 完成情况与性能 / 总结 / 参考文献 | `report/design-report.docx`（**8 图 2 表**，字数按模板限额全部合规） |
| **海报** | 一页英文，按 AMD PPT 模板版式（含对角分隔线、CREATIVE/RESULT 竖排字母、右栏边界） | `poster/poster.pptx` |
| **技能包** | **17 条踩坑清单（P1–P17）**，每条含触发条件、现象、根因、定位方法、修复、失效条件 | `skill/README.md` |
| **大模型协作记录** | 51 条真实提示词、5 条模型自我纠错原文、8 条用户纠正模型的清单、5 条工作流规则、12 条未采用清单 | `report/ai-collaboration.md` |
| **工程包** | 源码 + 仿真 + 构建脚本 + 实现报告 + 上板输出 + 黄金参考 | `src/ sim/ build/ board/ data/ ports/ config/ external/` |

---

## 四、核心技术主张（每条都有实测）

### 4.1　几何与像素按代价切分

分界物是 **192 字节的整数化三角形描述符**（4 B 头 `0x300000c0` + 192 B 负载），
不是顶点流。PL 收到的参数包已包含边函数初值、包围盒、w 梯度、
颜色/深度/双纹理梯度与 5-bit 定点化结果，**不做任何顶点变换、裁剪或透视除法**。

### 4.2　行流式超分

EASU 12 抽头边缘自适应重采样 + RCAS 5 抽头对比度自适应锐化，400×240 → 800×480。
不做整帧中间态往返，按行窗口计算；全部缩放模式复用同一块读突发缓存。

| 指标 | 数值 | 条件 |
|---|---:|---|
| 超分长测帧率（视距 32） | **57.089 帧/秒** | 120 秒，64³ 世界，源 57.107 |
| 超分长测帧率（视距 16） | **60.106 帧/秒** | 120 秒，源 60.132 |
| 同场景 20 秒对照 | 36.83 → **47.83 帧/秒** | 早期 → 当前版本 |
| **源呈现提速（Neverball）** | **28.97 → 45.17 帧/秒（+55.9%）** | 实际开局，异步呈现 |
| **源呈现提速（Quake III）** | **30.27 → 54.73 帧/秒（+80.8%）** | 内部上限 30→60 |
| **CNN＋FSR 串联吞吐** | **约 44–50 帧/秒** | 七游戏短测，非游戏完成帧 |
| **CNN＋FSR 提前通知** | **46.68 → 50.70 帧/秒（+8.62%）** | Neverputt 同球洞 ABCCBA |

### 4.3　CNN 存储原地复用

原方案用两个 160×96×8 INT8 整帧特征库交替读写（245,760 B，55 BRAM）。
改为「单整帧库 + 两行循环暂存 + 原地写回」。

| 指标 | 前 | 后 |
|---|---:|---:|
| CNN 核心 BRAM | 55 Tile | **28.5 Tile** |
| 整机 BRAM | 216 / 216 | **189.5 / 216** |
| DSP | 325 | 325（不变） |
| 核心周期 | 414,738 | 462,816（+11.6%） |
| 推理中位 | 12.405 ms | 12.873 ms |

**卷积、边界复制、舍入、ReLU、饱和与权重全部不变。**
93 用例 / 279 层输出零差异；另设「故意提前覆盖」负对照，验证器抓到 85 个通道值差异。

### 4.4　CNN 与超分的时分复用

原本判断「CNN + 完整 FSR 无法同存」（相加 **74,339 LUT > 70,560**，`place_design` 失败）。
实际采用的方案是**时分复用**，任一时点只有一个模块工作：

```
PL CNN（160×96 三层 INT8 推理，9.32 ms）
  → ARM（400×240 亮度细节融合，写回 8→2 ms）
  → PL FSR1（EASU12 + RCAS5，计算约 8.2 ms）
  → 800×480 LCD
```

**FPGA 资源不增加。** Neverputt 同一球洞呈现 **46.68 → 50.70 帧/秒（+8.62%）**，
显示等待 3.39 → 1.69 ms/帧。跨帧并行版本另测得 38.06 → 46.89（+23.19%），
但其首版因约 29.89 被拒绝，失败记录保留。

### 4.5　逐游戏分别调优（不是一套策略通吃）

| 游戏 | 原策略 | 改后 | 决策 |
|---|---:|---:|---|
| Neverball | 28.97 | **45.17（+55.9%）** | 用异步呈现 |
| Quake III | 30.27 | **54.73（+80.8%）** | 上限 30→60 |
| Tux Racer | 60.07 | 48.24 | **保留原策略**（同步反而更慢） |
| Neverputt | 60.10 | 60.10 | 原供帧，CNN 侧用 R3 |
| ClassiCube | 60.11 | 53.79 | 保留原 120 上限 |

**没有降低分辨率、纹理、光照或视距。** 低于 3% 的差异不作为切换依据。

### 4.6　十五款游戏库

八款原有 + 七款新增：rRootage（上游完整开源弹幕游戏）与六款自研原生规则小游戏
（贪吃蛇、落块消行、打砖块、2048、推箱子、扫雷）。六款规则集中在 `ports/arcade/rules.hpp`，
绘制统一走固定功能 GL 管线，**不使用 CPU 软件帧缓冲冒充 FPGA 光栅化**。
七款均过实机 PL FSR，短测源呈现 40–60 帧/秒。菜单支持分页、关键词搜索、收藏与最近游玩。

### 4.7　四层帧所有权保护

AXI 写排空 → 换页栅栏 → 帧桥完成码 → 消隐期发布。
**任一层缺失都会出现「画面撕裂但计数正常」的假通过。**
四层均经 1,000 次连续换页、延迟写响应、写响应非零、扫描欠流、DMA 超时等负向注入。

---

## 五、复现步骤

### 5.1　环境

| 项 | 版本 |
|---|---|
| Vivado / Vitis | 2026.1 |
| 器件 | `xczu3eg-sfvc784-1-i` |
| 宿主 | Windows 10/11 + WSL2 Ubuntu 22.04（g++ 11.4.0） |
| 板卡 | ALINX AXU3EG + AN970 800×480 RGB LCD（J16） |

### 5.2　三条重建命令

```powershell
# ① 只重建 ARM 库（不碰硬件；含宿主几何回归）
.\build\build.ps1 -Action arm
#   成功标志 ARM_MAINLINE_PREPARED / ALREADY_VERIFIED
#   回归判据：96 draws / 11,520 顶点 / 11,710 三角形 / 2,248,320 B
#             SHA cf6827033e79ba094bd7d55b45d66d1d00cd9d46193c8c7f74b64033753274c0

# ② 重建「ARM 主线实际使用的」双 TMU 位流
.\build\scripts\build_java256_dual.ps1
#   → build/minecraft-java-125/dual-tmu/board/java256.bin

# ③ 重建含完整超分的 v23 位流
vivado -mode batch -source build/scripts/run_fsr_v23_board.tcl
#   → build/fsr-pl/fixed-v23-bufferedread/board/fsr.bin
```

### 5.3　上游 RasterIX 如何还原

`external/rasterix/` 是上游固定提交 `9269a01c9bd4c3342bfa70ef8e3cdd751c15c6d0` 的
`rtl/` 与 `lib/` 目录。我们对它的全部改动在 **`0001-board-ports.patch`**（84 KB，28 个文件）。
还原方式：

```bash
cd external/rasterix
git init && git add -A && git commit -m upstream
git apply 0001-board-ports.patch     # 若要重新应用我们的改动
```

### 5.4　关键配置

| 项 | 值 | 位置 |
|---|---|---|
| 渲染 / 显示 | 400×240 RGB565 → 800×480 XRGB8888 | `config/rasterix_axu3eg.json:12-27` |
| 条带 | 3 × 80 行（`ceil(96000/32768)=3`） | `external/rasterix/lib/gl/renderer/RenderConfigs.hpp:55-63` |
| 像素时钟 | MMCM 200×(6/36) = 33.333 MHz | `src/rtl/reuse/mmcm_pixel_clk.v:17-25` |
| LCD 时序 | H 1056 / V 525 → 60.125 Hz | `src/rtl/reuse/video_timing.v:1-4` |
| 双 TMU 参数 | `TMU_COUNT=2`、`MAX_TEXTURE_SIZE=256` | 构建脚本生成 |

### 5.5　运行

```bash
# 板上（PS 侧 Linux）
export RIX_PRESENT_STRATEGY=async      # Neverball 推荐
python3 /opt/rasterix/linux/launcher/session.py
```

---

## 六、诚实边界（评审必须知道的三件事）

**① 超分与 CNN 不能同时占用一份配置。**
两者相加需 **74,339 LUT**，超出 **70,560** 容量，`place_design` 直接失败。
当前通过**时分复用**串起来（见 §4.4），但任一时刻只有一个模块工作。

**② 采用的位流是 RAM 加载，断电回旧版本。**
SD 卡的 `BOOT.BIN` 里仍是 2026-10-18 的旧 PL 分区。**没有任何脚本校验二者一致**，
所以「断电后回旧位流」是静默发生的。冷启动验收自 2026-10-22 起未再做。
**新游戏库也仍是 RAM 部署，尚未整合冷启动自启动。**

**③ 1080p 输出未验证。**
板卡具备 DisplayPort 通道，但当前 `disconnected`，无 EDID、无链路训练。
所有出图均为 800×480 RGB LCD。

---

## 七、许可与致谢

| 组件 | 来源 | 许可 |
|---|---|---|
| RasterIX | 固定提交 `9269a01c9bd4c3342bfa70ef8e3cdd751c15c6d0` | **GPLv3**（`external/rasterix/LICENSE`） |
| FidelityFX FSR1（EASU + RCAS） | AMD 2021，许可全文见 `src/hls/fsr1/LICENSE.FSR1.txt` | MIT 式 AMD 许可 |
| INT8 学生网络 | 本项目训练，3→8→8→3 / 160×96 / 1,027 参数 | 权重见 `data/models/` |
| 六款小游戏规则 | 本项目原创（`ports/arcade/rules.hpp`） | 随本作品 |
| tuxracer / SDL2 / gl4es 等 | 各自上游 | 各自许可 |
| Vivado / Vitis | AMD 2026.1 | AMD EULA |

本作品原创部分：板级 RTL（23 文件）、ARM 侧端口补丁（47 文件）、CNN 存储调度与 AXI 接口、
超分的行流式数据通路、板测事务与隔离机制、六款小游戏规则、全部证据文档与配图脚本。

**上游保留原版权与许可声明。本作品不声明拥有 RasterIX 或 FSR 的著作权。**
完整组件清单与许可全文见根目录 **LICENSE**（GPLv3）与 **NOTICE.md**。

### 开源发布（指南 3.3.3.3）

**已开源发布：<https://github.com/yilives/zynq-ultrascale-graphics>**

- 协议 **GPLv3**。GPLv3 允许再分发，满足「采用允许再分发的开源协议」；
  因链接上游 RasterIX（GPLv3），本作品须整体遵循 GPLv3，不能改用 MIT/Apache-2.0。
- 仓库内容与本提交包一致，可直接 `git clone` 复现。

---

## 八、复核入口（按重要性排序）

1. **技术文档**：`report/design-report.docx` —— 五部分，8 图 2 表
2. **技能包**：`skill/README.md` —— 522 行，**17 条踩坑（P1–P17）**
3. **协作记录**：`report/ai-collaboration.md` —— 51 条真实提示词、5 条自我纠错原文、8 条用户纠正模型
4. **技能包提炼过程**：`report/skill-derivation.md` —— 每条踩坑从哪次失败总结、如何验证、边界在哪
5. **演示口播稿**：`demo-script-3min.md` —— 3 分钟，含 8 条问答预案与数字速查卡
6. **工程源码**：`src/rtl/`（自研 RTL）、`ports/`（ARM 补丁）、`external/rasterix/`（上游+补丁）
7. **实现报告**：`build/reports/`（v23 层级资源、无 FSR 底座布线、r134 上板验收）
8. **海报**：`poster/poster.pptx` + `poster-preview.png`
9. **配图**：`figures/` —— 7 张，均可由 `rasterix-linux/scripts/build_amd_fig*.py` 重建
