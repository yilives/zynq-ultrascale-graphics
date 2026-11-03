/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef RIX_GEOMETRY_UAPI_H
#define RIX_GEOMETRY_UAPI_H
#include <linux/types.h>
#include <linux/ioctl.h>
#define RIX_GEOMETRY_MAGIC 0x47454f31u
#define RIX_GEOMETRY_ABI 0x00010001u
#define RIX_GEOMETRY_POOL_BYTES 4194304u
struct rix_geometry_info {
 __u32 magic,abi,pool_bytes,max_vertices;
 __u32 state_words,vertex_offset_words,carry_offset_words,output_offset_words;
 __u32 record_words,max_records,profile_magic,reserved;
};
struct rix_geometry_job {
 __u32 mode,count,sequence,reserved;
 __u32 records,status,reserved_out[2];
};
#define RIX_GEOMETRY_INFO _IOR('G',0,struct rix_geometry_info)
#define RIX_GEOMETRY_SUBMIT _IOWR('G',1,struct rix_geometry_job)
#endif
