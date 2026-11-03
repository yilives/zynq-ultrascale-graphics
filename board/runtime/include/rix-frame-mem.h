/* SPDX-License-Identifier: GPL-2.0-or-later WITH Linux-syscall-note */
#ifndef RIX_FRAME_MEM_H
#define RIX_FRAME_MEM_H
#include <linux/ioctl.h>
#include <linux/types.h>
#define RIX_FRAME_MEM_ABI 0x52464d31U
#define RIX_FRAME_MEM_BASE 0xa1000000U
#define RIX_FRAME_MEM_BYTES 0x00600000U
#define RIX_FRAME_MEM_NORMAL_NC 1U
struct rix_frame_mem_info { __u32 abi,physical_base,bytes,memory_type; };
#define RIX_FRAME_MEM_INFO _IOR('N',0,struct rix_frame_mem_info)
#endif
