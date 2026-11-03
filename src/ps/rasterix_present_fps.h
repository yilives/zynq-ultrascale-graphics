/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef RASTERIX_PRESENT_FPS_H
#define RASTERIX_PRESENT_FPS_H
#include "plgpu-display.h"
#include <fcntl.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <time.h>
static double rix_hardware_presented_fps(void)
{
    static int fd=-1,initialized=0;
    static double previous=0,value=0;
    static uint32_t frames=0;
    struct timespec now;
    struct plgpu_status state;
    double seconds;
    clock_gettime(CLOCK_MONOTONIC,&now);
    seconds=now.tv_sec+now.tv_nsec*1e-9;
    if(initialized&&seconds-previous<0.25)return value;
    if(fd<0)fd=open("/dev/plgpu_display",O_RDWR|O_CLOEXEC);
    if(fd<0||ioctl(fd,PLGPU_GET_STATUS,&state)||state.abi!=0x52495801||state.status!=3)return 0;
    if(initialized&&seconds>previous)value=(uint32_t)(state.presented-frames)/(seconds-previous);
    previous=seconds;frames=state.presented;initialized=1;
    return value;
}
#endif
