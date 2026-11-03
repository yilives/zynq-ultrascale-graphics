// SPDX-License-Identifier: MIT
#include "rix_fsr1_hls.hpp"
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

static void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
int main(int argc, char** argv) { try {
    require(argc == 3, "expected input.rgb565 output.xrgb");
    std::vector<uint16_t> raw(96000);
    std::ifstream input(argv[1], std::ios::binary);
    input.read(reinterpret_cast<char*>(raw.data()), 192000);
    require(bool(input) && input.peek() == EOF, "input length");
    std::vector<uint32_t> source(96000), output(384000, 0xdeadbeef);
    for (unsigned i = 0; i < raw.size(); ++i) {
        uint32_t p = raw[i], r = p >> 11, g = (p >> 5) & 63, b = p & 31;
        source[i] = (((r << 3) | (r >> 2)) << 16) | (((g << 2) | (g >> 4)) << 8) | (b << 3) | (b >> 2);
    }
    float sharpness = std::exp2(-.2f); uint32_t bits; std::memcpy(&bits, &sharpness, 4);
    require(bits == 0x3f5edc67u, "sharpness bits");
    uint32_t tag = 99;
    require(rix_fsr1_hls(2, nullptr, nullptr, 0, tag) == 0 && tag == 0, "invalidate");
    require(rix_fsr1_hls(1, nullptr, nullptr, 0, tag) == 1 && tag == 0, "missing input guard");
    require(rix_fsr1_hls(123, nullptr, nullptr, 0, tag) == 2 && tag == 0, "command guard");
    require(rix_fsr1_hls(0, source.data(), nullptr, 0x12345678, tag) == 0 && tag == 0x12345678, "load");
    std::fill(source.begin(), source.end(), 0x55aa55aa); // Prove cached input is immutable after LOAD completes.
    require(rix_fsr1_hls(1, nullptr, output.data(), 0x76543210, tag) == 0 && tag == 0x12345678, "compute/tag");
    require(rix_fsr1_hls(1, nullptr, nullptr, 0, tag) == 1, "no stale input reuse");
    std::ofstream result(argv[2], std::ios::binary);
    result.write(reinterpret_cast<const char*>(output.data()), output.size() * 4);
    require(bool(result), "output write");
    std::cout << "PASS FSR_HLS cached ownership, mode guards, tag, full 384000 output pixels\n";
    return 0;
} catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; } }
