# FPGA FSR1 第二轮优化

本轮接着已验收 v8（完整 EASU12＋RCAS5、400×240→800×480、实测新输出 8.468 FPS）继续优化，保持定点像素结果、原有 RasterIX 和 CNN。`fixed-v10-pipeline` 已于 2026-10-24 完成整机来源核对、RAM 加载、三组全帧／LCD 核验和真实游戏对照。原调度实测约 14.73 FPS，POST／LOAD 重叠调度 15.47 FPS，快照预取 **18.52 FPS**，游戏源仍约 60.10 FPS。下表是 HLS 结果，与后文板端 FPS 分开记录。

| 候选 | 结构 | HLS 最大计算延迟 | LUT | DSP | BRAM18K |
|---|---|---:|---:|---:|---:|
| v8 | EASU16、RCAS8、行写依次执行 | 97.196 ms | 31,187 | 112 | 117 |
| schedule-e12-r6 | 启动间隔缩至 12／6，仍顺序执行 | 74.093 ms | 31,903 | 118 | 117 |
| schedule-e8-r4 | 复制部分共享单元，间隔 8／4 | 51.020 ms | 39,971 | 180 | 119 |
| v9 dataflow | 16／8，EASU、RCAS、写回并发 | 61.514 ms | 30,354 | 112 | 122 |
| **v10 pipeline** | **并发＋12／6** | **46.138 ms** | **31,088** | **118** | **122** |
| v11 burst | v10 结构，额外固定每次内部写请求为 64 words | 46.138 ms | 31,153 | 118 | 122 |
| v12 e10r6 | v11 结构，增加 EASU 共享单元供给，间隔 10／6 | 38.458 ms | 33,674 | 150 | 124 |

8／4 候选需要额外约 8,784 LUT，超出本轮合理的整机增量预算，因此没有直接推进整机。v10 在 HLS 估计中比 v8 少 99 LUT，增加 6 DSP 和 5 个 BRAM18K；整机资源仍必须以 Vivado 布线报告为准。

## 数据流和数值验证

v8 每行先计算 EASU，再执行 RCAS，最后写 DDR。v10 把三阶段分成并发任务：EASU 经 1024 深度、73-bit 像素 FIFO 向 RCAS 发送颜色和错误标志，RCAS 用自己的三行缓存，经 1024 深度输出 FIFO 交给写回任务。writer 先收集 64 个 word，再连续写出；现有 EASU 和 RCAS 算术不再在时间上互相等待。

v10 的 EASU／RCAS 实际启动间隔为 12／6 拍。定点算术只改变综合调度，不改变数值表达式。每个候选独立检查 13 张原始功能图和 6 张压力图，共 7,296,000 个输出像素，与已验收 v8 输出逐字节一致。v10 证据在 `build/fsr-pl/fixed-v10-pipeline/functional/result.json`；源 manifest SHA256 为 `c4dc275a97ae345d4b9d26051c39d9d1d3f927a44b424913b62842978e7b7813`。

v10 的缩小 C/RTL 为 8×6→16×12、两帧、九次调用、16-entry FIFO，实际 PASS。原 manifest 的 `axi_depth_unchanged:true` 是元数据错误：该缩小版本输出 AXI 深度也变成 192，因此其 RTL 输出捕获只覆盖有效的 192 像素；超出该范围的 guard 属于 native C 检查。更正独立保存在 `protocol-audit-r2.json` 与 `protocol-audit-final.json`，没有重写冻结源或原报告。v9 的小源 manifest 摘要另有不一致，不能拿它替代 v10 的验收证据。

v11 是备用候选，已通过完整 19 图和缩小 C/RTL；其缩小版保留 AXI 原始深度并检查输出 guard。v12 进一步将 EASU 启动间隔降到 10，代价是增加约 2521 LUT、32 DSP，完整 19 图也与 v8 一致；目前只完成 HLS 与 native 数值检查。两者均没有启动新的整机构建，不能用其估计替代当前 v10 的最终实测。

## 所有权与 DDR 边界

