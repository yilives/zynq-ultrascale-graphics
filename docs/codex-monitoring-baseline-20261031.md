# Codex 监控基线（2026-10-31 22:45）

> 本文件是监控依据。每次巡检先读这里，再跑 `scripts/watch_codex.ps1` 对比。
> **不修改 codex、不上板、不改文件**——除非用户明确批准。

---

## 1. 监控对象

| 项 | 值 |
|---|---|
| 主线程 session id | `01a12056-7fa6-77e1-b6a7-5e81095ba5ce` |
| rollout 文件 | `C:\Users\yilives\.codex\sessions\2026\10\09\rollout-2026-10-09T19-05-02-01a12056-7fa6-77e1-b6a7-5e81095ba5ce.jsonl` |
| 当前大小 | 约 278 MB / 79,300+ 行 |
| 监控脚本 | `scripts/watch_codex.ps1`（只读，从尾部 4 MB 读，不加载全文件） |
| 调用方式 | `powershell -NoProfile -ExecutionPolicy Bypass -File ...\watch_codex.ps1`（必须走 powershell.exe，pwsh 会因执行策略拒绝） |

## 2. 额度窗口（2026-10-31 22:40 读数）

| 项 | 值 |
|---|---|
| 套餐 | `plus` |
| **5h 窗口** | 已用 **21%**，300 min |
| **5h 重置** | **2026-11-01 02:48:02 +08:00** |
| 7d 窗口 | 已用 14%，10080 min |
| 7d 重置 | 2026-11-07 16:49:36 +08:00 |
| 状态 | OK（距 85% 预警线还有很大空间） |

**关键判断**：codex 目前**远未耗尽额度**。用户担心的"5 小时额度跑完"现在不存在。
如果后续真的跑满，`used_percent` 会到 100 且 `resets_at` 之前不会回落。

## 3. codex 正在做什么（22:45 状态）

**RUNNING**（idle 个位数秒，文件持续增长）。

今日已完成（按 `docs/` 与 `report/` 时间戳核对）：

| 时间 | 交付 | 证据 |
|---|---|---|
| 16:53 | `src/ps/JavaPipelineProfiler.hpp` 阶段计时器 | `report/minecraft-java-125/pipeline-r134-evidence/` |
| 17:09 | **R134 阶段诊断**：772 帧 / 31.007 s / 24.90 FPS（`accepted_performance_run=false`） | `board-acceptance-r134.json` |
| 17:16 | `JAVA125_ARM_DMA_DIAGNOSTIC_2026-10-31.md` | 见文档 |
| 17:31 | `GAME_SWITCH_MINIDP1080_PLAN_2026-10-31.md`（方案，未部署） | 见文档 |
| 20:53 | **游戏选择界面 v1b**：ARM 离屏 28 项检查通过，1080p + 800×480 两种布局 | `report/launcher-ui-v1b/acceptance.json` |
| 22:33 | 正在传 `cpu-r143` 包（R137–R143 未被 `board-acceptance` 记录，说明都是准备/传输轮） | `cpu-r143-lowq-r116-transfer.log` |

**R134 的一个重大发现**（这是今天最有价值的产出）：

| 测量范围 | 墙钟累计/窗口 | 调用数 |
|---|---:|---:|
| 几何工作线程总范围 | 68.11% | 1,546 |
| **顶点批次链路** | **58.49%** | 18,556 |
| 前端等待几何线程 | **53.68%** | 361,561 |
| 命令流 FINISH 等待 | 23.54% | 4,638 |
| 资源 STORE FINISH 等待 | 4.75% | 10,562 |

**顶点批次链路占几何线程 CPU 的 90.5%**。这句话的意思是：**瓶颈确认在 ARM 侧几何计算，不在 PL**。
这和我上一轮从 r131 JSON 反推的结论（ARM 串行 25 ms + DMA 等待 11 ms，PL 段恒定）**方向一致**，
但 R134 是直接计时，比我那个"8 个样本反推"硬得多。

