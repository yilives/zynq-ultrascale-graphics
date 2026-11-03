// SPDX-License-Identifier: MIT
// Exact fixed-v8 arithmetic, with independent EASU, RCAS, and AXI store tasks.
#include "rix_fsr1_hls.hpp"
#include "fsr1_fixed.hpp"
#if defined(__SYNTHESIS__) || defined(RIX_FSR_COSIM)
#include <hls_stream.h>
#else
#include <queue>
namespace hls {
template<class T> struct stream {
    std::queue<T> values;
    void write(const T& value) { values.push(value); }
    T read() { T value=values.front(); values.pop(); return value; }
};
}
#endif
static uint16_t input_cache[6][8];
static FColor easu_rows[3][16];
static bool cache_valid=false;
static uint32_t cached_tag=0;
// Luma is only used by EASU. Do not spend FIFO BRAM transporting its unused field.
struct FPixel {FQ r,g,b; bool fault;};
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
static void easu_task(hls::stream<FPixel>& pixels) {
#pragma HLS INLINE off
    for(int y=0;y<12;++y)for(int x=0;x<16;++x) {
#pragma HLS PIPELINE II=8
        FColor c=fixed_easu(x,y);
        pixels.write({c.r,c.g,c.b,c.fault});
    }
}
static void rcas_task(hls::stream<FPixel>& pixels,
                      hls::stream<uint32_t>& words,hls::stream<bool>& faults) {
#pragma HLS INLINE off
#pragma HLS BIND_STORAGE variable=easu_rows type=ram_2p impl=bram
    bool frame_fault=false;
    for(int y=0;y<=12;++y) {
        if(y<12)for(int x=0;x<16;++x) {
#pragma HLS PIPELINE II=1
            FPixel c=pixels.read();
            easu_rows[y%3][x]={c.r,c.g,c.b,c.fault,0};
        }
        if(y>0)for(int x=0;x<16;++x) {
#pragma HLS PIPELINE II=6
            FColor c=fixed_rcas(x,y-1);
            frame_fault=frame_fault||c.fault;
            words.write((quantize_fixed(c.r)<<16)|(quantize_fixed(c.g)<<8)|quantize_fixed(c.b));
        }
    }
    faults.write(frame_fault);
}
static void store_burst(uint32_t* output,uint32_t burst[64]) {
#pragma HLS INLINE off
    // This function boundary prevents a frame-wide AW request from being lifted
    // out of the block loop. Its buffer is complete before this function starts.
    for(int i=0;i<64;++i) {
#pragma HLS PIPELINE II=1
        output[i]=burst[i];
    }
}
static void store_task(hls::stream<uint32_t>& words,uint32_t* output) {
#pragma HLS INLINE off
    uint32_t burst[64];
#pragma HLS BIND_STORAGE variable=burst type=ram_1p impl=lutram
    // Fill a whole AXI burst before AW. The shared DDR fabric never has to wait
    // on RCAS arithmetic while an accepted FSR write owns its W channel.
    for(int block=0;block<192/64;++block) {
        for(int i=0;i<64;++i) {
#pragma HLS PIPELINE II=1
            burst[i]=words.read();
        }
        store_burst(output+block*64,burst);
    }
}
static void fault_task(hls::stream<bool>& faults,bool& frame_fault) {
#pragma HLS INLINE off
    frame_fault=faults.read();
}
static void render_frame(uint32_t* output,bool& frame_fault) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<FPixel> pixels;
    hls::stream<uint32_t> words;
    hls::stream<bool> faults;
#pragma HLS STREAM variable=pixels depth=16
#pragma HLS STREAM variable=words depth=16
#pragma HLS STREAM variable=faults depth=2
#pragma HLS BIND_STORAGE variable=pixels type=fifo impl=bram
#pragma HLS BIND_STORAGE variable=words type=fifo impl=bram
#pragma HLS AGGREGATE variable=pixels compact=bit
    easu_task(pixels);
    rcas_task(pixels,words,faults);
    store_task(words,output);
    fault_task(faults,frame_fault);
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
    // The DATAFLOW join includes store_task completion, after all AXI B responses.
    bool frame_fault=false;
    render_frame(output,frame_fault);
    result_tag=cached_tag;
    return frame_fault?3:0;
}