CSR 控制 RTL 与已验收 v8 逐字节一致。完成路径为：最后 B 响应被适配器接收，writer 完成，DATAFLOW 等待 writer 与 fault task，顶层随后发出 AP_DONE。ARM 仍等待 AP_DONE 并核对返回码、帧标记后才发布高分辨率 bank。

v10 生成器将内部 AXI 请求提升为一帧的 384000 words，外部按最大 64 beats 和 4 KiB 边界分割；适配器启用 conservative 写策略。v11 用独立、非 inline 的 `store_burst` 把内部请求也限制成每次 64 words，等待本块最后 B 后才开始下一块，HLS 延迟未增加。两者的旧 GPU 错误计数都不能代替 FSR master 的响应检查：BRESP/RRESP 仍未传播至 `ap_return`，实际全帧金标准和 LCD 核验必不可少。

## 调度优化与实机对照

独立的 `linux/postproc/rix_fsr_pl_overlap.cpp` 只改变 ARM 调度：一帧计算结束并提交显示后，先取得下一帧 SNP1 快照并完成 LOAD，再确认上次 POST ACK。下一次 COMPUTE 仍在 ACK 后选择非活动 bank，LOAD 与 COMPUTE 继续串行；正常游戏没有 CPU 像素处理。

六项本地顺序和故障模型检查通过，包含停止时排空 COPYING、LOAD 完成后错误清理、缺失 POST ACK 时不写下一 bank，以及 AXI 未完成时保留 quarantine 和共享锁。候选不会替换原 `rix_fsr_pl.cpp`。

本次启动的四轮 ABBA 已实际通过，每次游戏运行 32 秒、测量约 20 秒，世界 64³、视距 32、400×240、style0、自动移动、CPU 上限 120 FPS。源帧率与完整 FSR 新输出独立计时，窗口内不抓图。

| 轮次 | 调度 | 源 FPS | FSR 新输出 FPS |
|---|---|---:|---:|
| A1 | 原版 | 60.168 | 8.45752 |
| B1 | POST／LOAD 重叠 | 60.124 | 8.68996 |
| B2 | POST／LOAD 重叠 | 60.130 | 8.66145 |
| A2 | 原版 | 60.037 | 8.50824 |

按完成帧数／累计测量时间加权，原版 **8.48286 FPS**、候选 **8.67569 FPS**，约 **+2.273%**。全部四轮正常退出，同世界、错误计数为零、SNP1 无过期和重试，游戏 profile 及显示模式恢复。收益较小，仍需新算术流水解决主瓶颈；新位流上是否有同样的调度收益须另测。

候选 AArch64 ELF SHA256 为 `ee7478cdee554a3228d79ae732836754fa9ba876f58aeaf9deee95a28ed50b79`，放在板端 `/tmp/rix-fsr-overlap/rix-fsr-pl`，原控制程序保留。93 文件回读包 `report/postproc_fsr_opt_v8_0881_evidence.bin`（tar.gz，47,357 B）SHA256 为 `98cbb6ffc8bb76d3c3cbf1b8b4cc6f28e6b5f07c8ab5fc16959eac704714bafd`，包含本次启动的三组全帧核验、LCD 采样、四轮游戏日志及加载凭证。

用户重新上电后，RAM 状态已重建；当前启动 ID 为 `0881389e-f309-46ce-ad04-0bb5a0a0c8ec`。原 SD 中的启动包保持原样。atomic-v4 与 v8 的新加载凭证、完整静态验证均在本次启动重新生成，没有沿用旧 boot ID 的通过结论。

## 整机实现与验收

工程为 `build/vivado_fsr_fixed_v10_pipeline/rasterix_fsr_fixed_v10_pipeline.xpr`。成功完成的实现 run 为 `impl_short_r2`，使用 `launch_runs -dir build/fsr-v10-runs-r2`；以下为实际整机布线结果。

| 资源 | 实际使用量 | 占用率 |
|---|---:|---:|
| LUT | 62,514 / 70,560 | 88.60% |
| FF | 62,972 / 141,120 | 44.62% |
| BRAM Tile | 197 / 216 | 91.20% |
| DSP | 277 / 360 | 76.94% |

整机 WNS 为 **0.870 ns**、WHS 为 **0.011 ns**、WPWS 为 **0.124 ns**。导出的 raw 位流 SHA256 为 `80667dc03952e1f9f304dc6a97bb20cd46a8f43b7f495e23bf88491861a31fc5`。

