// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>

// mode 0: copy SNP1 XRGB8888 to internal RGB565, then complete (release lease).
// mode 1: consume cached frame, EASU + RCAS -> XRGB8888 DDR, then complete.
// mode 2: invalidate cache, without issuing any DDR operation.
// Return 0 on success, 1 for missing input, 2 for an invalid command.
extern "C" uint32_t rix_fsr1_hls(uint32_t mode, const uint32_t* source,
                               uint32_t* output, uint32_t source_tag,
                               uint32_t& result_tag);
