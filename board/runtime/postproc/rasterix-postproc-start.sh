#!/bin/sh
# Start with the FPGA scaler; CPU FSR remains an explicit runtime experiment.
set -eu
test -d /proc/device-tree/touch-gpio@a0020000 || exit 0
/opt/rasterix/postproc-touch/bin/rix-superres --pl-mode bilinear --style 0
echo 'RASTERIX_FPGA_BILINEAR_DEFAULT_ACTIVE'
