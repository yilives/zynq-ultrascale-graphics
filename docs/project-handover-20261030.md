# rasterix-linux 项目接管交接书

日期：2026-10-30　对象：新维护者　平台：ALINX AXU3EG / `xczu3eg-sfvc784-1-i`

> 本文不是功能说明，是**接管用的状态快照 + 操作地图 + 红线清单**。
> 每条结论带 `path:line`；凡是「我的判断」都单独标注，与文档已有结论分开。
> 配套阅读：`docs/前端与架构全景_20261030.md`（架构与证据）、`config/java_arm_mainline.json`（当前选择）。

---

## 0. 一句话现状

**路线已回退到「ARM 出几何 + PL 出像素」，主线配置已冻结并上板验证；游戏帧率约 24.9–25.7 FPS（静止 Tiny 短测），未达 32/60；采用的位流只在 RAM，断电即回落到 SD 上 2026-10-18 的旧 BOOT.BIN。**

三条已被用户明确放弃的路线（**不要重启**）：
Vortex 计算前端、完整 HLS 几何迁移 → `config/java_arm_mainline.json:10-11` 写着 `abandoned_by_user`；
Mali 渲染 → `:9` `mali_enabled:false`。

---

## 1. 这个项目到底是什么

一个**私有 GL 实现 + FPGA 固定功能像素后端**，跑未修改的 Minecraft Java 1.2.5。

```
游戏（MC Java 1.2.5 / LWJGL）
  → 私有 libGL.so.1（RasterIX 的 C++ 前端 + 板级端口）
      ARM A53 干完 12 个阶段的几何：顶点解包 → 矩阵变换 → 光照 → 裁剪 → 图元装配
                → 透视除法 → 视口 → 剔除 → setup（边函数/梯度/定点）→ 3 条带 → 命令打包
      产物：196 B/三角形的整数描述符（4 B 头 0x300000c0 + 192 B 负载）
  → AXI DMA（8 槽 × 1 MiB mmap）
  → PL RasterIX(IF)：命令解析 → 边漫游光栅 → 属性插值 → 双 TMU → 深度/混合
                → 32768 像素内部条带 ×3 → RGB565 流出
  → 帧桥 RGB565→XRGB8888 → PL DDR 双 slot → 扫描/缩放 → 800×480 LCD
```

**关键事实：PL 里没有任何几何硬件。** 五条独立证据见 `docs/前端与架构全景_20261030.md:19-27`。

竞赛背景：2026 AMD FPGA 创新设计赛道自主选题初级组，评分含创新 30 / 性能资源 20 / 完整性 20 / 大模型协作 15 / 文档复现 15（`docs/contest_14_day_plan_2026-10-26.md:41-47`）。

---

## 2. 五个「身份」，必须分清

这是本项目**最容易出错的地方**。仓库里同时存在 4 份位流、2 套硬件配置、2 套 R 编号。

### 2.1 位流（4 份，互不相同）

| 位流 | SHA-256 前 8 位 | 在哪 | 能力 | 上板 |
|---|---|---|---|---|
| **BOOT.BIN 里的 PL** | `fc3a6e37` | SD 卡 `build/sdcard/BOOT.BIN`（`8f26ae5a…`） | 单 TMU / 128² 纹理 / 无 FSR | **2026-10-18 之后没有再验过冷启动** |
| **ARM 主线用的** | `14fd58da` | `build/minecraft-java-125/dual-tmu/board/java256.bin` | 双 TMU / 256² / 含 FSR | 是（R131 等，**运行时 RAM 加载**） |
| **v23** | `035c3059` | `build/fsr-pl/fixed-v23-bufferedread/board/fsr.bin` | 单 TMU + CNN + 完整 FSR | 是（RAM），Java 试验结束后恢复到此 |
| **无 FSR 基座** | `6f8b5437` | `build/minecraft-java-125/no-fsr-base-r1/` | 双 TMU / 无 FSR / 无 CNN | **从未上板**（`resource-routed.json:148-149`） |

当前主线选的是 **`14fd58da`**（`config/java_arm_mainline.json:18-19`）。

### 2.2 硬件参数的两套值（这是陷阱）

| 来源 | TMU | 纹理上限 | 说明 |
|---|---|---|---|
| `config/rasterix_axu3eg.json:36-37` | **1** | **128** | 给 `build.ps1 -Action board` 用，产出 `fc3a6e37` |
| `build/minecraft-java-125/{dual-tmu,no-fsr-base-r1}/rtl/rasterix_linux_top.v` | **2** | **256** | 实际采用的位流用这份私有覆盖（两者 SHA 同为 `7be2febb…`） |

