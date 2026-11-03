// SPDX-License-Identifier: MIT
#pragma once
#include "frame_resample.hpp"
namespace rix_frames {
inline uint16_t stage565(uint32_t p){return uint16_t(((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&0x1f));}
class StageBilinear2 {
 Axis<400,800> horizontal;Axis<240,480> vertical;
 std::vector<std::array<int16_t,3>> rows=std::vector<std::array<int16_t,3>>(240*800);
public:
 void upscale(const std::vector<uint32_t>&input,std::vector<uint32_t>&output){
  if(input.size()!=96000||output.size()!=384000)throw std::runtime_error("invalid stage bilinear buffers");
  for(unsigned y=0;y<240;y++)for(unsigned x=0;x<800;x++){
   auto tap=horizontal.taps[x];auto a=stage565(input[y*400+tap.lo]),b=stage565(input[y*400+tap.hi]);
   for(unsigned c=0;c<3;c++)rows[y*800+x][c]=(4-tap.fraction)*channel565(a,c)+tap.fraction*channel565(b,c);
  }
  for(unsigned y=0;y<480;y++){
   auto tap=vertical.taps[y];auto*a=rows.data()+tap.lo*800;auto*b=rows.data()+tap.hi*800;
#ifdef __aarch64__
   for(unsigned x=0;x<800;x+=8){auto top=vld3q_s16(a[x].data()),bottom=vld3q_s16(b[x].data());uint8x8x4_t pixels;
    for(unsigned c=0;c<3;c++){
     auto value=vmlaq_n_s16(vmulq_n_s16(top.val[c],4-tap.fraction),bottom.val[c],tap.fraction);
     auto magnitude=vshrq_n_s16(vaddq_s16(vabsq_s16(value),vdupq_n_s16(8)),4);
     auto rounded=vbslq_s16(vcltq_s16(value,vdupq_n_s16(0)),vnegq_s16(magnitude),magnitude);
     pixels.val[2-c]=vmovn_u16(vreinterpretq_u16_s16(vaddq_s16(rounded,vdupq_n_s16(128))));
    }
    pixels.val[3]=vdup_n_u8(0);vst4_u8(reinterpret_cast<uint8_t*>(output.data()+y*800+x),pixels);
   }
#else
   for(unsigned x=0;x<800;x++){uint32_t pixel=0;for(unsigned c=0;c<3;c++)pixel|=uint32_t(rounded<16>((4-tap.fraction)*a[x][c]+tap.fraction*b[x][c])+128)<<(16-8*c);output[y*800+x]=pixel;}
#endif
  }
 }
};
}