首次实现曾被 Windows 调试核生成临时路径 151 字符超过 146 限制中断，原 `impl_1` 和日志保留；新的短路径 run 复用已完成综合并完成逻辑优化、布局、布线和导出。独立项目来源审计已经通过，读取既有设计中的约束，不临时 source XDC。早期逐网路由字符串／PIP 枚举内存开销过大，各次中止记录保留；最终从成功 run 与导出 DCP 各自原生重生成配置，**两份全部 4,748,048 B raw 配置均与发布候选逐字节相同**，没有屏蔽或归一化任何配置字节。

审计核对 1554 个实际工作区文件、所有综合 run 的非过期状态、当前实现、FSR 地址、PS 保留内存、100 MHz PL 时钟，以及既有 DCP 中的 CDC／reset 约束。Vivado 将七份 HLS ROM/RAM `.dat` 放在实例目录，RTL 放在 `ipshared`；两处实际注册输入均与 HLS 导出逐字节一致。审计结果为 `report/fsr-pl/fixed-v10-pipeline/board/project-audit/verified.json`，整机阶段验收为同级 `board/acceptance.json`。

后续产物由 `accept_fsr_optimized_board.py`、`prepare_fsr_optimized_runtime.py`、`prepare_fsr_qa_optimized.py`、`package_fsr_optimized_ram.py` 依次绑定。每步校验实际 SHA256 和阶段结果，不生成缺失的通过证据；旧 v8 和失败候选均保留。当前没有更新 SD BOOT，也没有把本轮 FSR 串联到神经风格入口。

## 2026-10-24：v10 实机结果

本次启动为 `11f7effc-6138-45a4-af2e-f3608360cf5d`。开发板重新启动后，先重新加载 atomic-v4 并建立本次启动的回退证明，再通过保留的 PS RAM 窗口传输 v10；所有压缩包、raw 位流、程序和测试向量均完成回读 SHA256 核对。Linux FPGA Manager 的实际事务为 `passed / new-loaded-and-verified`，加载后才访问 FSR CSR。所有新增板端文件在 `/tmp`，SD BOOT 没有更新。

三幅完整 800×480 输出均与 v8 的定点金标准零差异，LCD 6000 点也为零差异。静态 COMPUTE 为 46.220／46.292／46.287 ms；游戏中约 **46.27 ms**，比 v8 游戏中的约 97.64 ms 缩短约 52.6%。静态 LOAD 约 1.11 ms，游戏 LOAD 约 5.6 ms，二者的输入位置与并发负载不同，不能互相替代。

同场景首次对照：流式双线性新输出 **60.1313 FPS**；v10 原调度 FSR 新输出 **14.7568 FPS**，启用 FSR 时游戏源 **60.1318 FPS**。随后四轮 ABBA 使用同一 64³ 地图、视距 32、400×240 源、800×480 显示、style0、120 FPS 上限和自动移动，各轮游戏 32 s、FSR 测量约 20 s；窗口内没有像素抓图或文件传输。

| 轮次 | v10 调度 | 源 FPS | FSR 新输出 FPS |
|---|---|---:|---:|
| A1 | 原版 | 60.0916 | 14.7525 |
| B1 | POST／LOAD 重叠 | 60.0972 | 15.5638 |
| B2 | POST／LOAD 重叠 | 60.1293 | 15.3682 |
| A2 | 原版 | 60.1247 | 14.7120 |

按完成帧／累计测量时间加权，原版 **14.73224 FPS**，重叠调度 **15.46597 FPS**，收益 **4.9805%**。重叠调度每帧约 COMPUTE 46.269 ms、LOAD 5.564 ms、SNP 等待 12.611 ms、剩余 POST 等待 0.199 ms。下一项预取试验针对剩余 SNP 等待，不改变 FPGA 的像素算术。