`src/rtl/top/rasterix_linux_top.v` 是 `scripts/generate_top.py` 生成的，内容对应**单 TMU/128**。
**引用能力参数时必须指明来源**，否则会得出错误结论。

另外两个 `src/rtl/video/` 文件在构建时被覆盖，仓库版本不是编译版本：
`rix_scaler.v`、`rix_frame_reader_dynamic.v` → 实际用 `build/fsr-pl/video-v24-burstcache/video/`（`scripts/create_java256_no_fsr_base_r1.tcl:21-26`）。

### 2.3 R 编号有两套命名空间

| 命名空间 | 含义 | 例 |
|---|---|---|
| **大写 R19–R45** | **HLS 几何综合批次**，从未上板 | R32 = 139,017 LUT 的 HLS 估计 |
| **小写 r14–r133** | **上板游戏轮次**，一轮 = 一次完整 session | r131 = 26.2034 FPS |

原文自己写明这条：`docs/JavaMC_完整几何前端_硬件接入进度_20261030.md:5`。
**所以 R19 / R21 / R32 各有两种含义**，`README.md:50` 的 R19/R21 是游戏轮，`JavaMC_...:72` 的 R19 是 374,209 LUT 的综合批次。

事实上的登记表（不是单一文件）：
- `report/minecraft-java-125/swap-fence/board-acceptance-r<N>.json`（83 个）
- `report/minecraft-java-125/swap-fence/local-r<N>.json`（105 个）
- 失败/未执行：`swap-fence/failed-queued-trials.json`、`failed-sequential-trials.json`
- 编号规则：单调递增，失败轮也占号且**永不重用**（`docs/JAVA125_TEXTURE_WAIT_OPTIMIZATION_2026-10-29.md:21`）

**R110/R120/R121/R126/R127/R132/R133 是准备/导出/采纳号，永远没有 FPS。** 下一轮从 **r134** 起。

---

## 3. 构建入口：8 个 Action，没有一个碰硬件

`build.ps1`（59 行）签名在 `:1-4`，共 8 个 Action。

| Action | 产出 | 触硬件 |
|---|---|---|
| `prepare` | `generated/*`、`src/rtl/top/rasterix_linux_top.v`、`report/source_manifest.json` | 否 |
| `check` | `build/top_ooc/`、`build/{sim,gpu_sim}/` | 否（仿真 + OOC） |
| `candidate` | `build/vivado_board/rasterix_linux.xpr`（无 bit/XSA） | 否 |
| `board` | `build/rasterix_linux.bit`（`fc3a6e37`）+ `.xsa` | 否（只 write_bitstream） |
| `postproc` | `build/postproc-touch/*.bit` | 否 |
| `neural` | `build/neural-style/` | 否 |
| `classicube` | `build/classicube/` | 否 |
| **`arm`** | **`build/minecraft-java-125/arm-mainline-r3/`** | 否（`proof.json` 记 `board_executed:false`） |

**没有任何 Action 打开串口/JTAG 或写 SD。** 全脚本无 `flock`。

### 3.1 三条常用命令

```powershell
cd F:\1FPGA\Xilinxprj\prj2\rasterix-linux

# ① 只重建 ARM 库（最常用；走 WSL + SDK 2020.1）
.\build.ps1 -Action arm
# 成功标志：ARM_MAINLINE_PREPARED（首次）或 ARM_MAINLINE_ALREADY_VERIFIED（重复）
# 换目录：WSL 内 bash scripts/build_java_arm_mainline_r1.sh --attempt r4

# ② 重建「ARM 主线真正用的」双 TMU 位流（不经 build.ps1！）
.\scripts\build_java256_dual.ps1     # → build/minecraft-java-125/dual-tmu/board/java256.bin

# ③ 重建 v23（Java 试验后要恢复的那份，没有 ps1 入口）
vivado -mode batch -source scripts/run_fsr_v23_board.tcl
```

`-Action arm` 自带宿主几何回归：96 draws / 11,520 顶点 / 11,710 三角形，
两份输出各 2,248,320 B，SHA 必须都是 `cf6827033e79ba094bd7d55b45d66d1d00cd9d46193c8c7f74b64033753274c0`
（`scripts/prepare_java_arm_mainline_r1.py:108-109`）。

**`-Action arm` 只证明「库字节身份 + 宿主回归」，不证明板上能跑。** `proof.json` 自己写着
`board_executed:false`、`board_or_sd_written:false`、`new_board_fps_measured:false`。

### 3.2 一个隐藏依赖