**同时它也推翻了我一个猜测**：我之前说 DMA 等待可能是"每帧固定握手成本"，
但 R134 显示 FINISH 等待 23.54% 里主要是睡眠等待，且"从提交到观察完成累计约 85.2%"，
这更接近"ARM 供数慢，DMA 在等 ARM"而不是"固定开销"。四个子代理的结论在这里收敛了。

## 4. codex 当前卡在哪 / 风险在哪

**已知未完成（codex 自己写明的）**：

1. **miniDP 1080p 输出完全没做**。DP 状态 `disconnected`，`modetest` 未安装，无 EDID、无链路训练。
   用户 10/31 明确说"暂时不能连接，先完成游戏和 FSR"。
2. **真实游戏切换未验收**。`launcher-ui-v1b/acceptance.json` 里
   `real_game_switch_validated: false`、`dp_output_validated: false`。
   UI 只在 SDL dummy 离屏跑过，**没有输出到物理 LCD 或 DP**。
3. **Java 的 FSR 未真正跑通**。codex 自述：FSR 整帧 384000 像素比对通过，
   但随后"Java 渲染库要求凭据位于旧的固定路径，因此在向 RasterIX 提交任何命令前主动退出了"，
   触发隔离机制，软重启恢复。**这是 22:29 的状态，之后一直在补凭据路径。**
4. **CNN 在 Java 位流里是 stub**（`rix_java_cnn_unavailable.sv`，`0xb8=1` 的 bit1=CNN absent）。

**风险点**：

| 风险 | 严重度 | 说明 |
|---|---|---|
| 隔离机制频繁触发 | 中 | 每次触发都要整板软重启 + 重建 RAM 环境，一轮损失 10–20 分钟 |
| RAM 环境每次重启清空 | 高 | JRE/素材/库都要重传（2 MiB/5 s，277 MB 要 ~12 分钟） |
| 位流不落地 | 高 | 见交接书 §7.1，断电回旧 BOOT.BIN |
| 一次不安全终止即锁死 boot_id | 高 | `gpu-quarantine.json` |

---

## 5. 用户目标 vs 当前现实（差距表）

用户要的最终形态：**ARM 前端 FPGA 图形 + 超分 + CNN，可以跑游戏，并且做优化。**

| 目标 | 现状 | 差距 | 卡在哪 |
|---|---|---|---|
| ARM 前端 + FPGA 图形 | **已达成** | 无 | — |
| 可以跑游戏 | **已达成**（8 游戏，Java 1.2.5 已进世界） | 切换未验收 | 菜单未接物理输出 |
| **超分（FSR）** | **部分**：v23 位流有完整 FSR，ClassiCube 线已验收 57 FPS；**Java 线 FSR 未跑通** | Java FSR 需要凭据路径修复 | codex 正在修 |
| **CNN（神经风格）** | **Java 线是 stub**；ClassiCube 线已验收 25–26 FPS | **Java 位流装不下** | 见 §6 |
| 优化 | R134 已定位瓶颈在 ARM 顶点链路 58.5% | 优化未开始 | — |

## 6. 我算出来的一道硬墙（**这是最重要的发现**）

用户要的"ARM 图形 + 超分 + CNN 同时跑"在**当前 Java 双 TMU 位流上装不下**：

| 资源 | Java 双TMU（主线） | CNN 需求 | 合计 | 器件容量 | 判定 |
|---|---:|---:|---:|---:|---|
| LUT | 65,624 | 4,466 | 70,090 | 70,560 | ok（只剩 470） |
| FF | 74,028 | 2,075 | 76,103 | 141,120 | ok |
| DSP | **330** | **65** | **395** | **360** | **超 35** |
| BRAM | 149 | 55 | 204 | 216 | ok |

而 v23（单 TMU + CNN + FSR）**BRAM 已 216/216 满**，且 RasterIX 只占 84 DSP
（单 TMU），换成双 TMU 要 154 DSP，差 70。

**三条可能的出路（我的判断）：**

1. **砍 CNN 的并行度**。`rix_cnn_engine.sv:53-56` 是 64 个 `use_dsp="yes"` 乘法器，
   报告 65 DSP。降到 32 个乘法器 → 约 33 DSP，能塞进 30 的余量（还差一点，可配合减少 bank）。
   代价：推理时间约翻倍（现在 4.147 ms 核 + PIO）。
