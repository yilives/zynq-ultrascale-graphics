# 两项运行阻断修复记录

本页保留首次两项 P1 修复发布的数据。当时的 23 项本地检查通过，随后实际板测仍停在 BL31。后续已修复 U-Boot 2026.1 控制树阶段标记，当前为 24 项检查；最新控制树地址、镜像摘要和板测状态见 [启动修复记录](BOOT_FIX_2026-10-16.md) 及发布清单。

对应 `REVIEW_2026-10-16.md` 的两个 P1，均已修复。2026-10-16 已完整重建硬件、启动固件、用户态及镜像，最终发布清单的 23 项本地检查全部通过。旧版 20 项检查遗漏了以下启动/初始化条件，不能作为旧镜像可运行的证明。

## U-Boot 控制设备树

固定上游 Makefile 的 `u-boot.elf` 目标将完整 `u-boot.bin` 封装为 ELF。构建脚本现在显式构建并复制该目标，保留 OF_SEPARATE 的控制 DTB。独立于供 Linux 加载的 `system.dtb`，控制 DTB 必须位于 U-Boot 的可装载内容内。

`check_uboot_control_dtb.py` 核对 ELF 的实际 PT_LOAD 字节等于完整 u-boot.bin，并检查尾部完整 DTB。打包后遍历真实 BOOT.BIN 的分区表，校验分区头校验和，并核对 U-Boot 分区确实携带同样的代码及控制 DTB。缺失时打包和发布失败。

负向证据保存于 `report/uboot_old_elf_negative.log` 和 `report/uboot_old_boot_bin_negative.log`；修复后证据为 `report/uboot_control_dtb.json`。新 ELF 的可装载内容为 1,638,124 字节，包含 29,700 字节控制 DTB，位于物理地址 `0x08188ae8`；新 BOOT.BIN 实际分区内容检查通过。是否实际完成冷启动仍需物理板验证。

## DMA 容量和 ABI

共同配置和规范 ABI 头文件统一为 ABI 2、每方向 8 个 1 MiB 数据槽。三片区双缓冲使用 TX 0–5，资源暂存使用 TX 7，TX 6 保留。两个方向各映射约 8 MiB，合计 16 MiB 数据及 16 KiB ABI 对齐开销；使用 64 MiB CMA，独立于 32 MiB 图形保留区。

主 RasterIX 和游戏嵌套副本同步同一头文件。旧 ABI 在打开通道时被拒绝。配置生成要求至少 `2 × 分片数 + 1` 个槽，禁止 4/6 槽配置；真实渲染器在分配显示列表前也检查可用槽容量。部署模块的 modinfo 记录 ABI 和槽数，根文件系统验证时核对这些值。

`test_dma_initialization.sh` 使用真实连接器、DeviceDataUploader、ThreadedVertexTransformer 和 GL 上下文，系统调用替换为内存设备。它复现旧索引异常、检查提前容量拒绝和旧 ABI 拒绝，并验证当前三片区及独立资源槽初始化。测试没有运行物理 DMA。结果和源码摘要写入 `report/dma_initialization.json`，作为发布门禁。

原生构造测试同时暴露约 12 MiB 的渲染器对象在默认栈上分配的问题。smoke 已改用堆分配，并保持渲染器存活到工作线程结束；回归测试限定 8 MiB 栈。

## 构建与验收范围

配置摘要更新为 `9adb505e4fd41ad9a2688a080f33112af60325541ed67ba832a388c5e3ce4690`。bit/XSA、OOC、FSBL/PMUFW、DTB、用户态、匹配内核模块、BOOT.BIN、ext4 和完整 SD 镜像已重建，发布清单中的配置、来源及内容一致性检查通过。

| 检查 | 本次结果与证据 |
|---|---|
| 完整硬件综合、布线、bit/XSA | 通过；WNS 1.147 ns、WHS 0.010 ns、Critical CDC 0，见 `report/blocker_fix_hardware_console.log` 和 `report/routed_review_final_console.log` |
| 控制 DTB 的实际打包 | 通过 ELF/bin/DTB/BOOT.BIN 四文件摘要及分区字节检查，见 `report/uboot_control_dtb.json` |
| 三片区初始化与旧配置拒绝 | 真实连接器、渲染器和 GL 上下文测试通过；4/6 槽配置及旧 ABI 被拒绝，见 `report/dma_initialization.json` |
| ext4 部署内容 | 回读核对 188 个文件，模块 ABI 2、每方向 8 槽，见 `report/rootfs_validation.json` |
| SD 分区与最终发布 | FAT 文件和 ext4 分区回读一致，23/23 检查通过，见 `report/blocker_fix_package_console.log`、`report/sd_image.json`、`report/release_manifest.json` |

重打包还修复了已有 Unix 回读目标使 `mcopy -o` 等待交互输入的问题，改为 `mcopy -n`，并加入无控制终端和 120 秒超时。最初停顿及停止记录保留于 `report/blocker_fix_finish_console.log`；成功重跑记录为 `report/blocker_fix_package_console.log`。

交付文件为 [完整 SD 镜像](../build/sdcard/AXU3EG_RasterIX_Linux_TuxRacer.img)，大小 1,610,612,736 字节，SHA256：

```text
a9050b858b1847a6ee365e34ca73db405886162546f5b5a1eecd4b24fcd3879a
```

配套 BOOT.BIN 的 SHA256 为 `0a6791817749a6e411f4400683f0044efe1851480ab9912e4995a87de46ff849`，ext4 为 `7305144570c86a725934b382511681a9bbf2b212b14703657b039068c4dd3734`。

本次修复不代表完成了新镜像冷启动、LCD、USB 输入、游戏图像、30 分钟或 FPS 的物理验收。审核记录中的 P2 硬件输入构建快照问题以及其余验收事项仍单独保留。