`-Action arm` 依赖 `build/minecraft-java-125/sequential-batch/` 里的冻结产物
（`source.json`、`build-audit.json`、`link-inputs.json`、`unit-build.json`、`glx.cpp.o`、
两个 `geometry-*-host` 可执行文件）。**这套东西删了就无法重建**，因为上游私有源码树
在 WSL 的 `/var/tmp/rix-java-queued-v2-source`，而 `/var/tmp` 会被清理。

实测 `/var/tmp/rix-java-*` 目前仍有 22 个目录，但**没有任何备份机制**。

---

## 4. 板务：三把锁 + 隔离守卫 + receipt + 回滚

### 4.1 三把锁（唯一权威定义）

`linux/postproc/fpga_fsr_control.py:41`

```python
LOCKS = ('rasterix-game-launch.lock', 'rix-superres.lock', 'rix-mc-style-extract.lock')
```

实现 `:358-368`：逐个 `os.open('/tmp/'+name, O_CREAT|O_RDWR|O_NOFOLLOW, 0o600)` → 拒绝符号链接 → `flock(LOCK_EX|LOCK_NB)`。
**非阻塞**：拿不到就抛，不等待。

| 锁 | 语义 |
|---|---|
| `rasterix-game-launch.lock` | 有游戏/GPU 客户端在跑（全局启动互斥） |
| `rix-superres.lock` | 后处理/显示模式独占 |
| `rix-mc-style-extract.lock` | SD 上风格/画质包解包 + 入口替换独占 |

三锁同持处：`fpga_fsr_control.py:277`、`stage_fsr_ram_v23.py:34-36`、
`linux/java_minecraft/run_java256_trial.py:57`（循环 `m.LOCKS`）、`prepare_java125_recovery.py:11` 等。

### 4.2 隔离守卫（一次失败就要求断电重启）

`linux/game_runtime_support.py:12-37` `GpuRecoveryGuard`

- `check()` `:18-22`：`/opt/rasterix/experimental/gpu-quarantine.json` 里若有**同一 boot_id** 的失败记录 → 抛
  `"Previous GPU/DMA failure in this boot; reboot the board before starting another game."`
- `mark()` `:24-37`：`fsync` 落盘 + `os.replace` 原子替换 + 目录 fsync

**含义：任何一次不安全终止（进程被杀、DMA 超时、计数不收敛）都会让本 boot_id 内无法再起游戏，
只能整板重启。** R71 就是这么被锁的（`docs/minecraft_java125_sequential_cache_2026-10-28.md:44-46`）。

### 4.3 位流身份认定（两段式）

**(a) SHA-256 receipt**：`/tmp/rix-fpga-fsr/active-receipt.txt`，4 行
```
RIX_FSR_PL_ACTIVE_V1
<boot_id>
<bit_sha256>
<source_manifest_sha256>
```
写入 `fpga_fsr_control.py:344-350`（`O_CREAT|O_EXCL|O_NOFOLLOW` 0600 + fsync）。
变体 magic：Java 256 用 `RIX_TEX256_CACHE_ACTIVE_V1`（`run_java256_trial.py:116`），
no-FSR 用 `RIX_JAVA_NOFSR_ACTIVE_V1`。

**(b) CSR 身份**：`fpga_fsr_control.py:509-511` 读 `0x00 == 0x52495801`、`0x0c == 0x9adb505e`。
`0x9adb505e` 来自 `generated/config.sha256[:8]`（`scripts/generate_top.py:70`）。

双 TMU 位流的能力位（`build/minecraft-java-125/dual-tmu/rtl/rix_control.v:107-114`）：
`0xb0=0x4a324d31`（J2M1）、`0xb4=2`、`0xb8=1`、`0xa8=0x53574631`（SWF1 换页栅栏）、
`0x98=0x54584332`（TXC2 双 TMU）、`0x9c=0x01000100`、`0xa0=1024`、`0xa4=7`。
校验器：`build/minecraft-java-125/dual-tmu/java_dual_loader.py:96` 要求 8 个偏移**全部相等**。

进程内还有一道：`ports/java256_profile_guard.hpp:36` 在静态初始化时校验 receipt + MMIO，失败 `std::abort()`。

### 4.4 回滚（`run_java256_trial.py`，303 行）

跑一轮游戏的完整事务：

1. 持三锁（`:65-67`）→ `guard.check()`（`:68`）→ 快照并 `check_idle()`（`:69`）
2. 校验 boot_id、`proof['passed']`、旧 receipt 内容、`old.bin` 的 SHA（`:70-74`）
3. **先建反向往回包**（`:77-84`）：把 `old↔new` 互换，生成 `restore_dir/manifest.json`
4. 把旧 receipt **退役**（`:88`）再切位流
5. 加载新位流 → `set_trial_nearest()`（`:149`）→ 跑探针 → 跑游戏
6. `finally`：`set_post_mode1()` → 反向 transaction 恢复 → 重建原 receipt（`:107-112`）
7. 若 `unsafe`：`guard.mark()` 落隔离文件（`:288-291`），并作废 receipt

