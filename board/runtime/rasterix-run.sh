#!/bin/sh
set -eu
export DISPLAY=${DISPLAY:-:0}
for module in rix_dma_proxy plgpu_display; do
    if ! grep -q "^$module " /proc/modules; then
        insmod "/opt/rasterix/modules/$module.ko"
    fi
done
exec rasterix-launch "$@"
