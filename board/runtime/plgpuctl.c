// SPDX-License-Identifier: GPL-3.0-or-later
#include "include/plgpu-display.h"
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
int main(int argc,char **argv) {
    int fd=open("/dev/plgpu_display",O_RDWR|O_CLOEXEC);struct plgpu_status s;__u32 enabled=1;
    if(fd<0) {perror("open display");return 1;}
    if(argc==2&&strcmp(argv[1],"enable")==0&&ioctl(fd,PLGPU_ENABLE,&enabled)<0) {perror("enable display");close(fd);return 1;}
    if(ioctl(fd,PLGPU_GET_STATUS,&s)<0) {perror("display status");close(fd);return 1;}
    printf("{\"abi\":%u,\"config\":%u,\"status\":%u,\"enabled\":%u,\"swap\":%u,\"copy\":%u,\"presented\":%u,\"frame_id\":%u,\"last_presented\":%u,\"read_errors\":%u,\"write_errors\":%u,\"timeouts\":%u,\"underflows\":%u,\"scan_errors\":%u,\"command_beats\":%u,\"gpu_busy_cycles\":%u}\n",
        s.abi,s.configuration,s.status,s.enabled,s.swap_requests,s.copy_done,s.presented,s.frame_id,s.last_presented_id,s.read_errors,s.write_errors,s.timeouts,s.scan_underflows,s.scan_errors,s.command_beats,s.gpu_busy_cycles);
    close(fd);return (s.status&PLGPU_STATUS_FAULT)?2:0;
}
