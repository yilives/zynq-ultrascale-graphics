// SPDX-License-Identifier: GPL-3.0-or-later
// Opt-in, inclusive pipeline timings. Never add nested or concurrent phases.
#pragma once
#include <array>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <mutex>
#include <stdexcept>
#include <time.h>

namespace rr::java_pipeline_profile {
enum Phase : unsigned {
    Worker, VertexBatch, ProducerWaitWorker, WaitUploader, TextureUpload,
    UploadTask, SwapUpload, DmaSubmit, DmaFinishStream, DmaFinishStore,
    DmaFinishOther, DmaLifetimeStream, DmaLifetimeStore, DmaLifetimeOther,
    DmaRequestDelayStream, DmaRequestDelayStore, DmaRequestDelayOther, Count
};
inline const char* name(unsigned phase) {
    static const char* names[] = {
        "worker", "vertex_batch", "producer_wait_worker", "wait_uploader",
        "texture_upload", "upload_task", "swap_upload", "dma_submit",
        "dma_finish_stream", "dma_finish_store", "dma_finish_other",
        "dma_lifetime_stream", "dma_lifetime_store", "dma_lifetime_other",
        "dma_request_delay_stream", "dma_request_delay_store", "dma_request_delay_other"
    };
    return names[phase];
}
inline uint64_t now() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
inline uint64_t threadNow() {
    timespec value{};
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &value)) std::abort();
    return uint64_t(value.tv_sec) * 1000000000ULL + value.tv_nsec;
}
struct Counter {
    std::atomic<uint64_t> calls{0}, wall{0}, cpu{0}, units{0};
};
struct Reporter {
    FILE* file = nullptr;
    std::array<Counter, Count> counters;
    std::atomic<uint64_t> next{0};
    std::mutex output;
    Reporter() {
        const char* path = std::getenv("RIX_JAVA_PIPELINE_PROFILE");
        if (path && *path) {
            file = std::fopen(path, "wx");
            if (!file) throw std::runtime_error("Cannot create pipeline profile");
        }
    }
    void emit(bool force = false) {
        if (!file) return;
        const uint64_t stamp = now();
        uint64_t expected = next.load(std::memory_order_relaxed);
        if (!force && (stamp < expected || !next.compare_exchange_strong(
                expected, stamp + 500000000ULL, std::memory_order_relaxed))) return;
        std::lock_guard<std::mutex> lock(output);
        // Timestamp after taking the output lock to keep records ordered.
        std::fprintf(file, "{\"kind\":\"pipeline_cumulative\",\"schema\":1,\"ns\":%llu,\"final\":%s,\"phases\":{",
            (unsigned long long)now(), force ? "true" : "false");
        for (unsigned i = 0; i < Count; ++i) {
            auto& c = counters[i];
            std::fprintf(file, "%s\"%s\":{\"calls\":%llu,\"wall_ns\":%llu,\"cpu_ns\":%llu,\"units\":%llu}",
                i ? "," : "", name(i),
                (unsigned long long)c.calls.load(std::memory_order_relaxed),
                (unsigned long long)c.wall.load(std::memory_order_relaxed),
                (unsigned long long)c.cpu.load(std::memory_order_relaxed),
                (unsigned long long)c.units.load(std::memory_order_relaxed));
        }
        std::fputs("}}\n", file);
        std::fflush(file);
    }
    void add(Phase phase, uint64_t wall, uint64_t cpu, uint64_t units = 0) {
        if (!file) return;
        auto& c = counters[phase];
        c.calls.fetch_add(1, std::memory_order_relaxed);
        c.wall.fetch_add(wall, std::memory_order_relaxed);
        c.cpu.fetch_add(cpu, std::memory_order_relaxed);
        c.units.fetch_add(units, std::memory_order_relaxed);
        emit();
    }
};
// Deliberately process lifetime: renderer teardown can still complete DMA.
inline Reporter& reporter() { static Reporter* value = new Reporter(); return *value; }
struct Scope {
    Phase phase;
    uint64_t wall = 0, cpu = 0, units;
    bool active;
    explicit Scope(Phase p, uint64_t amount = 0) : phase(p), units(amount), active(reporter().file) {
        if (active) { wall = now(); cpu = threadNow(); }
    }
    ~Scope() {
        if (active) {
            const auto used = threadNow() - cpu;
            const auto elapsed = now() - wall;
            reporter().add(phase, elapsed, used, units);
        }
    }
    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;
};
inline unsigned dmaKind(uint32_t op) {
    return op == 0x90000000 ? 0 : op == 0xd0000000 ? 1 : 2;
}
inline Phase finishPhase(uint32_t op) { return Phase(DmaFinishStream + dmaKind(op)); }
inline Phase lifetimePhase(uint32_t op) { return Phase(DmaLifetimeStream + dmaKind(op)); }
inline Phase requestDelayPhase(uint32_t op) { return Phase(DmaRequestDelayStream + dmaKind(op)); }
inline void finish() { reporter().emit(true); }
} // namespace rr::java_pipeline_profile
