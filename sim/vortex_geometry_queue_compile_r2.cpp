// SPDX-License-Identifier: GPL-3.0-or-later
// Compile probe retains all public queue paths in the AArch64 object.
#include "vortex_geometry_queue_r2.hpp"
extern "C" vx_result_t rix_vortex_queue_enqueue(rixvortex::GeometryQueue* binding, rixvortex::GeometrySubmission* job) {
    return rixvortex::enqueueGeometry(*binding, *job);
}
extern "C" vx_result_t rix_vortex_queue_wait(rixvortex::GeometrySubmission* job, uint64_t timeoutNs) {
    return rixvortex::waitGeometry(*job, timeoutNs);
}
extern "C" vx_result_t rix_vortex_queue_quiesce(rixvortex::GeometryQueue* binding, rixvortex::GeometrySubmission* job, uint64_t timeoutNs) {
    return rixvortex::quiesceGeometry(*binding, *job, timeoutNs);
}