2. **CNN 分时复用 TMU 的 DSP**。TMU 是 40 DSP/个，两 TMU 80 DSP。
   但 TMU 和 CNN 在**同一帧里是并发的**（CNN 处理低分辨率输入的同时游戏在渲染下一帧），分时不可行。
3. **降 CNN 输入分辨率**。现在 160×96，降到 128×72 → 乘法器数可降到 36 左右。
   代价：风格迁移细节变差。

**建议**：先做 (1)，把 64 乘法器减到 32，同时把 `PIXELS` 保持 160×96，
用时间换面积。这个改动是纯 RTL 参数，不动 CNN 算法、不动 Java 库、不动 ABI。

---

## 7. 监控协议（每轮巡检照做）

```
1. powershell -NoProfile -ExecutionPolicy Bypass -File ...\watch_codex.ps1
2. 记录：state / 5h used_pct / idle 秒 / 最近 3 条动作 / 最后一条自述
3. 对比上一次巡检：
   - state 从 RUNNING → IDLE 且 idle > 30 min 且 used_pct < 100 → 「疑似卡死」，需要人工介入
   - used_pct 到 100 → 「额度耗尽」，记下 resets_at，等重置
   - 新的 board-acceptance-r*.json 出现 → 记下轮次号与 FPS
4. 检查不安全状态（每条必查）：
   - report/minecraft-java-125/swap-fence/board-acceptance-r<N>.json 的 original_v23_restored
   - 有无 gpu-quarantine.json 残留（只能从 docs 或 board 日志间接看）
   - 最新一轮 accepted_performance_run / passed / restored 三个字段
5. 报告给用户，不擅自干预。
```

## 8. 续跑指令（**只在用户批准后执行**）

⚠️ **重要限制（已实测）**：`codex exec` 在本机**无法工作**，原因：
- `~/.codex/config.toml` 里 `service_tier = "default"` 不合法（只接受 `fast`/`flex`）
- 且 `model = "gpt-6-luna"` 走的是第三方 `base_url = https://www.micuapi.ai`
- 用 `-m gpt-5.4` 也报 `model_not_supported when using Codex with a ChatGPT account`
- **实测三条命令全部失败**

所以**"自动续跑"只能靠 Codex Desktop GUI 里手动发消息**，不能用 CLI。
我能做的是：监控 + 到点提醒 + 给出该发什么 prompt。

如果要续跑，建议在 Codex Desktop 里发（按优先级）：

```
# 如果 Java FSR 凭据还没修好
继续修 Java 的 FSR 凭据路径。目标：Java 游戏跑起来时 FSR 真正工作，
不只是 384000 像素的静态比对。修完要有 R137 的 board-acceptance，
original_v23_restored=true、passed=true。

# 如果 FSR 已通，接 CNN
现在做 CNN 进 Java 位流。约束：Java 双 TMU 位流 DSP 只剩 30，
CNN 现在要 65。把 rix_cnn_engine.sv 的 64 个乘法器降到 32（改 bank 数），
重新综合，报 LUT/FF/DSP/BRAM 和 WNS。不要动 Java 库和 ABI。

# 如果两个都通了，回到 R134 的结论做优化
R134 显示顶点批次链路占几何线程 CPU 90.5%。下一个候选是融合 MVP 矩阵：
VertexTransformer.hpp:268 的 modelView 和 :300 的 projection 现在对无裁剪批次
做两次 4×4 变换，预乘成一次。必须位精确 ABBA 比对。
```

## 9. 我设的提醒

| 提醒 | 时间 | 目的 |
|---|---|---|
| 额度重置后检查 | 2026-11-01 02:52 | codex 5h 窗口重置，看它是否因额度停住、停在何处、是否安全 |
| 每小时巡检 | 每小时 | state / 额度 / 最新动作 / 最后自述 |

**注意**：这轮的提醒只在**本会话**有效。如果会话被清理，提醒会丢。
需要长期监控的话，得靠人看或另建机制。
