// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstdint>

namespace rr::boardopt {
using Clock = std::chrono::steady_clock;
inline bool vertexCacheEnabled() {
    static const bool enabled = !std::getenv("RIX_VERTEX_CACHE") || std::getenv("RIX_VERTEX_CACHE")[0] != '0';
    return enabled;
}
struct FrameMetrics {
    uint64_t frames=0, draws=0, vertices=0, fetched=0;
    double drawSeconds=0, swapSeconds=0;
    Clock::time_point start=Clock::now();
    bool enabled = std::getenv("RIX_FRAME_METRICS") != nullptr;
    void frame(double swap) {
        swapSeconds += swap;
        ++frames;
        if (enabled && frames % 60 == 0) {
            double elapsed=std::chrono::duration<double>(Clock::now()-start).count();
            std::fprintf(stdout,"RIX_FRAME_METRICS frames=%llu seconds=%.6f cpu_submit_fps=%.3f draws_per_frame=%.3f vertices_per_frame=%.3f fetch_hit_ratio=%.6f cpu_draw_ms=%.3f swap_wait_ms=%.3f\n",
                static_cast<unsigned long long>(frames),elapsed,60/elapsed,draws/60.0,vertices/60.0,
                vertices ? 1.0-static_cast<double>(fetched)/vertices : 0,drawSeconds*1000/60,swapSeconds*1000/60);
            std::fflush(stdout);
            draws=vertices=fetched=0;
            drawSeconds=swapSeconds=0;
            start=Clock::now();
        }
    }
};
inline FrameMetrics& metrics() { static FrameMetrics value; return value; }
}
