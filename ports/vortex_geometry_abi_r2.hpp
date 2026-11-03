// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>

struct GeometryTask {
    uint64_t pool_address;
    uint32_t mode;
    uint32_t vertex_count;
    uint32_t sequence;
    uint32_t order;
};
struct GeometryBatch {
    uint64_t tasks_address;
    uint64_t results_address;
    uint32_t task_count;
    uint32_t poison_workspace;
};
struct alignas(64) GeometryResult {
    uint32_t records, error, order, owner;
    uint32_t cycle_begin, cycle_end, magic;
    uint32_t guards[9];
};
constexpr uint32_t ResultMagic = 0x56583232;
constexpr uint32_t ResultGuard = 0xa55a3cc3;
static_assert(sizeof(GeometryTask) == 24);
static_assert(sizeof(GeometryBatch) == 24);
static_assert(sizeof(GeometryResult) == 64);
