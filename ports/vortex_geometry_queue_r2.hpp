// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <vortex2.h>
#include "vortex_geometry_abi_r2.hpp"
#include <array>
#include <cstring>

namespace rixvortex {
constexpr uint64_t GeometryPoolBytes = 4 * 1024 * 1024;
struct GeometrySubmission;
struct GeometryQueue {
    GeometryQueue(vx_queue_h q, vx_kernel_h k, vx_buffer_h p, vx_buffer_h t, vx_buffer_h r)
        : queue(q), kernel(k), pools(p), tasks(t), results(r) {}
    GeometryQueue(const GeometryQueue&) = delete;
    GeometryQueue& operator=(const GeometryQueue&) = delete;
    vx_queue_h queue = nullptr;
    vx_kernel_h kernel = nullptr;
    vx_buffer_h pools = nullptr, tasks = nullptr, results = nullptr;
    uint64_t poolsAddress = 0, tasksAddress = 0, resultsAddress = 0;
    GeometrySubmission* active = nullptr;

    vx_result_t resolveAddresses() {
        if (!queue || !kernel || !pools || !tasks || !results) return VX_ERR_INVALID_HANDLE;
        auto status = vx_buffer_address(pools, &poolsAddress);
        if (status != VX_SUCCESS) return status;
        status = vx_buffer_address(tasks, &tasksAddress);
        if (status != VX_SUCCESS) return status;
        return vx_buffer_address(results, &resultsAddress);
    }
};

enum class SubmissionState { Idle, Pending, SubmissionFailed };
struct GeometrySubmission {
    GeometrySubmission() = default;
    GeometrySubmission(const GeometrySubmission&) = delete;
    GeometrySubmission& operator=(const GeometrySubmission&) = delete;
    // Buffers and host pointers remain owned by the caller until wait/quiesce succeeds.
    std::array<const uint32_t*, 4> inputs{};
    std::array<uint32_t*, 4> outputs{};
    std::array<GeometryTask, 4> tasks{};
    std::array<GeometryResult, 4> results{};
    GeometryBatch arguments{};
    vx_event_h completion = nullptr;
    SubmissionState state = SubmissionState::Idle;
    GeometryQueue* owner = nullptr;
};

inline vx_result_t enqueueGeometry(GeometryQueue& binding, GeometrySubmission& submission) {
    if (binding.active || submission.owner || submission.state != SubmissionState::Idle || submission.completion)
        return VX_ERR_INVALID_VALUE;
    const auto count = submission.arguments.task_count;
    if (count == 0 || count > 4 || submission.arguments.poison_workspace > 1) return VX_ERR_INVALID_VALUE;
    for (unsigned i = 0; i < count; ++i) {
        const auto& task = submission.tasks[i];
        if (!submission.inputs[i] || !submission.outputs[i] || (task.mode != 1 && task.mode != 2) ||
            task.vertex_count == 0 || task.vertex_count > 2048 || task.sequence == 0)
            return VX_ERR_INVALID_VALUE;
    }
    auto status = binding.resolveAddresses();
    if (status != VX_SUCCESS) return status;
    if ((binding.poolsAddress | binding.tasksAddress | binding.resultsAddress) & 63u)
        return VX_ERR_INVALID_VALUE;
    constexpr uint64_t AddressLimit = uint64_t(1) << 32; // This kernel is RV32.
    if (binding.poolsAddress > AddressLimit - 4 * GeometryPoolBytes ||
        binding.tasksAddress > AddressLimit - sizeof(submission.tasks) ||
        binding.resultsAddress > AddressLimit - sizeof(submission.results)) return VX_ERR_INVALID_VALUE;
    submission.arguments.tasks_address = binding.tasksAddress;
    submission.arguments.results_address = binding.resultsAddress;
    std::array<uint32_t, 16> guard;
    guard.fill(ResultGuard);
    for (auto& result : submission.results) std::memcpy(&result, guard.data(), sizeof(result));
    // Use a dedicated in-order queue and one submission at a time per binding.
    // A partial enqueue or timeout must never make the caller recycle in-flight storage.
    submission.state = SubmissionState::SubmissionFailed;
    submission.owner = &binding;
    binding.active = &submission;
    for (unsigned i = 0; i < count; ++i) {
        submission.tasks[i].pool_address = binding.poolsAddress + i * GeometryPoolBytes;
        status = vx_enqueue_write(binding.queue, binding.pools, i * GeometryPoolBytes,
                                  submission.inputs[i], GeometryPoolBytes, 0, nullptr, nullptr);
        if (status != VX_SUCCESS) return status;
    }
    status = vx_enqueue_write(binding.queue, binding.tasks, 0, submission.tasks.data(),
                              sizeof(submission.tasks), 0, nullptr, nullptr);
    if (status != VX_SUCCESS) return status;
    status = vx_enqueue_write(binding.queue, binding.results, 0, submission.results.data(),
                              sizeof(submission.results), 0, nullptr, nullptr);
    if (status != VX_SUCCESS) return status;
    vx_launch_info_t launch{};
    launch.struct_size = sizeof(launch); launch.kernel = binding.kernel;
    launch.args_host = &submission.arguments; launch.args_size = sizeof(submission.arguments);
    launch.ndim = 1; launch.grid_dim[0] = count; launch.block_dim[0] = 1;
    vx_event_h launched = nullptr;
    status = vx_enqueue_launch(binding.queue, &launch, 0, nullptr, &launched);
    if (status != VX_SUCCESS) return status;
    for (unsigned i = 0; i < count; ++i) {
        status = vx_enqueue_read(binding.queue, submission.outputs[i], binding.pools, i * GeometryPoolBytes,
                                 GeometryPoolBytes, 1, &launched, nullptr);
        if (status != VX_SUCCESS) { vx_event_release(launched); return status; }
    }
    status = vx_enqueue_read(binding.queue, submission.results.data(), binding.results, 0,
                             sizeof(submission.results), 1, &launched, &submission.completion);
    vx_event_release(launched);
    if (status != VX_SUCCESS) return status;
    submission.state = SubmissionState::Pending;
    return VX_SUCCESS;
}

inline vx_result_t waitGeometry(GeometrySubmission& submission, uint64_t timeoutNs) {
    if (submission.state != SubmissionState::Pending || !submission.completion || !submission.owner)
        return VX_ERR_INVALID_VALUE;
    auto status = vx_event_wait_value(submission.completion, 1, timeoutNs);
    if (status != VX_SUCCESS) return status;
    status = vx_event_release(submission.completion);
    if (status != VX_SUCCESS) return status;
    submission.completion = nullptr;
    submission.state = SubmissionState::Idle;
    submission.owner->active = nullptr;
    submission.owner = nullptr;
    return VX_SUCCESS;
}

inline vx_result_t quiesceGeometry(GeometryQueue& binding, GeometrySubmission& submission, uint64_t timeoutNs) {
    if ((binding.active && binding.active != &submission) || (submission.owner && submission.owner != &binding))
        return VX_ERR_INVALID_VALUE;
    auto status = vx_queue_finish(binding.queue, timeoutNs);
    if (status != VX_SUCCESS) return status;
    if (submission.completion) {
        status = vx_event_release(submission.completion);
        if (status != VX_SUCCESS) return status;
    }
    submission.completion = nullptr;
    submission.state = SubmissionState::Idle;
    submission.owner = nullptr;
    binding.active = nullptr;
    return VX_SUCCESS;
}
}
