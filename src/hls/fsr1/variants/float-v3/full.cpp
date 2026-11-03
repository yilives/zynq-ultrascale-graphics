// SPDX-License-Identifier: MIT
// Complete fixed-2x FSR1 prototype. FPGA performs every EASU and RCAS operation.
// FP32 and shared arithmetic prioritize traceable bring-up, not video-rate claims.
#include "rix_fsr1_hls.hpp"
#include "fsr_hls_types.hpp"
#include "fsr1_normalize.hpp"
#ifndef __SYNTHESIS__
#include <stdexcept>
#endif

static uint16_t input_cache[240][400];
static float easu_rows[3][800][3];
static bool cache_valid = false;
static uint32_t cached_tag = 0;

static float fsr_source(int x, int y, int channel) {
#pragma HLS INLINE
    x = x < 0 ? 0 : (x > 399 ? 399 : x);
    y = y < 0 ? 0 : (y > 239 ? 239 : y);
    uint16_t pixel = input_cache[y][x];
    uint32_t word = channel == 1 ? norm6[(pixel >> 5) & 63] :
                    norm5[channel == 0 ? (pixel >> 11) : (pixel & 31)];
    return AF1_AU1(word);
}

static AF4 FsrRcasLoadF(ASU2 p) {
#pragma HLS INLINE
    int x = p.x < 0 ? 0 : (p.x > 799 ? 799 : p.x);
    int y = p.y < 0 ? 0 : (p.y > 479 ? 479 : p.y);
    return AF4(easu_rows[y % 3][x][0], easu_rows[y % 3][x][1], easu_rows[y % 3][x][2], 1);
}

static void FsrRcasInputF(float&, float&, float&) {}
#include "fsr1_hls_generated.hpp"

static uint32_t quantize(float value) {
#pragma HLS INLINE
    // fminf/fmaxf match the reference's NaN-tolerant limiters. The testbench
    // separately rejects non-finite final output before it can be hidden here.
    value = fsr_min_bits(1.0f, fsr_max_bits(0.0f, value));
    return uint32_t(value * 255.0f + 0.5f);
}

extern "C" uint32_t rix_fsr1_hls(uint32_t mode, const uint32_t* source,
                               uint32_t* output, uint32_t source_tag,
                               uint32_t& result_tag) {
#pragma HLS INTERFACE m_axi port=source offset=slave bundle=gmem depth=96000 max_read_burst_length=64 num_read_outstanding=2
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem depth=384000 max_write_burst_length=64 num_write_outstanding=2
#pragma HLS INTERFACE s_axilite port=mode bundle=control
#pragma HLS INTERFACE s_axilite port=source bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=source_tag bundle=control
#pragma HLS INTERFACE s_axilite port=result_tag bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS BIND_STORAGE variable=input_cache type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=easu_rows type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=easu_rows complete dim=3
#pragma HLS RESET variable=cache_valid
#pragma HLS RESET variable=cached_tag
#pragma HLS RESET variable=input_cache off
#pragma HLS RESET variable=easu_rows off
    result_tag = 0;
    if (mode == 2) {
        cache_valid = false;
        cached_tag = 0;
        return 0;
    }
    if (mode == 0) {
        cache_valid = false;
        for (int y = 0; y < 240; ++y) {
            for (int x = 0; x < 400; ++x) {
#pragma HLS PIPELINE II=1
                uint32_t p = source[y * 400 + x];
                input_cache[y][x] = ((p >> 8) & 0xf800) | ((p >> 5) & 0x7e0) | ((p >> 3) & 0x1f);
            }
        }
        cached_tag = source_tag;
        cache_valid = true;
        result_tag = cached_tag;
        return 0;
    }
    if (mode != 1) return 2;
    if (!cache_valid) return 1;
    cache_valid = false; // A partial/aborted frame is never reusable as new input.
    AU4 con;
    con.x = 0x3f5edc67u; // float32(exp2(-0.2f)), checked by the host testbench.
    for (int y = 0; y <= 480; ++y) {
        if (y < 480) {
            for (int x = 0; x < 800; ++x) {
#pragma HLS PIPELINE II=64
                AF3 color;
                FsrEasuF(color, x, y);
                easu_rows[y % 3][x][0] = color.x;
                easu_rows[y % 3][x][1] = color.y;
                easu_rows[y % 3][x][2] = color.z;
            }
        }
        if (y != 0) {
            for (int x = 0; x < 800; ++x) {
#pragma HLS PIPELINE II=16
                float r, g, b;
                FsrRcasF(r, g, b, I2(x, y - 1), con);
#ifndef __SYNTHESIS__
                if (!std::isfinite(r) || !std::isfinite(g) || !std::isfinite(b))
                    throw std::runtime_error("non-finite HLS FSR output");
#endif
                output[(y - 1) * 800 + x] = (quantize(r) << 16) | (quantize(g) << 8) | quantize(b);
            }
        }
    }
    result_tag = cached_tag;
    return 0;
}
