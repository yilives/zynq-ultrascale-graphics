// SPDX-License-Identifier: GPL-3.0-or-later
// Test ownership after asynchronous failures, without claiming a hardware driver.
#include "vortex_geometry_queue_r2.hpp"
#include <cstdlib>
#include <iostream>

using namespace rixvortex;
static unsigned writes = 0, reads = 0, releases = 0, finishes = 0, failWrite = 0;
static vx_result_t waiting = VX_SUCCESS, finishing = VX_SUCCESS;
static bool highAddress = false;
static const void* recordedTasks = nullptr;
static const GeometryBatch* recordedArgs = nullptr;
static auto queue = reinterpret_cast<vx_queue_h>(1);
static auto kernel = reinterpret_cast<vx_kernel_h>(2);
static auto pool = reinterpret_cast<vx_buffer_h>(3);
static auto tasks = reinterpret_cast<vx_buffer_h>(4);
static auto results = reinterpret_cast<vx_buffer_h>(5);
static auto launched = reinterpret_cast<vx_event_h>(6);
static auto copied = reinterpret_cast<vx_event_h>(7);
static void check(bool value, const char* message) {
    if (!value) { std::cerr << message << '\n'; std::abort(); }
}
extern "C" vx_result_t vx_buffer_address(vx_buffer_h b, uint64_t* address) {
    *address = b == pool ? (highAddress ? (uint64_t(1) << 32) : 0x40000000) : b == tasks ? 0x41000000 : 0x42000000;
    return VX_SUCCESS;
}
extern "C" vx_result_t vx_enqueue_write(vx_queue_h, vx_buffer_h b, uint64_t,
        const void* host, uint64_t size, uint32_t, const vx_event_h*, vx_event_h*) {
    ++writes;
    if (b == tasks) {
        check(size == 4 * sizeof(GeometryTask), "Task extent changed");
        recordedTasks = host;
    }
    return writes == failWrite ? VX_ERR_INTERNAL : VX_SUCCESS;
}
extern "C" vx_result_t vx_enqueue_launch(vx_queue_h, const vx_launch_info_t* info,
        uint32_t, const vx_event_h*, vx_event_h* event) {
    check(info->block_dim[0] == 1 && info->grid_dim[0] == 1, "Unexpected work shape");
    recordedArgs = static_cast<const GeometryBatch*>(info->args_host);
    *event = launched;
    return VX_SUCCESS;
}
extern "C" vx_result_t vx_enqueue_read(vx_queue_h, void*, vx_buffer_h, uint64_t,
        uint64_t, uint32_t count, const vx_event_h* wait, vx_event_h* event) {
    check(count == 1 && *wait == launched, "Missing launch dependency");
    ++reads;
    if (event) *event = copied;
    return VX_SUCCESS;
}
extern "C" vx_result_t vx_event_wait_value(vx_event_h event, uint64_t value, uint64_t) {
    check(event == copied && value == 1, "Waiting on wrong completion");
    return waiting;
}
extern "C" vx_result_t vx_event_release(vx_event_h) { ++releases; return VX_SUCCESS; }
extern "C" vx_result_t vx_queue_finish(vx_queue_h, uint64_t) { ++finishes; return finishing; }

int main() {
    GeometryQueue binding(queue, kernel, pool, tasks, results);
    GeometrySubmission job, other;
    static uint32_t input = 0, output = 0; // Mock never dereferences the pool.
    job.inputs[0] = &input; job.outputs[0] = &output;
    job.tasks[0] = {0, 1, 3, 1234, 0};
    check(enqueueGeometry(binding, job) == VX_ERR_INVALID_VALUE && writes == 0, "Zero-task batch queued work");
    job.arguments.task_count = 1;
    highAddress = true;
    check(enqueueGeometry(binding, job) == VX_ERR_INVALID_VALUE && writes == 0, "RV32 address truncation accepted");
    highAddress = false;
    job.tasks[0].mode = 99;
    check(enqueueGeometry(binding, job) == VX_ERR_INVALID_VALUE && writes == 0, "Invalid mode accepted");
    job.tasks[0].mode = 1;
    check(enqueueGeometry(binding, job) == VX_SUCCESS, "Valid enqueue failed");
    check(recordedTasks == job.tasks.data() && recordedArgs == &job.arguments, "Async metadata was not caller-owned");
    check(job.tasks[0].pool_address == 0x40000000 && reads == 2, "Unexpected pool or readback");
    waiting = VX_ERR_TIMEOUT;
    check(waitGeometry(job, 0) == VX_ERR_TIMEOUT && job.state == SubmissionState::Pending, "Timeout recycled task");
    check(binding.active == &job && job.owner == &binding && releases == 1, "Timeout dropped ownership/event");
    check(enqueueGeometry(binding, job) == VX_ERR_INVALID_VALUE, "Pending task reused");
    check(enqueueGeometry(binding, other) == VX_ERR_INVALID_VALUE, "Another task stole busy buffers");
    finishing = VX_ERR_TIMEOUT;
    check(quiesceGeometry(binding, job, 0) == VX_ERR_TIMEOUT && binding.active == &job, "Drain timeout recycled buffers");
    waiting = VX_SUCCESS;
    check(waitGeometry(job, VX_TIMEOUT_INFINITE) == VX_SUCCESS && binding.active == nullptr, "Completion did not release occupancy");
    check(releases == 2 && job.owner == nullptr, "Completion reference leaked");

    failWrite = writes + 2;
    check(enqueueGeometry(binding, job) == VX_ERR_INTERNAL, "Partial enqueue failure not injected");
    check(job.state == SubmissionState::SubmissionFailed && binding.active == &job, "Partial enqueue recycled storage");
    GeometryQueue unrelated(queue, kernel, pool, tasks, results);
    auto oldFinishes = finishes;
    check(quiesceGeometry(unrelated, job, 0) == VX_ERR_INVALID_VALUE && finishes == oldFinishes, "Wrong binding drained task");
    finishing = VX_ERR_INTERNAL;
    check(quiesceGeometry(binding, job, 0) == VX_ERR_INTERNAL && binding.active == &job, "Failed drain recycled storage");
    finishing = VX_SUCCESS;
    check(quiesceGeometry(binding, job, VX_TIMEOUT_INFINITE) == VX_SUCCESS, "Failed submission not recoverable");
    check(binding.active == nullptr && job.state == SubmissionState::Idle && job.owner == nullptr, "Recovered job remains occupied");
    failWrite = 0;
    check(enqueueGeometry(binding, job) == VX_SUCCESS, "Recovered task cannot be reused");
    waiting = VX_ERR_EVENT_FAILED;
    check(waitGeometry(job, 0) == VX_ERR_EVENT_FAILED && binding.active == &job, "Failed event recycled storage");
    check(quiesceGeometry(binding, job, VX_TIMEOUT_INFINITE) == VX_SUCCESS && binding.active == nullptr, "Failed event not drained");
    std::cout << "VORTEX_QUEUE_LIFETIME_PASS timeout_resume partial_enqueue busy_buffer rv32_bounds event_failure\n";
}