**这套事务是项目最成熟的部分**，改板务时照抄它的结构，别另起一套。

---

## 5. 性能现状（唯一可信的数字）

### 5.1 当前配置

`config/java_arm_mainline.json`：ARM 几何 + PL RasterIX、Mali 关、Vortex/HLS 迁移放弃、
`RIX_JAVA_FPGA_GEOMETRY=0`、**`RIX_JAVA_BATCH_CACHE_BYPASS=1`**、`RIX_JAVA_DEFER_TEXTURE_WAIT=0`、
原画质 / Tiny（`viewDistance=3`）/ Fast / 关云 / 最近邻 / FSR·CNN 关。

包：`build/minecraft-java-125/arm-mainline-r3/`（r1/r2 保留）。
板端 options 已同步（备份 `/tmp/java-quality-selection-r133/original-options.txt`）。

### 5.2 帧率：给区间，不给单点

| 组 | 轮次 | 加权 FPS |
|---|---|---|
| PL Tiny 正确视距 | R79/R80 | 25.7183 |
| 缓存/直通 ABBA（直通 ON） | R123/R124 | 25.3751 |
| 原画质对照（直通 ON） | R128/R131 | 24.9424 |

**同一配置三次独立 session 的加权是 24.94 / 25.38 / 25.72，波动约 3%。**
这个波动**大于**除直通以外所有已测优化的组间差。

所以正确写法是「**24.9–25.7 FPS 区间**」，不要说「基准 25.72」。

### 5.3 唯一站得住的增益

**顶点直通 `RIX_JAVA_BATCH_CACHE_BYPASS=1`：+7.55%**（缓存 23.5930 → 直通 25.3751）。
同 session 四轮 ABBA，两轮直通均高于两轮缓存，4/4 方向一致
（`docs/JAVA125_TINY_SEQUENTIAL_2026-10-30.md:5,28`）。

**但幅度不可跨 session 引用**：R128 也是直通 ON + 原画质，只有 23.7217，
落在缓存组区间内（`docs/JAVA125_LOWQ_SEQUENTIAL_2026-10-30.md:30-31` 自己承认了这点）。

### 5.4 我算出来的帧预算（**我的分析，非文档已有结论**）

用 `report/minecraft-java-125/swap-fence/board-acceptance-r131.json` 的一轮完整数据：

| 项 | 值 | 来源 |
|---|---|---|
| 帧时间 | **38.16 ms** | 786 帧 / 29.996 s |
| 最忙线程 CPU | **25.01 ms** | tid 10920，19.66 s，`comm="Minecraft main"`
| 第二线程 CPU | 8.13 ms | tid 10917，6.39 s，`comm="Minecraft main"`
| DMA FINISH 阻塞 | **11.13 ms** | `dma_delta.wait_ns / 786` |
| **串行两段之和** | **36.15 ms** | 最忙线程 + DMA 等待 |
| 未解释 | 2.02 ms | — |

> 注意：两个线程的 `comm` **都是 `Minecraft main`**（Linux 线程名不区分角色）。
> 说 10917 是几何 worker 是**推断**（按 R85 的符号归属惯例），不是直接证据。
> `docs/前端与架构全景_20261030.md:110-111` 明确警告过不能靠名字区分。

**关键发现：`ARM 忙` 与 `DMA 等待` 在 8 轮里几乎严格互补。**
把 `1000/(arm_ms + pl_ms)` 当预测帧率，8 轮误差都在 3.4–6.2% 且方向一致（预测值偏高）：

| 轮次 | 实测 FPS | 预测 FPS | 误差 |
|---|---:|---:|---:|
| r122 | 23.66 | 24.99 | +5.6% |
| r123 | 25.50 | 27.05 | +6.1% |
| r128 | 23.72 | 25.09 | +5.8% |
| r130 | 26.49 | 27.40 | +3.4% |
| r131 | 26.20 | 27.66 | +5.6% |

而「第二线程 + 最忙线程 + DMA 等待」会超过帧时间（如 r131 是 44.28 > 38.16），
说明**几何 worker 的 CPU 与主线程/DMA 等待是重叠的**，只有「最忙线程 + DMA 等待」是串行关键路径。

