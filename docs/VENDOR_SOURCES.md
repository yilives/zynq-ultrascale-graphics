# 板级资料来源

用户指定查找 `G:\baidudownload\AXU3EG`。本项目只读取该目录及相邻的配套工具目录，原压缩包未修改。

| 来源 | 提取或使用内容 |
|---|---|
| `AXU3EG/factory_file/axu3eg出厂bsp.zip` | `axu3eg.bsp`、PetaLinux project-spec、PS 外设 DT、内存地址图、旧 XSA |
| `AXU3EG/factory_file/axu3eg_factory_vivado.zip` | 出厂 BD 中的 PS DDR、UART、USB、SD、ENET、QSPI 参数 |
| `AXU3EG/AXU3EG开发板用户手册.pdf` | XCZU3EG-1SFVC784I、PS 4 GiB / PL 1 GiB DDR、板级接口依据 |
| `AXU3EG/AXU3EGB开发板用户手册.pdf` | 区分另一底板型号；当前没有混用其 BSP |
| `AXU3EG/course_s3.tar.gz` | Linux 基础教程 PetaLinux 项目配置与硬件参考 |
| `AXU3EG/course_s4.tar.gz` | Linux 驱动教程参考；文件扩展名为 gz，压缩格式由工具实际识别 |
| `zynq_soft_2020/petalinux/sdk/sdk.sh` | PetaLinux 2020.1 SDK，局部安装到新工程 build 中用于兼容测试 |
| `zynq_soft_2020/petalinux/u-boot及内核源码/linux-xlnx-xilinx-v2020.1.zip` | 与旧 BSP 对应的内核源码，目标模块构建须核对实际版本 |
| `zynq_soft_2020/petalinux/sdk/rootfs.tar.gz` | Linux 2020.1 用户态底座；替换匹配的新内核模块、加入游戏及 Xorg 输入后端 |

`report/vendor_inventory.json` 保存压缩包目录，`report/board_source_verification.json` 保存实际配置依据和文件摘要。派生 PS 预设位于 `config/axu3eg_ps_preset.tcl`。

厂商 AXU3EG BD 和固定的官方仓库预设在 QSPI feedback clock 与 preset 名称上存在差异；当前显式采用出厂 BD 的 QSPI feedback=0、DDR 64-bit / 8192 Mbit 器件 / 16 行地址位和 DDR 时序值，并保留新工程所需的 HP0/HPM0/DMA/IRQ 配置。

出厂 DT 报告低 DDR 为 `0x00000000..0x7FEFFFFF`，另有高地址 DDR bank。32 位 GPU 仅使用低 bank。本项目在低 bank 内新预留 `0x60000000..0x61FFFFFF`，以生成的 `reserved-memory no-map` 落实。该范围避开出厂 U-Boot/内核的低地址装载区，仍必须随新 BSP 的 DTB 生效；启动后以 `/proc/iomem` 再次核对。

`board_config.verified=true` 仅表示配置已经与来源资料核对，并允许生成硬件；物理 DDR 训练、Linux 启动、输入及游戏验收另行记录。资料盘 2020.1 BSP/SDK 与 Vivado 2026.1 的版本差异不会被隐藏。

启动固件不是出厂 BOOT.BIN：FSBL/PMUFW 从新 XSA 构建，TF-A/U-Boot 固定 2026.1 提交，来源及归档 SHA256 在 `config/boot_sources.json`。新 Linux DTB 显式投影当前 PL 地址、中断、保留区，并保留 5.4 内核对应的 PS 绑定；不能直接把原 SDT 当作 Linux 设备树使用。最终跨版本启动兼容性需要实际启动日志确认。
