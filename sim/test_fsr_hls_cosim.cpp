// SPDX-License-Identifier: MIT
// Small dimensions, original AXI depth. Vitis compares these C transactions to RTL.
#include "rix_fsr1_hls.hpp"
#include <iostream>
#include <stdexcept>
#include <vector>
static void require(bool v) { if (!v) throw std::runtime_error("FSR C/RTL contract"); }
int main() {
    std::vector<uint32_t> source(96000), output(384000, 0xdeadbeef);
    uint32_t tag = 0;
    require(rix_fsr1_hls(2, source.data(), output.data(), 0, tag) == 0 && tag == 0);
    require(rix_fsr1_hls(1, source.data(), output.data(), 0, tag) == 1 && tag == 0);
    require(rix_fsr1_hls(99, source.data(), output.data(), 0, tag) == 2 && tag == 0);
    for (uint32_t frame = 1; frame <= 2; ++frame) {
        for (unsigned i = 0; i < 48; ++i)
            source[i] = frame == 1 ? ((i * 35059) & 0xffffff) : ((i % 3) ? 0 : 0xffffff);
        std::fill(output.begin(), output.end(), 0xdeadbeef);
        require(rix_fsr1_hls(0, source.data(), output.data(), frame, tag) == 0 && tag == frame);
        std::fill(source.begin(), source.end(), 0);
        require(rix_fsr1_hls(1, source.data(), output.data(), 99, tag) == 0 && tag == frame);
        for (unsigned i = 0; i < 192; ++i) require(output[i] != 0xdeadbeef && !(output[i] >> 24));
        for (unsigned i = 192; i < output.size(); ++i) require(output[i] == 0xdeadbeef);
        require(rix_fsr1_hls(1, source.data(), output.data(), 0, tag) == 1 && tag == 0);
    }
    std::cout << "PASS FSR_COSIM two frames, cached input, command/tag guards, output bounds\n";
}