**推论（判断，需实测验证）：** 帧时间近似为 `T ≈ T_arm_serial + T_dma_wait`，
其中 `T_dma_wait ≈ 11.1 ms` 在 8 轮里几乎恒定（10.70–12.12），**不随命令量变化**：
r100 是 249,791 命令拍/帧、r103 是 270,147 拍/帧（+8.2%），DMA 等待只从 11.19 变到 11.85（+5.9%）。

> 但 r103 同时是异常负载轮（594 次条带溢出、FPS 24.03），所以这个「不随命令量变化」
> **只有 8 个样本、且含一个离群轮**，不足以定论。要真正确认，必须做 §8.1 ②③。

这更像**每帧固定的同步握手成本**（`beforeSubmit()` 等上一次 present + 每次 `writeData()` 前的
`waitForDma()`，见 `src/ps/rasterix_presenter.hpp:49-51`、`src/ps/DMAProxyBusConnector.cpp:52`），
而不是 PL 在算像素。

如果这个判断成立，那么**「PL 满负荷」是错的，真正的瓶颈是 ARM 串行段 25 ms**。
但这需要新增计数器才能确认——现在**没有**命令输入空泡、光栅反压、有效片元三个计数（见 §7.1）。

### 5.5 命令量账（我算的）

从 r131 的 `dma_delta`：

- 每帧 `stream_bytes` ≈ **972.7 KiB**，`store_bytes`（纹理）≈ 262.7 KiB
- 硬件计数 **321,492 命令拍/帧** ≈ 1.23 MiB/帧 → 约 **6,561 个三角形/帧**
（按 49 word/三角形含头算）
- 每帧 5.9 次 stream + 12.9 次 texture store = **18.8 次 DMA 事务/帧**，每次都可能阻塞
- CPU 对空闲 DMA 槽的连续写入可达 **3.3 GiB/s**，实际只提交 **32 MiB/s**
  （`docs/JAVA125_GEOMETRY_OFFLOAD_STUDY_2026-10-29.md:53`）→ **带宽不是瓶颈**
- 整场 59,763 批次 / 91,746,888 顶点，平均 **1,535 顶点/批次**

### 5.6 这不是游戏 FPS，别混

| 数字 | 真是什么 |
|---|---|
| 44.35 / 36.08 | 命令**重放**上限（驻留纹理、3 帧、无游戏逻辑） |
| 40.76 / 7.82 | Mali 的 **PBuffer/X11** 完成交换，不是 LCD 通路 |
| 57.09 / 60.11 | ClassiCube + PL FSR 长测，**不是 Java** |
| 60.125 Hz | LCD 扫描节拍，不是新帧率 |
| 48.9–51.9% | `perfBusy` = 命令解析器 `state != COMMAND_IN`，**不是像素利用率** |
| `fpsLimit=1` | 原版限帧策略参数，从未实测到 120 |

---

## 6. 已证伪清单（**不要重复包装**）

| 实验 | 结果 | 出处 |
|---|---|---|
| 命令 RAM 暂存 | **+2.73%**，四轮 ABBA 落在噪声内 | `JAVA125_COMMAND_STAGING_2026-10-28.md:38` |
| 大条带命令空间翻倍 | **−0.062%**（最大命令体从未超过原容量） | `JAVA125_BUFFER_POSITION_OPTIMIZATION_2026-10-28.md:19` |
| 128 槽位置复用 | 命中 70.18%，FPS **−2.99%** | 同上 `:42` |
| 纹理等待后移 | +3.06% 但组内 −0.55%/+1.32%，方向不稳 | `JAVA125_TEXTURE_WAIT_OPTIMIZATION_2026-10-29.md:34-38` |
| 控制/存储互联拆分 | 省 6,059 LUT，游戏 **−13.5%**；但新候选每帧命令多 15.5%、2,105 次 band spill vs 0，**原文明确说不足以归因于 AXI 转换器** | `JAVA125_INTERCONNECT_REPLAY_2026-10-28.md:64-67` |
| 降低画质（AO/粒子/晃动） | **+2.13%**，组间差 < 组内差 | `JAVA125_LOW_QUALITY_ABBA_2026-10-30.md:5` |
| 全低画质 + 直通 | +5.94% 但基线自身波动更大，**未采纳** | `JAVA125_LOWQ_SEQUENTIAL_2026-10-30.md:30-31` |
| 向量值语义 | **−0.31%**（仅差一帧） | `minecraft_java125_cpu_vector_2026-10-27.md:100` |
| 显示列表直接读取 | CPU −12.17%，FPS 5.000→5.031 | `README.md:42` |
| DMA 映射写入慢假设 | 64 KiB memcpy 普通堆 4,357 vs DMA 3,835 MiB/s，**否证** | `JAVA125_TEXTURE_WAIT_OPTIMIZATION_2026-10-29.md:56-61` |
| 完整 HLS 几何 | R45 实际综合 91,645 LUT，是可用余量 32,510 的 **2.82×** | `JavaMC_..._容量与吞吐可行性复核_20261030.md:49` |
| 紧凑状态机编码 | FF −3,692 但 LUT **+4,074**，不采用 | `JavaMC_..._硬件接入进度_20261030.md:211` |

