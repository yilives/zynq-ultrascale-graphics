// SPDX-License-Identifier: MIT
#pragma once
#include "pl_frames.hpp"
#include "../include/rix-frame-mem.h"
#include <sys/ioctl.h>
namespace rix_pl {
inline int frame_memory_fd(){
 int fd=open("/dev/rix-frame-mem",O_RDONLY|O_SYNC);if(fd<0)throw std::runtime_error("RFM1 frame-memory driver is not loaded");
 rix_frame_mem_info info{};
 if(ioctl(fd,RIX_FRAME_MEM_INFO,&info)||info.abi!=RIX_FRAME_MEM_ABI||info.physical_base!=RIX_FRAME_MEM_BASE||
    info.bytes!=RIX_FRAME_MEM_BYTES||info.memory_type!=RIX_FRAME_MEM_NORMAL_NC){close(fd);throw std::runtime_error("RFM1 mapping ABI mismatch");}
 return fd;
}
}
