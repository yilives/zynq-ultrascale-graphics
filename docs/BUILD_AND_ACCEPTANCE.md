# 构建与验收记录

更新：2026-10-18。此记录区分源码实现、宿主测试、目标编译和物理板验收。两项 P1 的修复与负向复现见 [阻断修复记录](BLOCKER_FIX_2026-10-16.md)；BL31 后的控制树修订及写卡结果见 [启动修复记录](BOOT_FIX_2026-10-16.md)。Linux 启动和 RGB LCD 游戏启动图已确认；布局修订完成板测、像素读回、SD 持久化和正常重启验证，见 [比例修复记录](LCD_LAYOUT_2026-10-18.md)。用户暂时无法观察修复后的 LCD。

## 本地验证

| 检查 | 入口 | 结果证据 |
|---|---|---|
| GPU 命令与 framebuffer DDR 完成 | `scripts/run_gpu_sim.ps1` | `report/tb_gpu_normal.log` |
| 非 OK DDR B 阻止 swap | 同上 | `report/tb_gpu_fail_bresp.log` |
| STORE→LOAD 实际 GPU DDR/RX | 同上 | `report/tb_upload.log` |
| RGB565→XRGB 帧桥、1000 次换页、错误恢复协议 | `scripts/run_sim.ps1` | `report/tb_display.log` |
| 2× 行复用、视频时序、欠流恢复 | 同上 | `report/tb_scale2x.log` |
| AXI-Lite 背压、WSTRB、独立 AW/W、计数快照 | 同上 | `report/tb_control.log` |
| 复位立即生效、停钟、五边沿释放 | 同上 | `report/tb_domain_reset.log`、`report/reset_cdc.rpt` |
| 模块接口、DMA 连接器、CLI、纹理越界检查 | `scripts/host_compile_check.sh` | `report/*host_compile.log`、`report/texture_resize.log` |
| 游戏 + 板上 smoke API/链接 | `scripts/host_game_build.sh` | `report/game_host_build.log`、`report/game_host_elf.txt` |
| 真实渲染器三片区初始化、旧容量/ABI 拒绝 | `scripts/test_dma_initialization.sh` | `report/dma_initialization.json`；内存设备替代系统调用，未测试物理 DMA |
| GPU/显示顶层综合 | `scripts/top_ooc.tcl` | `build/top_ooc/checks.txt`、`utilization.rpt`、`cdc.rpt` |
| 板级 BD 和 IP 生成 | `scripts/create_board.tcl`、`elaborate_board.tcl` | `report/board_create_console.log`、`board_elaborate_console.log` |
| 整机 RTL / 布线 / bit 与 XSA | `scripts/build_board.tcl` | 正式项目综合与实现；本次重建见 `report/blocker_fix_hardware_console.log` 和 `report/board_*` |

宿主测试产物为 x86_64，不能部署到 A53。仿真 AXI 存储模型并不代表物理 DDR 已训练，也不能证明 SD/USB/Linux 可启动。OOC 的综合时序尚未经过整机布线。

Vivado 2026.1 的 `synth_design -rtl` 在扁平展开 SmartConnect/MIG 时发生进程崩溃；完整设计使用项目的分层 IP 综合和正式实现流程验证。该失败的 RTL-only 检查不作为通过证据。

每个时钟域分别同步 PS/button、MIG ready 和像素 PLL lock，四级同步链之后再用本域寄存器发布复位；停止时钟时仍立即断言。GPU 就绪状态复用同一条 MIG 同步链，避免两条独立同步链重汇合。异步复位断言引脚单独施加 false path，数据握手和保持总线继续检查 20 ns max delay / 10 ns bus skew。没有整体切断时钟组或豁免 Critical CDC；完整布线的 CDC、建立/保持和总线偏斜均是导出及打包的硬性条件。

2026-10-16 最终整机布线及复核结果如下，包含 PS、MIG、DMA 和 SmartConnect：