**唯一可复用的旧成果：顶点直通。其余全部为零或负。**

---

## 7. 现在的真实缺口

### 7.1 阻塞

1. **位流不落地**。`14fd58da`（Java 主线）与 `035c3059`（v23）都只在 RAM。
   SD 上 `BOOT.BIN`（`8f26ae5a`）的 PL 分区仍是 2026-10-16 的单 TMU 基线 `fc3a6e37`。
   **而且没有任何脚本校验 BOOT.BIN 的 PL 分区等于哪一份位流**
   （`release_manifest.py:107-111` 只比对 XSA 内嵌 bit 与 `build/rasterix_linux.bit`）。
   这就是「断电回旧位流」没有任何检测的根本原因。

2. **冷启动未验收**。唯一被记录的成功是 2026-10-16
   （`docs/BOOT_FIX_2026-10-16.md:13`，`report/physical_boot_2026-10-16.json` 的
   `revised_physical_boot` 里 `linux_booted:true` + `user_reported_cold_boot_success:true`，
   U-Boot 横幅 `U-Boot 2026.01 (Oct 16 2026 - 18:14:13 +0800)`）。
   **注意这是用户口头确认，不是自动验收。**
   2026-10-18 只做了「正常 Linux 重启」（`report/runtime_promotion_2026-10-18.json` 的
   `post_reboot_verified:true`），不是断电冷启动。
   自 2026-10-22 起所有记录都写「本轮没有进行冷启动验收」。

3. **没有通路归因计数器**。现在只有 `perfBusy`（命令解析器状态）。
   缺命令输入空泡、光栅反压、有效片元数（`JAVA125_COMMAND_STAGING_2026-10-28.md:79`）。
   **没有这三个，任何「加速了」的说法都无法归因。**

4. **无版本控制**。`rasterix-linux` / `linestream-rs` 都没有 `.git`。
   只有 `external/*` 的 7 个子树有（`RasterIX`、`SDL2`、`tcl`、`tuxracer`、`alinx_board`、
   `gl4es`、`vortex`，实测 `Test-Path .git`）。
   `rasterix-linux` 69.7 GB / 440,872 文件，其中 `build/` 占 64.1 GB（325,360 文件）。
   **这是最大的工程风险。**

5. **`/var/tmp` 私有源码树无备份**。重建 `-Action arm` 依赖它。

### 7.2 可选 / 已知但低优先

- 触摸（GT911 已识别）、MiniDP 输出（驱动注册但 disconnected，无后端）
- 神经风格与 FSR 的组合链路（模块共存 ≠ 已串接）
- 实体键鼠人工验收（目前是 X11 注入按键）

### 7.3 文档口径

`docs/前端与架构全景_20261030.md` 是当前最完整的口径文档。
其中 §7.3 与 §9 是**对外表述的硬约束**，改文档时不要放宽它们。

---

## 8. 下一步：我的建议（标注为判断）

按「不改 PL → 改 PL → 改板务」排序。

### 8.1 立刻做（低成本、可验证）

**① 建版本控制。** 现在 69.7 GB 无 git 是灾难。
建议：`git init` 后只跟踪 `config/ docs/ src/ ports/ linux/ scripts/ sim/ patches/ samples/ generated/ report/*.json`，
用 `.gitignore` 排除 `build/ external/ .Xil/ preserved/ report/*.bin`。
`report/` 只进 JSON/PNG，不进 `.bin`。

**② 补三个计数器再谈优化。** 把 `perfTriangleRendering`、`perfRasterizerStall`、
输入 valid/ready 空泡分别计数，加 CSR。这是**唯一能验证 §5.4 那个判断**的手段。
不改功能，只加只读计数，风险最低。

**③ 验证 §5.4 的「PL 段恒定 11 ms」假设。** 用现有 JSON 就能做一半：
把 8 轮的 `dma wait` 与命令拍数做散点，看是否有相关性。若确认无关，
下一步方向就不是「优化 PL」而是「去掉每帧的同步握手」。

### 8.2 中期（有明确收益路径）

