#!/bin/sh
# Additive boot hook; only operates with the experimental GPIO device tree.
set -eu
test -d /proc/device-tree/touch-gpio@a0020000 || exit 0
base=/opt/rasterix/postproc-touch
for pair in 'i2c_gpio i2c-gpio.ko' 'uinput uinput.ko'; do
    set -- $pair
    if ! grep -q "^$1 " /proc/modules; then insmod "$base/modules/$2"; fi
done
python3 "$base/bin/rix-goodix-configure"
if ! grep -q '^rix_goodix ' /proc/modules; then insmod "$base/modules/rix_goodix.ko"; fi
grep -q 'Goodix Capacitive TouchScreen' /proc/bus/input/devices
echo 'RASTERIX_PHYSICAL_GOODIX_INPUT_REGISTERED'