| 项目 | 最终结果 |
|---|---|
| LUT / CLB 寄存器 | 25433 / 33551，分别占 36.04% / 23.77% |
| BRAM / DSP | 77 / 87，分别占 35.65% / 24.17% |
| 建立 / 保持 | WNS=1.147 ns，WHS=0.010 ns；TNS=THS=0，失败端点为 0 |
| CDC | Critical=0；CDC-3 Info 162，CDC-9 Info 8，CDC-15 Warning 660 |
| 保持总线偏斜 | 本工程 10 ns 约束实际 3.495 ns，余量 6.505 ns；IP 偏斜检查也通过 |
| 内部路径 | 无未约束内部端点、无时钟寄存器、组合环或锁存器环 |
| bit / XSA | 正式 bitgen 和含 bit 的 XSA 导出通过；发布清单核对两者内容一致 |

剩余 Warning 保留在报告中。CDC-15 的 591 条来自 SmartConnect/XPM FIFO，69 条来自 64 位计数快照及 5 位呈现槽/帧号的保持总线；后者由同步请求/确认控制采样，源数据保持到确认，且检查 max delay 和 bus skew。`TIMING-9` 对这些使能采样结构给出提示，`TIMING-38` 提示保持总线约束包含多个时钟方向；这些检查没有被整体屏蔽。

DRC 有 146 条 Warning，主要是 DSP 输入/输出流水级建议，其余涉及未使用时钟、LUT 项和 BRAM 碰撞模式；方法学报告有 13 条 Warning 和 2 条 Advisory，均无 Error/Critical。`LUTAR-1` 的 10 条中，3 条对应本工程各域同步链末端的本地复位组合，7 条位于 MIG/debug hub。各同步链末端只在本域边沿释放，组合结果再经本域寄存器发布；异步就绪丢失和停钟断言由复位仿真覆盖，物理就绪/DDR 训练仍待上板。`ULMTCS-1` 与像素 PLL 的 `CLKC-30/56` 保留为资源/时钟布局提示。外部时序例外仅为异步 `sys_rst_n`、`ddr4_reset_n`、状态 LED；`lcd_dclk` 是转发时钟，LCD 数据和控制输出有相对该时钟的延迟约束。

## 目标 Linux 构建与镜像