**④ 融合 MVP 矩阵（V1）。** `transform/VertexTransformer.hpp:268` 与 `:298-300`
目前对无裁剪批次做**两次** 4×4 变换（modelView、projection）。
在 `init()` 里预乘 `m_mvp = projection * modelView`，无裁剪时只做一次。
预期砍掉 `Mat44::transform`（12.04%）的约一半。
**风险：浮点误差不可忽略，必须逐位 ABBA 比对**——`prepare_java_sequential.py:28`
的「正文逐字保留」断言框架可直接复用。

**⑤ `java_prepared::View` 去掉 `std::vector` 间接。** `at()` 7.63% + `vector::operator[]` 0.95%
≈ 8.6%，几乎全是 5 个 `const std::vector<T>&` 的 `empty()` + `operator[]` 开销。
换成 `struct{const T* p; size_t n;}`，`empty()` 变 `n==0`。纯 CPU 结构改动，风险极低。

**⑥ 让 `at()` 引用写入。** 现在按值返回 88 B，再被 `pushVertex` 绑定、再被 `PushVertexCmd` 拷一次。
改成 `void at(size_t, VertexParameter&)` + `pushVertex(VertexParameter&&)`。

> ④⑤⑥ 三条全部落在 R85 命中的约 31% 里（`Mat44` 12.04% + `Vec4` 拷贝赋值 11.39% +
> `View::at` 7.63%，样本份额不可相加，见全景文档 §2.2），都不碰 PL ABI；
> ⑤⑥ 不碰数学语义，④ 需位精确验证。做完用 `src/ps/rix_perf_sample.c`
> （`scripts/build_java_cpu_ip.sh:10` 已改成 2 ms 周期）在同一 Tiny 静止场景复测，
> 看 `Mat44::transform` 与 `Vec4::operator=` 的份额是否真降。
> **若没降，说明 O3 已把 ④ 融掉，应转去做顶点格式特化**
> （参考 `ports/classicube/PackedVertexReader.hpp:13-38` 已验证的路径，但它在 ClassiCube 线，
> 搬到 Java 需要新的 `OwnedBatch` 解码路径）。

### 8.3 不要做

- **不要**复活 `Mat44.hpp:101-139` 的 NEON 版本——注释明确写着 *"The assembler version is still slower"*。
- **不要**动 `Rasterizer::increment`（`Rasterizer.cpp:26-74`）的整数语义——
  它与 PL 的 `Y_OFFSET` 逐位耦合，任何改动必须位精确。
- **不要**缩 `ClipList` 尺寸（`Clipper.hpp:40` 9 槽）——会丢顶点。
- **不要**重开 `RIX_JAVA_FPGA_GEOMETRY`——三重标注已放弃。
- **不要**把 `getDisplayLines()` 从 3 降到 2——那会改 PL 条带契约，需要新位流。
- **不要**在没有新计数器的情况下声称定位了瓶颈。

---

## 9. 对外表述红线

竞赛与文档口径（源自 `.workbuddy/memory/2026-10-28.md:8` 与全景文档 §9）：

1. 不写「稳定 60 / 满帧」。实测 24.9–25.7 FPS，未达 32。
2. 不写「GPU / 可编程着色器」。这是固定功能管线。
3. 不写「自研光栅器」。RasterIX 是 GPLv3 上游（`9269a01c…`），必须署名。
4. 不写「神经超分」。CNN 是 3 层 INT8 小网络，7×7 感受野，不是完整 GAN。
5. 不写「FSR2 / FSR3」。是 FSR1（EASU12 + RCAS5），空间域，**无运动矢量**。
6. 不写「全部渲染在 PL」。几何 12 阶段在 ARM。
7. 不写「几何前端已上板」。`0xbc=0`，`hardware_built:false`。
8. 不写「完全不经过 PS DDR」。恰恰相反，PS DDR 是主通路。
9. 不写「完整 Minecraft」。是 1.2.5 的静止超平坦场景短测。
10. 不写「1080p」。是 400×240 渲染 + 800×480 显示。
11. 不宣称「CNN + FSR 联合帧率」——模块共存不等于已串接。

---

## 10. 一页速查

