# SD0 is eMMC; SD1 is the removable SD card, matching the DT aliases.
if part uuid mmc 1:2 rootpart; then
    setenv bootargs "console=ttyPS0,115200 earlycon clk_ignore_unused root=PARTUUID=${rootpart} rw rootwait"
    if fatload mmc 1:1 0x10000000 Image; then
        if fatload mmc 1:1 0x00100000 system.dtb; then
            booti 0x10000000 - 0x00100000
        fi
    fi
fi
echo "RasterIX SD boot failed: check SD1 partitions, Image and system.dtb"
