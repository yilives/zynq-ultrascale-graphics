/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef RIX_DMA_PROXY_H
#define RIX_DMA_PROXY_H
#include <linux/types.h>
#include <linux/ioctl.h>
#define RIX_DMA_ABI_VERSION 2
#define BUFFER_SIZE (1024U * 1024U)
/* Three IF strips use six command slots; the final slot is resource staging. */
#define BUFFER_COUNT 8U
#define TX_BUFFER_COUNT BUFFER_COUNT
#define RX_BUFFER_COUNT BUFFER_COUNT
#define PROXY_NO_ERROR 0U
#define PROXY_BUSY 1U
#define PROXY_TIMEOUT 2U
#define PROXY_ERROR 3U
#define FINISH_XFER _IOW('a', 'a', __u32)
#define START_XFER _IOW('a', 'b', __u32)
#define XFER _IOW('a', 'c', __u32)
#define RIX_DMA_GET_ABI _IOR('a', 'v', __u32)
struct channel_buffer {
    __u32 buffer[BUFFER_SIZE / 4U];
    __u32 status;
    __u32 length;
} __attribute__((aligned(1024)));
#endif