所有已结束轮次均正常退出、GPU 五类错误计数为零、SNP 无过期，profile 恢复，GPU 客户端排空。122 个文件的回读包 `report/postproc_fsr_opt_v10_11f7_evidence.bin`（60,293 B）SHA256 为 `b95e8b0bbdf9097ac050534f597ffba69cc88779615a7084b816166502916757`，已由 PC 独立核对三幅输出 SHA、LCD 数据、加载凭证、运行程序和四轮加权结果。实际验收为 `report/fsr-pl/fixed-v10-pipeline/optimization-11f7-acceptance.json`，原始提取文件在同名无后缀目录。

## 快照预取：当前最佳实验运行程序

独立的 `linux/postproc/rix_fsr_pl_prefetch.cpp` 先用首帧校准真实 COMPUTE 时间，再在后续 COMPUTE 预计结束前约 12 ms 请求下一帧 SNP。当前 COMPUTE 使用内部 input cache，下一份快照使用独立的 PL DDR 目的区；LOAD 与 COMPUTE 仍然串行。AP_DONE／返回 tag 核验后，才发布当前 bank、完成下一次 LOAD、等待 POST ACK 并选择后续输出 bank。LOAD 启动前和结束后重新验证租约；异常必须排空正在执行的 kernel，超时继续保持 quarantine 和共享锁。重复源 tag 在 LOAD 前丢弃。

同源码的 16 项 host mock 检查通过，覆盖停止、取消、过期、callback 异常、重复帧及 tag 回绕；基于已验收 v10 header 独立交叉编译。原 baseline 与 overlap 程序均保留，原有公开游戏入口没有替换为这个实验程序。

再次执行同条件的四轮 ABBA：

| 轮次 | v10 调度 | 源 FPS | FSR 新输出 FPS |
|---|---|---:|---:|
| A1 | 原版 | 60.0521 | 14.7912 |
| B1 | 快照预取＋POST／LOAD 重叠 | 60.1091 | 18.6256 |
| B2 | 快照预取＋POST／LOAD 重叠 | 60.0958 | 18.4081 |
| A2 | 原版 | 60.1618 | 14.7529 |

加权结果为原版 **14.77204 FPS**、预取 **18.51676 FPS**，同位流同次启动收益 **25.3500%**。两个预取窗口完成 742 帧，重复帧、SNP 过期、stale 丢弃、重复快照重试均为零。平均每输出帧 COMPUTE 46.287 ms、LOAD 4.378 ms、剩余 SNP 等待 2.771 ms、POST 等待 0.544 ms；预取实际提前约 11.859 ms，最大请求年龄 32.126 ms。两轮合计 738 次预取请求，其中 526 次在 COMPUTE 结束时已经 READY。

与此前另一次启动的 v8 原调度加权 8.48286 FPS 相比，当前最佳结果约 **2.183 倍（+118.3%）**。这是相同地图及参数的历史比较；25.3500% 才是本次同位流、同次启动 ABBA 的调度收益，不能将不同试验的百分比直接相加。

预取证据另存于 `report/postproc_fsr_prefetch_v10_11f7_evidence.bin`，61,101 B、123 文件，SHA256 `a0a58f10b2bf73d6b37d5e0617c3f7b09976d13a603cb611509925b7cb33edd8`。PC 独立重新核验完整配置绑定、静态金标准、LCD、源与输出帧数、地图／程序一致性、退出及恢复条件、四轮加权结果和预取租约／唯一帧统计，实际验收为 `report/fsr-pl/fixed-v10-pipeline/prefetch-11f7-acceptance.json`。归档读取的四种不安全路径／链接案例和六项错误预取统计均被拒绝。

本轮推荐记录为 `report/fsr-pl/fixed-v10-pipeline/runtime-recommendation.json`，最佳 AArch64 ELF 为 `build/fsr-pl/fixed-v10-pipeline/runtime-prefetch/rix-fsr-pl`，SHA256 `6b98a19d7aba7eaafd17e292bead741ec2718fdbb78b650f8e5e6ab7a5652cb5`；本次启动板上路径为 `/tmp/rix-fsr-prefetch-v10/rix-fsr-pl`。所有验证结束后已恢复双线性空闲状态，GPU 客户端排空、错误计数为零，root／SD 的 32／16 MiB 空间保护未降低。位流和实验程序仅在 RAM；断电保持、公开入口默认切换和神经风格串联均未包含在此次验收中。
