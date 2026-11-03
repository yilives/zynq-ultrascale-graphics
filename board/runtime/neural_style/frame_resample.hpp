// SPDX-License-Identifier: MIT
#pragma once
#include "cnn_cpu.hpp"
#include <algorithm>
#include <array>
#include <numeric>
#ifdef __aarch64__
#include <arm_neon.h>
#endif

namespace rix_frames {
// Center-aligned coordinates are exact rationals: /4 for 400 -> 160 and
// /5 for 160 -> 800. Preserve signed, half-away-from-zero RGB rounding.
template<unsigned In, unsigned Out> struct Axis {
 static constexpr int distance=In>Out?In-Out:Out-In;
 static constexpr int divisor=std::gcd(std::gcd(2*int(In),distance),2*int(Out));
 static constexpr int denominator=2*int(Out)/divisor;
 struct Tap { unsigned lo,hi; int fraction; };
 std::array<Tap,Out> taps;
 Axis(){for(unsigned x=0;x<Out;x++){
  int n=std::max(0,(2*int(x)+1)*int(In)-int(Out))/divisor;
  unsigned lo=n/denominator;
  taps[x]={lo,std::min(lo+1,In-1),n%denominator};
 }}
};
template<int Den> inline int rounded(int n){return n<0?-((-n+Den/2)/Den):(n+Den/2)/Den;}
#ifdef __aarch64__
// Exact division for this scaler's accumulator range [-3200,3175]. For
// x=abs(n)+12 <=3212, floor(x*2622/65536) == floor(x/25); the reciprocal
// error is smaller than the minimum 1/25 remainder gap. No approximate math.
inline int16x8_t rounded25(int16x8_t n){
 uint16x8_t magnitude=vaddq_u16(vreinterpretq_u16_s16(vabsq_s16(n)),vdupq_n_u16(12));
 uint16x8_t q=vcombine_u16(vshrn_n_u32(vmull_n_u16(vget_low_u16(magnitude),2622),16),vshrn_n_u32(vmull_n_u16(vget_high_u16(magnitude),2622),16));
 auto value=vreinterpretq_s16_u16(q);
 return vbslq_s16(vcltq_s16(n,vdupq_n_s16(0)),vnegq_s16(value),value);
}
#endif
inline int channel565(uint16_t p,unsigned c){
 unsigned v=c==0?(p>>11):(c==1?((p>>5)&63):(p&31));
 return int(c==1?((v<<2)|(v>>4)):((v<<3)|(v>>2)))-128;
}
struct Resampler {
 static_assert(Axis<400,160>::denominator==4&&Axis<240,96>::denominator==4,"downsample coefficients");
 static_assert(Axis<160,800>::denominator==5&&Axis<96,480>::denominator==5,"upscale coefficients");
 Axis<400,160> dx;Axis<240,96> dy;
 Axis<160,800> ux;Axis<96,480> uy;
 std::array<bool,240> source_rows{};
 std::vector<std::array<int16_t,3>> horizontal=std::vector<std::array<int16_t,3>>(96*800);
 Resampler(){for(auto t:dy.taps){source_rows[t.lo]=true;source_rows[t.hi]=true;}}
 void downsample(const std::vector<uint16_t>&source,rix_cnn::Frame&small)const{
  if(source.size()!=96000||small.size()!=15360)throw std::runtime_error("invalid downsample buffers");
  for(unsigned y=0;y<96;y++){
   auto ty=dy.taps[y];const auto*a=source.data()+ty.lo*400;const auto*b=source.data()+ty.hi*400;
   for(unsigned x=0;x<160;x++){
    auto tx=dx.taps[x];auto&p=small[y*160+x];
    for(unsigned c=0;c<3;c++){
     int top=(4-tx.fraction)*channel565(a[tx.lo],c)+tx.fraction*channel565(a[tx.hi],c);
     int bottom=(4-tx.fraction)*channel565(b[tx.lo],c)+tx.fraction*channel565(b[tx.hi],c);
     p[c]=int8_t(rounded<16>((4-ty.fraction)*top+ty.fraction*bottom));
    }
   }
  }
 }
 void upscale(const rix_cnn::Frame&small,std::vector<uint32_t>&display){
  if(small.size()!=15360||display.size()!=384000)throw std::runtime_error("invalid upscale buffers");
  // Only 96 horizontal rows are needed. Reuse them for five output rows;
  // avoid recomputing four RGB samples for every one of 384,000 pixels.
  for(unsigned y=0;y<96;y++)for(unsigned x=0;x<800;x++){
   auto tx=ux.taps[x];const auto&a=small[y*160+tx.lo];const auto&b=small[y*160+tx.hi];
   for(unsigned c=0;c<3;c++)horizontal[y*800+x][c]=(5-tx.fraction)*a[c]+tx.fraction*b[c];
  }
  for(unsigned y=0;y<480;y++){
   auto ty=uy.taps[y];const auto*a=horizontal.data()+ty.lo*800;const auto*b=horizontal.data()+ty.hi*800;
#ifdef __aarch64__
   static_assert(sizeof(std::array<int16_t,3>)==6,"packed horizontal RGB");
   for(unsigned x=0;x<800;x+=8){
    auto top=vld3q_s16(a[x].data()),bottom=vld3q_s16(b[x].data());uint8x8x4_t pixels;
    for(unsigned c=0;c<3;c++){
     auto sum=vmlaq_n_s16(vmulq_n_s16(top.val[c],5-ty.fraction),bottom.val[c],ty.fraction);
     pixels.val[2-c]=vmovn_u16(vreinterpretq_u16_s16(vaddq_s16(rounded25(sum),vdupq_n_s16(128))));
    }
    pixels.val[3]=vdup_n_u8(0);vst4_u8(reinterpret_cast<uint8_t*>(display.data()+y*800+x),pixels);
   }
#else
   for(unsigned x=0;x<800;x++){
    uint32_t rgb=0;
    for(unsigned c=0;c<3;c++)rgb|=uint32_t(rounded<25>((5-ty.fraction)*a[x][c]+ty.fraction*b[x][c])+128)<<(16-8*c);
    display[y*800+x]=rgb;
   }
#endif
  }
 }
};
}