资料盘 SDK 可以通过 `scripts/install_vendor_sdk.sh` 局部安装。首次安装遇到旧 relocator 错误时，运行 `scripts/repair_vendor_sdk.py`、SDK 的 `relocate_sdk.sh`、`scripts/finish_vendor_sdk.py` 后再使用 `scripts/use_vendor_sdk.sh`。SDL2 2.0.20 / Tcl 8.6.12 缺项由 `build_sdk_dependencies.sh` 从固定提交构建到 `build/target-deps`，并记录 AArch64 ELF；来源分别为 [SDL 官方仓库](https://github.com/libsdl-org/SDL/tree/release-2.0.20) 和 [Tcl 官方镜像](https://github.com/tcltk/tcl/tree/core-8-6-12)。这个 SDK 兼容编译仍与可启动镜像分开验收。

Windows 已安装 Vitis 2026.1。该版本的 XSCT 入口明确报告禁用，脚本使用 [AMD 2026.1 Python 平台构建接口](https://docs.amd.com/r/en-US/Vitis-Tutorials-Embedded-Software/Create-Vitis-Platform)。硬件 XSA 生成后运行 `scripts/build_vitis.ps1`，从本次 XSA 生成 FSBL，并为 `psu_pmu_0` 创建 PMUFW 域及应用。`report/vitis_boot_artifacts.json` 只接受实际构建的固件，不接受 QEMU 目录中的预编译文件。Windows 的 R: 仅映射本工程 build，供 Vitis 避开 MAX_PATH 限制。

本次已构建 Linux 5.4.0 Image 及匹配其完整 Module.symvers 的两个 AArch64 模块。游戏、smoke、CLI、SDL2/Tcl 及 28 个运行依赖 ELF 已完成架构和依赖闭包检查。Xorg dummy 0.3.8 使用同一 SDK 的 Xorg 头文件编译，作为 SDL 输入窗口后端；LCD 像素由 PL 输出，因此不要求另接 DisplayPort 显示器。其来源和摘要在 `config/x11_dummy.json`，归档来自 [X.Org 官方发布目录](https://www.x.org/releases/individual/driver/)。USB 输入和窗口焦点仍须物理验证。

启动固件采用 Vitis 2026.1 FSBL/PMUFW，以及固定提交的 AMD TF-A/U-Boot 2026.1。TF-A 放在 Linux 内存图已排除的低 DDR 顶部：`0x7ff00000..0x7ff7ffff`；PMU 的顶部保留区与其分开。U-Boot 链接地址为 `0x08000000`，Linux Image 载入 `0x10000000`，DTB 载入 `0x00100000`。U-Boot 禁用旧 NAND/QSPI/FAT 环境和扫描式 preboot，使用本工程 SD1 启动脚本。U-Boot 要求 GCC≥10，使用独立的 Ubuntu AArch64 GCC 11；Linux/用户态仍用资料盘 GCC 9.2 SDK。

U-Boot 显式构建上游 `u-boot.elf` 目标，以 ELF 封装含控制 DTB 的完整 `u-boot.bin`。打包门禁比较 ELF 可装载字节、尾部控制 DTB 和实际 BOOT.BIN 的 U-Boot 分区，结果写入 `report/uboot_control_dtb.json`；供 Linux 加载的单独 DTB 不能替代这个检查。

U-Boot 控制树由 `scripts/uboot_control_fdt.py` 单独生成到 `build/boot-firmware/u-boot-control.dtb`，将旧 `u-boot,dm-pre-reloc` 迁移为 U-Boot 2026.1 使用的 `bootph-all`，并补齐祖先节点的阶段标记。生成和发布检查覆盖 UART0、父总线、时钟和固件依赖，Linux 5.4 的 `system.dtb` 字节保持不变。已启用 UART0 早期调试输出 `<debug_uart>`，用于后续板测定位。真实旧树拒绝及移除 UART/总线/参考时钟标记的负向回归见 `report/uboot_early_console_regression.json`。

设备树以资料盘的 Linux 5.4 PS/GT 绑定为底座，PL 节点来自新 XSA 的 SDT。投影明确将中断父节点转换到 Linux GIC（DMA SPI 89/90），保留单个 GPU 地址节点，排除原 SDT 的 R5/OCM/QSPI 重叠 memory 节点，并禁用当前 PS 预设没有启用的 UART1/I2C0。文件和来源摘要位于 `build/linux-dts` 与 `report/linux_dts_sources.json`。SDT 入口使用 Tcl 可接受的绝对正斜杠路径，在全新目录生成文件，并在 `report/sdt_generation.json` 记录 XSA/输出摘要；设备树投影必须核对这些摘要，不能以旧输出文件的存在作为成功依据。

在当前项目目录可复用已验收硬件运行 `build_local.ps1`；`-RebuildHardware` 会先新建板级工程并重新实现。所需 Ubuntu 构建工具包括 cmake、gcc/g++、make、unzip、flex、bison、swig、python3-dev、libssl-dev、uuid-dev、libgnutls28-dev、device-tree-compiler、gcc-aarch64-linux-gnu、dosfstools 和 mtools。编译缓存位于 WSL `/var/tmp/rasterix-*`，项目输出仍在本工程 build。SDK 安装到 build，不替换资料盘或 `/opt`。

本地 SD 输出在 `build/sdcard`：`BOOT.BIN`、`Image`、`system.dtb`、`boot.scr`、1 GiB `rootfs.ext4` 和 1.5 GiB `AXU3EG_RasterIX_Linux_TuxRacer.img`。镜像使用 MBR，第一分区 128 MiB FAT32，第二分区 1 GiB ext4，root PARTUUID=`52495831-02`。构建脚本只操作项目中的普通文件；FAT 启动文件回读比对和 ext4 e2fsck、目标 ELF/模块/151 个素材检查均有报告。最终产物必须通过发布清单中的实际哈希与检查；本地打包不表示开发板已启动。

最新交叉检查记录在 `report/release_manifest.json` 的 `local_release_checks`；布局修订打包日志为 `report/lcd_layout_release_package_console.log`。在原 24 项检查上，新增精确像素命令、真实 Renderer 前后缓冲读回和 LCD 布局三项门禁。ext4 回读覆盖 28 个运行 ELF、两个模块、Xorg dummy、启动配置及 151 个素材；SDL 库的符号链接和目标内容分别核对。Bootgen 只读解析记录在 `report/bootgen_read.log`，实际分区确认 FSBL 位于 OCM `0xfffc0000`，BL31 位于 `0x7ff00000`，U-Boot 位于 `0x08000000`，其控制 DTB 位于 `0x08188c38`，PL bit 和 PMUFW 均已打包。ARM64 Image 的实际头信息将内核重定位到 `0x10080000`，与 DTB、脚本、U-Boot、BL31 和图形保留区不重叠，见 `report/boot_memory_layout.json`。

完整 SD 镜像为 1610612736 字节，当前 SHA256 见 `report/sd_image.json` 和发布清单。历史控制树修订镜像摘要 `5d35181adc219dddfb1c673c5166e5ad02580e54f0d478298f0e19fb2c235987` 仅属于 2026-10-16 的那次打包。实际卡片若只更新 FAT 启动文件，以原始 FAT 回读提取的四文件摘要验收；通过 Linux 更新程序时，以各文件摘要验收，均不能声称整卡与新镜像逐字节相同。用户态更新后先运行 `scripts/build_rootfs.sh`，再运行 `build_local.ps1 -PackageOnly`；后者只核验并打包已存在的根文件系统。该入口仍执行内容、地址和来源一致性检查，FAT 回读使用 `mcopy -n` 非交互覆盖已有 Unix 验证文件。

以下为迁移到完整 PetaLinux 工程时的集成顺序；本次也提供了以上独立的本地构建路径：

1. 在受支持的 Linux 构建主机上准备 PetaLinux 与匹配 SDK。资料盘提供了 2020.1 BSP/SDK；当前硬件使用 Vivado 2026.1。旧版工具不能直接视为已支持新版 XSA，必须记录实际导入、FSBL/PMUFW、DT 和内核结果。优先采用与 Vivado 匹配的 PetaLinux 工具构建新镜像，使用旧 BSP 作为 DDR/MIO/PS 外设参考。
2. 使用新 `build/rasterix_linux.xsa` 导入一个 ZynqMP Linux 项目。不要把出厂 `system-user.dtsi` 中的摄像头、旧 AXI Ethernet、frmbuf、VDMA 节点复制到新硬件，它们对应的 PL IP 已不存在。
3. 将生成的 `generated/rasterix-system-user.dtsi` 合入项目的 `system-user.dtsi`。检查 XSA 生成的 DMA 标签是否为 `axi_dma_0`，核对 `amba_pl` 的两级地址单元及 `0xA0000000/0xA0010000`。加入 `linux/axu3eg-ps-peripherals.dtsi` 中与当前 PS 外设对应的覆盖。
4. 合入 `linux/kernel.cfg`；内核必须启用 Xilinx AXI DMA、CMA/连续内存、USB host、HID/input 和 misc device。DMA ABI 为 2，每方向 8 个 1 MiB 槽，各分配约 8 MiB coherent ring，合计 16 MiB 数据及 16 KiB 对齐开销；64 MiB CMA 与图形 32 MiB 保留区分开。TX 0–5 用于三片区双缓冲，TX 7 独立用于资源暂存，TX 6 保留。
5. rootfs/SDK 中准备 SDL2、Tcl 8.6、Python 3、libstdc++、线程库及对应开发头文件。SDL 用于事件窗口和输入，最终游戏图像由 PL LCD 显示。
6. 导出 SDK，source 环境；将 `KERNEL_BUILD` 指向同一个部署内核已配置、准备并带符号版本的构建目录，运行 `scripts/build_linux.sh`。输出位于 `build/target-rootfs`。对游戏、smoke 和模块核对 ELF Machine=AArch64、内核 release/vermagic；缺少 Module.symvers 的模块构建不作为部署验收。
7. 将模块集成进 BSP 并由该 BSP 打包 BOOT.BIN、image.ub/DTB、rootfs。FSBL、PMUFW、U-Boot、bitstream 和 DTB 必须属于本次硬件；保留厂商出厂镜像作为回退包。SD 卡格式化/烧录在确认实际目标设备后单独执行。

本项目不把资料盘原有 Ubuntu/BOOT.BIN 复制为“新 GPU 启动镜像”。该镜像没有新的 DMA/GPU 硬件和图形保留区。

## 板上顺序

先从启动日志确认 PS DDR 容量、USB host、DMA IRQ 和驱动加载，再确认设备：

```bash
insmod /opt/rasterix/modules/rix_dma_proxy.ko
insmod /opt/rasterix/modules/plgpu_display.ko
ls -l /dev/dma_proxy_tx /dev/dma_proxy_rx /dev/plgpu_display
plgpuctl status
plgpuctl enable
rix-smoke 1000
```

`rix-smoke` 先做资源池 64 字节 STORE/LOAD，再绘制红底、绿色前景、被遮挡的蓝色几何和 2×2 纹理；读回深度遮挡中心并保存 `rix-smoke.ppm`。比较 LCD、读回 PPM 与预期图形，记录全部错误计数。测试显示区左右/上下边缘、长延迟 B 和重新启动。

已固定官方 tuxracer-data 0.61 的 151 个文件，安装到 `/usr/local/share/tuxracer`，内容 SHA256 与单赛道 `bunny_hill` 记录在 `config/game_assets.json` 和 `report/game_assets.json`。硬件共同配置中的 quality 字段仍表示物理性能验收未完成；素材版本单独锁定，避免在构建中改变硬件 ABI 摘要。启动器会逐文件核对素材并在首次运行时创建 `~/.tuxracer/options`。

```bash
export DISPLAY=:0
rasterix-run --seconds 1800 --log /tmp/rasterix-acceptance.jsonl
```

USB 键盘需检查菜单、暂停、比赛结束、再次开始；手柄功能需单独映射并实测。至少保存菜单、比赛、结束三种图像，并检查 RasterIX 未实现 GL 日志。静态 API 清单位于 `report/game_gl_calls.md`，它不等同于所有调用场景已通过。

## 验收通过条件

- DMA TX/RX 及图形保留区地址正确，无法越界或使用高于 4 GiB 的 GPU 地址。
- 实际 GPU 绘制基本场景和游戏单赛道图像正确，三片区覆盖全部 240 行。
- 无未等待 DDR B 就提交/读取资源的情况；连续 1000 次板上换页无撕裂、槽位覆盖或 ID 错序。
- 连续 30 分钟错误计数不增加，USB 输入、退出、再次启动和完整故障复位有效。
- 单赛道记录渲染/呈现 FPS、帧时间 P95/P99、重复帧比例、CPU/GPU/DDR/等待时间。30 FPS 是目标，测量不足时记录差距，不以 LCD 刷新率代替游戏帧率。
- 完整设计 DRC、CDC、时序与未约束路径经审查，bit/XSA/DTB/库/模块/素材摘要及版本进入发布 manifest。

## 实施方案阶段对应

当前已经完成源码、版本迁移、协议仿真、宿主及 AArch64 编译，并建立新板级工程和本地启动包流程。Linux 启动与用户确认的 RGB LCD 游戏启动图已有物理证据。修复布局后，板上 1000 帧 smoke、四角像素/深度/纹理断言及 60.44 秒启动图通过，启动图约 29.73 FPS、采样错误计数为零；实际 GPU 像素读回显示 Logo 和底部文字完整。两个程序和 DMA 模块已持久化到 SD，正常重启后摘要、模块加载、smoke 和运行程序来源均已验证。之后已通过 X11 注入按键完成 Frozen River 练习赛，比赛中间窗口约 30.06 呈现 FPS、采样错误为零，详见 [比赛与 DP 记录](RACE_AND_DP_2026-10-18.md)。修复后 LCD 人眼确认、实体 USB 输入/转向刹车及 30 分钟稳定性仍须单独验收。
