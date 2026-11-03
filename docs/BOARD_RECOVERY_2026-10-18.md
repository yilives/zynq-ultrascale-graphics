# PS 软复位与串口恢复

用户最终确认 PS 串口为 COM11，新接入的 PL 串口为 COM15。本次配置为 115200、8N1、无流控。Windows 能枚举两个 CP210x，但最初都收不到输出；用户提出尝试软复位。

## 已执行的恢复

XSDB 检出唯一的 Digilent JTAG-HS1 `210512180081` 及 `xczu3`。10 MHz 扫描链报不稳定，降至 1 MHz 后恢复 PSU、APU 及四个 A53 目标。对该 PSU 执行 `rst -system` 后，主核进入 `Reset Catch`、PC=`0xffff0000`；继续执行主核后四个 A53 恢复运行。该流程通过本机临时 hw_server 完成，服务空闲后自动退出。

串口仍无输出时，根据匹配 Image 的 vmlinux 符号，经 JTAG 只读导出并解析内核 printk 缓冲，得到 361 条完整记录。日志确认 Linux 5.4.0 已启用 ttyPS0、识别 SD 卡、完成 ext4 journal 恢复、挂载根分区并启动 `/sbin/init`，没有观察到 panic。使用的固定物理地址只适用于当前关闭 KASLR、Image SHA256 为 `77ee4fd605510596456a542f641cdaecb5dda4a617f1e6500ceebb651885962a` 的内核。

UART0 控制、参考时钟、MIO42/43 和发送排空状态均可通过 JTAG 正常读取。打开串口后经 JTAG 直接发出测试标记，Windows 仍收不到字符。随后只重启已核对身份的 COM11 CP210x USB 设备，设备操作成功，COM11 立即收到 PetaLinux 登录提示；登录后可正常执行 Linux 命令。相关脚本现在显式接受 `-Port`，默认 COM11。

## SD 检查与部署边界

启动日志带有 FAT 分区未正常卸载标记；这不等于已确认文件损坏。实际 BOOT.BIN、Image、system.dtb 和 boot.scr 均已在板上完整读回 SHA256，与此前已验证的卡片版本一致。启动分区随后重新挂载为只读。目标未安装 fsck.vfat，FAT 的完整离线检查仍应在下次维护卡片时执行。

本次比例修复已更新 Linux 根分区内的两个程序与 DMA 模块，完成正常 Linux 重启后的三文件摘要、模块加载、smoke 和游戏可执行文件来源验证。部署测试及回退位置记录在 [LCD 比例修复](LCD_LAYOUT_2026-10-18.md)。本地完整镜像的摘要与实际卡片逐文件验收分别记录。

证据：`report/board_recovery_2026-10-18.json`、`report/board_serial/com15_jtag_system_reset.log`、`com15_jtag_resume_boot.log`、`jtag_linux_after_softreset.log`、`com11_usb_restart.log`、`com11_layout_after_login_inventory.log`、`com11_boot_files_before_runtime_update.log`。前两个日志文件名保留了当时按用户第一次说明监听 COM15 的历史名称，实际 CPU 操作由已核对的 JTAG 身份定位。
