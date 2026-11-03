/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PLGPU_DISPLAY_H
#define PLGPU_DISPLAY_H
#include <linux/ioctl.h>
#include <linux/types.h>
struct plgpu_status {
    __u32 abi,configuration,status,enabled;
    __u32 frame_id,swap_requests,copy_done,presented,last_presented_id;
    __u32 read_errors,write_errors,timeouts,scan_underflows,scan_errors;
    __u32 command_beats,gpu_busy_cycles;
};
struct plgpu_wait { __u32 frame_id,timeout_ms; };
#define PLGPU_GET_STATUS _IOR('R',0,struct plgpu_status)
#define PLGPU_ENABLE _IOW('R',1,__u32)
#define PLGPU_WAIT_PRESENT _IOW('R',2,struct plgpu_wait)
#define PLGPU_STATUS_READY 3U
#define PLGPU_STATUS_FAULT 4U
#endif
