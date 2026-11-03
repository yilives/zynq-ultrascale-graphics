// SPDX-License-Identifier: MIT
#include "rix_fsr1_hls.hpp"
#include "fsr1_fixed.hpp"
static uint16_t input_cache[6][8];
static FColor easu_rows[3][16];
static bool cache_valid=false;
static uint32_t cached_tag=0;
static FColor decode_fixed(uint16_t p) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
    return {FQ(FSR_COLOR_R[p>>11]),FQ(FSR_COLOR_G[(p>>5)&63]),FQ(FSR_COLOR_R[p&31]),false,luma_of_raw(p)};
}
static FColor load_fixed(int x,int y) {
#pragma HLS INLINE
    x=x<0?0:(x>7?7:x);y=y<0?0:(y>5?5:y);
    return decode_fixed(input_cache[y][x]);
}
static FColor load_easu_fixed(int x,int y) {
#pragma HLS INLINE
    x=x<0?0:(x>15?15:x);y=y<0?0:(y>11?11:y);
    return easu_rows[y%3][x];
}
static uint32_t quantize_fixed(FQ value) {
#pragma HLS INLINE
    value=fminq(FQ(FS),fmaxq(FQ(0),value));
    return uint32_t((FW(value)*255+FS/2)>>18);
}
extern "C" uint32_t rix_fsr1_hls(uint32_t mode,const uint32_t* source,uint32_t* output,uint32_t source_tag,uint32_t& result_tag) {
#pragma HLS INTERFACE m_axi port=source offset=slave bundle=gmem depth=96000 max_read_burst_length=64 num_read_outstanding=2
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem depth=384000 max_write_burst_length=64 num_write_outstanding=2
#pragma HLS INTERFACE s_axilite port=mode bundle=control
#pragma HLS INTERFACE s_axilite port=source bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=source_tag bundle=control
#pragma HLS INTERFACE s_axilite port=result_tag bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS BIND_STORAGE variable=input_cache type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=easu_rows type=ram_2p impl=bram
#pragma HLS RESET variable=cache_valid
#pragma HLS RESET variable=cached_tag
#pragma HLS RESET variable=input_cache off
#pragma HLS RESET variable=easu_rows off
    result_tag=0;
    if(mode==2) {cache_valid=false;cached_tag=0;return 0;}
    if(mode==0) {
        cache_valid=false;
        for(int y=0;y<6;++y)for(int x=0;x<8;++x) {
#pragma HLS PIPELINE II=1
            uint32_t p=source[y*8+x];
            input_cache[y][x]=((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&0x1f);
        }
        cached_tag=source_tag;cache_valid=true;result_tag=cached_tag;return 0;
    }
    if(mode!=1)return 2;
    if(!cache_valid)return 1;
    cache_valid=false;
    bool frame_fault=false;
    for(int y=0;y<=12;++y) {
        if(y<12)for(int x=0;x<16;++x) {
#pragma HLS PIPELINE II=16
            easu_rows[y%3][x]=fixed_easu(x,y);
        }
        if(y>0)for(int x=0;x<16;++x) {
#pragma HLS PIPELINE II=8
            FColor c=fixed_rcas(x,y-1);
            frame_fault=frame_fault||c.fault;
            output[(y-1)*16+x]=(quantize_fixed(c.r)<<16)|(quantize_fixed(c.g)<<8)|quantize_fixed(c.b);
        }
    }
    result_tag=cached_tag;
    return frame_fault?3:0;
}