```
板卡      ALINX AXU3EG / xczu3eg-sfvc784-1-i
时钟      GPU/控制 100 MHz（pl_clk0）· PL DDR4 200 MHz（MIG）· 像素 33.333 MHz（200/6 MMCM）
LCD       AN970 800×480 @ J16，1056×525×60.125 Hz
渲染      400×240 RGB565 → 内部 3×5bit 子像素（无 alpha）→ RGB565 流出
呈现      帧桥 → PL DDR XRGB8888（stride 1600）双 slot → 扫描/缩放 → LCD

主线库    build/minecraft-java-125/sequential-batch/libGL-sequential.so.1  = 8e89c36f
主线位流  build/minecraft-java-125/dual-tmu/board/java256.bin              = 14fd58da
恢复位流  build/fsr-pl/fixed-v23-bufferedread/board/fsr.bin                = 035c3059
SD 现状   build/sdcard/BOOT.BIN = 8f26ae5a（PL 分区 fc3a6e37，单 TMU）
主线包    build/minecraft-java-125/arm-mainline-r3/

构建      .\build.ps1 -Action arm            只重建库，不碰硬件
          .\scripts\build_java256_dual.ps1   重建主线位流（不经 build.ps1）
串口      PS COM11 115200 · PL COM15（JTAG-HS1 210512180081，6 MHz）
下一轮号  r134

三把锁    rasterix-game-launch.lock · rix-superres.lock · rix-mc-style-extract.lock
隔离      /opt/rasterix/experimental/gpu-quarantine.json（同 boot_id 失败即禁跑）
receipt   /tmp/rix-fpga-fsr/active-receipt.txt（4 行，v23 口径）
          /tmp/rix-fpga-java256/active-receipt.txt（RIX_TEX256_CACHE_ACTIVE_V1）

帧预算    T = 38.16 ms ≈ ARM 串行 25.01 ms + DMA 等待 11.13 ms
命令量    321,492 拍/帧 ≈ 6,561 三角形/帧 ≈ 1.23 MiB/帧
吞吐      提交 32 MiB/s vs 链路能力 3.3 GiB/s → 带宽不是瓶颈
```

---

## 附：本文引用的关键文件

| 主题 | 文件 |
|---|---|
| 当前路线选择 | `config/java_arm_mainline.json` |
| 板级硬件共同配置 | `config/rasterix_axu3eg.json` |
| 构建入口 | `build.ps1`、`build_local.ps1`、`scripts/build_java256_dual.ps1` |
| ARM 主线重建 | `scripts/build_java_arm_mainline_r1.sh`、`scripts/prepare_java_arm_mainline_r1.py` |
| 上板事务 | `linux/java_minecraft/run_java256_trial.py`、`linux/postproc/fpga_fsr_control.py` |
| 隔离守卫 / 遥测 | `linux/game_runtime_support.py` |
| DMA 连接器 | `src/ps/DMAProxyBusConnector.cpp`、`linux/dma-proxy/rix_dma_proxy.c` |
| 呈现 fence | `src/ps/rasterix_presenter.hpp`、`build/minecraft-java-125/sequential-batch/glx.cpp` |
| CPU 采样器 | `src/ps/rix_perf_sample.c` |
| 板级 RTL | `src/rtl/{top,gpu,video,common}/`、`src/board/` |
| 位流私有覆盖 | `build/minecraft-java-125/dual-tmu/rtl/rasterix_linux_top.v` |
| 架构与证据全景 | `docs/前端与架构全景_20261030.md` |
| 竞赛计划 | `docs/contest_14_day_plan_2026-10-26.md` |
| 提交文案 | `AMD赛道_提交文案_最终版_2026-10-28.md`（在 `prj2/` 根，不在 `rasterix-linux/` 下） |

---

## 附二：接管后第一小时该做什么

按顺序，前四步都不碰硬件：

1. `Get-ChildItem rasterix-linux\docs\*.md | Sort-Object LastWriteTime -Descending | Select -First 10`
   —— 确认自己没有漏掉比本文更新的文档。
2. 读 `config/java_arm_mainline.json` 全文（65 行）+ `docs/JAVA125_CURRENT_PROFILE.md`（22 行）。
   **这两份就是"当前要做什么"的全部答案。**
3. 读 `docs/前端与架构全景_20261030.md` §0 / §3.3 / §7 / §9 —— 架构、条带约束、缺口、口径红线。
4. `.\build.ps1 -Action arm` 跑一次，确认本机能重建主线库并复现
   `ARM_MAINLINE_ALREADY_VERIFIED`（或首次 `ARM_MAINLINE_PREPARED`）。
   若失败，先修 WSL `/var/tmp/rix-java-*` 与 `build/sdk-2020.1`，**不要**去动板上任何东西。
5. 到这一步再决定要不要上板。上板前必须：读 `boot_id`、确认隔离文件不存在、
   确认 GPU 空闲、持三把锁、准备好回滚包。**照抄 `run_java256_trial.py` 的结构，不要自己写。**

**第一次上板前不要做的事**：不要写 SD、不要改 `BOOT.BIN`、不要改时钟、不要换 PMIC/PLL、
不要在没有 `restore_dir/manifest.json` 的情况下切位流。
