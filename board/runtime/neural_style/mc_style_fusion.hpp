// SPDX-License-Identifier: MIT
#pragma once
#include "frame_resample.hpp"
#include <cstdlib>
#define RIX_MC_FUSION_FACTORED_NEON 1

namespace rix_frames {
#ifdef __aarch64__
namespace mc_style_detail {
inline uint16x8x3_t expand565(uint16x8_t pixel) {
 uint16x8x3_t result;
 auto red=vshrq_n_u16(pixel,11);
 auto green=vandq_u16(vshrq_n_u16(pixel,5),vdupq_n_u16(63));
 auto blue=vandq_u16(pixel,vdupq_n_u16(31));
 result.val[0]=vorrq_u16(vshlq_n_u16(red,3),vshrq_n_u16(red,2));
 result.val[1]=vorrq_u16(vshlq_n_u16(green,2),vshrq_n_u16(green,4));
 result.val[2]=vorrq_u16(vshlq_n_u16(blue,3),vshrq_n_u16(blue,2));
 return result;
}
inline uint16x8_t duplicate4(uint16x4_t values) {
 auto pairs=vzip_u16(values,values);
 return vcombine_u16(pairs.val[0],pairs.val[1]);
}
// Exact half-away-from-zero n/1638400 for |n|<=417792000. The unsigned
// ceil(2^32/divisor) reciprocal overestimates the quotient by at most one:
// n'*(2622/2^32 - 1/divisor) < 0.055 for n'=abs(n)+divisor/2.
// Compare q*divisor with n' to remove that possible one-unit overestimate.
inline int32x4_t rounded_correction4(int32x4_t value) {
 auto numerator=vaddq_u32(vreinterpretq_u32_s32(vabsq_s32(value)),vdupq_n_u32(819200));
 auto low=vmull_n_u32(vget_low_u32(numerator),2622);
 auto high=vmull_n_u32(vget_high_u32(numerator),2622);
 auto quotient=vcombine_u32(vshrn_n_u64(low,32),vshrn_n_u64(high,32));
 auto excess=vcgtq_u32(vmulq_n_u32(quotient,1638400),numerator);
 quotient=vsubq_u32(quotient,vandq_u32(excess,vdupq_n_u32(1)));
 auto magnitude=vreinterpretq_s32_u32(quotient);
 return vbslq_s32(vcltq_s32(value,vdupq_n_s32(0)),vnegq_s32(magnitude),magnitude);
}
// floor(floor(m/65536)/25) == floor(m/1638400). After adding the
// half-denominator, m>>16 is at most 6387, so eight 16-bit lanes replace
// the previous two sets of 32->64-bit products. ceil(65536/25)=2622
// overestimates floor(n/25) by at most one in this range; correct it.
inline int16x8_t rounded_correction8(int32x4_t low,int32x4_t high,int16x8_t sign) {
 auto lo=vaddq_u32(vreinterpretq_u32_s32(vabsq_s32(low)),vdupq_n_u32(819200));
 auto hi=vaddq_u32(vreinterpretq_u32_s32(vabsq_s32(high)),vdupq_n_u32(819200));
 auto numerator=vcombine_u16(vshrn_n_u32(lo,16),vshrn_n_u32(hi,16));
 auto quotient=vcombine_u16(vshrn_n_u32(vmull_n_u16(vget_low_u16(numerator),2622),16),
                            vshrn_n_u32(vmull_n_u16(vget_high_u16(numerator),2622),16));
 auto excess=vcgtq_u16(vmulq_n_u16(quotient,25),numerator);
 quotient=vsubq_u16(quotient,vandq_u16(excess,vdupq_n_u16(1)));
 auto magnitude=vreinterpretq_s16_u16(quotient);
 return vbslq_s16(vcltq_s16(sign,vdupq_n_s16(0)),vnegq_s16(magnitude),magnitude);
}
inline uint16x8_t edge_weights8(const uint16_t*center,const uint16_t*up,const uint16_t*down) {
 auto rgb=expand565(vld1q_u16(center));
 uint16x8_t difference=vdupq_n_u16(0);
 const uint16_t*neighbors[]={center-1,center+1,up,down};
 for(const auto*neighbor:neighbors) {
  auto other=expand565(vld1q_u16(neighbor));
  for(unsigned c=0;c<3;c++)difference=vmaxq_u16(difference,vabdq_u16(rgb.val[c],other.val[c]));
 }
 auto clipped=vminq_u16(vmaxq_u16(difference,vdupq_n_u16(8)),vdupq_n_u16(64));
 auto numerator=vshlq_n_u16(vsubq_u16(vdupq_n_u16(64),clipped),5);
 // floor(n/7), n<=1792: ceil(65536/7)=9363 has error <1/7 here.
 return vcombine_u16(vshrn_n_u32(vmull_n_u16(vget_low_u16(numerator),9363),16),
                     vshrn_n_u32(vmull_n_u16(vget_high_u16(numerator),9363),16));
}
}
#endif
// Low-frequency neural colour correction over an immutable, same-frame RGB565
// source. This is ARM composition; CNN inference can still run on the FPGA.
// Rectangles protect actual source-space UI regions supplied by the caller.
// No rectangle is guessed here, and this does not itself separate engine HUDs.
struct McStyleRect { unsigned x, y, width, height; };
class McStyleFusion {
 Axis<96,480> uy;
 std::vector<std::array<int16_t,3>> horizontal =
     std::vector<std::array<int16_t,3>>(96*800);
 std::vector<uint16_t> weights = std::vector<uint16_t>(96000);
 static uint32_t original(uint16_t pixel) {
  uint32_t result=0;
  for(unsigned c=0;c<3;c++)result|=uint32_t(channel565(pixel,c)+128)<<(16-8*c);
  return result;
 }
 static unsigned difference(uint16_t a,uint16_t b) {
  unsigned d=0;
  for(unsigned c=0;c<3;c++)d=std::max(d,unsigned(std::abs(channel565(a,c)-channel565(b,c))));
  return d;
 }
 static void original_row(const uint16_t*source,uint32_t*display) {
#ifdef __aarch64__
  for(unsigned x=0;x<400;x+=4) {
   auto rgb=mc_style_detail::expand565(mc_style_detail::duplicate4(vld1_u16(source+x)));
   uint8x8x4_t pixels;
   for(unsigned c=0;c<3;c++)pixels.val[2-c]=vmovn_u16(rgb.val[c]);
   pixels.val[3]=vdup_n_u8(0);vst4_u8(reinterpret_cast<uint8_t*>(display+x*2),pixels);
  }
#else
  for(unsigned x=0;x<400;x++)display[2*x]=display[2*x+1]=original(source[x]);
#endif
 }
public:
 using Rect=McStyleRect;
 void compose(const std::vector<uint16_t>&source,const rix_cnn::Frame&input,
              const rix_cnn::Frame&styled,std::vector<uint32_t>&display,
              unsigned strength=128,const std::vector<Rect>&protected_rects={}) {
  if(source.size()!=96000||input.size()!=15360||styled.size()!=15360||display.size()!=384000)
   throw std::runtime_error("invalid MC style fusion buffers");
  if(strength>256)throw std::runtime_error("MC style strength must be 0..256");
  for(const auto&r:protected_rects)
   if(!r.width||!r.height||r.x>=400||r.y>=240||r.width>400-r.x||r.height>240-r.y)
    throw std::runtime_error("MC style protection rectangle is outside source");
  if(!strength) {
   for(unsigned y=0;y<240;y++) {
    original_row(source.data()+y*400,display.data()+2*y*800);
    std::copy_n(display.data()+2*y*800,800,display.data()+(2*y+1)*800);
   }
   return;
  }
  std::array<bool,240> protected_rows{};
  for(const auto&r:protected_rects)if(r.x==0&&r.width==400)
   std::fill(protected_rows.begin()+r.y,protected_rows.begin()+r.y+r.height,true);
  std::array<bool,96> needed{};
  for(unsigned y=0;y<480;y++)if(!protected_rows[y/2]) {
   needed[uy.taps[y].lo]=true;needed[uy.taps[y].hi]=true;
  }
  // Full colour residual in flat areas. Gradually suppress correction at
  // original-source contrast edges (8..64 RGB levels), fully preserving
  // strong block/texture/text boundaries. No previous frame is mixed in.
  for(unsigned y=0;y<240;y++) {
   if(protected_rows[y]) {
    std::fill_n(weights.data()+y*400,400,0);
    continue;
   }
   unsigned x=0;
   auto scalar_weight=[&](unsigned x) {
   unsigned i=y*400+x,d=0;
   if(x)d=std::max(d,difference(source[i],source[i-1]));
   if(x+1<400)d=std::max(d,difference(source[i],source[i+1]));
   if(y)d=std::max(d,difference(source[i],source[i-400]));
   if(y+1<240)d=std::max(d,difference(source[i],source[i+400]));
   weights[i]=d<=8?256:(d>=64?0:(64-d)*256/56);
   };
#ifdef __aarch64__
   scalar_weight(x++);
   const auto*row=source.data()+y*400;
   const auto*up=source.data()+(y?y-1:y)*400;
   const auto*down=source.data()+(y+1<240?y+1:y)*400;
   for(;x+8<400;x+=8)vst1q_u16(weights.data()+y*400+x,mc_style_detail::edge_weights8(row+x,up+x,down+x));
#endif
   for(;x<400;x++)scalar_weight(x);
  }
  for(const auto&r:protected_rects)for(unsigned y=r.y;y<r.y+r.height;y++)
   std::fill(weights.begin()+y*400+r.x,weights.begin()+y*400+r.x+r.width,0);
  // Signed residual needs 9 bits, so do not put it back into an INT8 Frame.
  for(unsigned y=0;y<96;y++)if(needed[y]) {
   auto*row=horizontal.data()+y*800;
   // Out x=2+5*i+f has coefficients (5-f)*delta[i]+f*delta[i+1].
   // Load each adjacent low-resolution pixel once for five output pixels.
   for(unsigned c=0;c<3;c++) {
    int left=int(styled[y*160][c])-int(input[y*160][c]);
    row[0][c]=row[1][c]=int16_t(5*left);
    for(unsigned i=0;i<159;i++) {
     int right=int(styled[y*160+i+1][c])-int(input[y*160+i+1][c]);
     int value=5*left,step=right-left;
     for(unsigned f=0;f<5;f++,value+=step)row[2+5*i+f][c]=int16_t(value);
     left=right;
    }
    row[797][c]=row[798][c]=row[799][c]=int16_t(5*left);
   }
  }
  for(unsigned y=0;y<480;y++) {
   if(protected_rows[y/2]) {
    if(!(y&1))original_row(source.data()+(y/2)*400,display.data()+y*800);
    else std::copy_n(display.data()+(y-1)*800,800,display.data()+y*800);
    continue;
   }
   const auto ty=uy.taps[y];
   const auto*a=horizontal.data()+ty.lo*800;
   const auto*b=horizontal.data()+ty.hi*800;
#ifdef __aarch64__
   static_assert(sizeof(std::array<int16_t,3>)==6,"packed residual RGB");
   for(unsigned x=0;x<800;x+=8) {
    unsigned i=(y/2)*400+x/2;
    auto rgb=mc_style_detail::expand565(mc_style_detail::duplicate4(vld1_u16(source.data()+i)));
    auto edge_weight=mc_style_detail::duplicate4(vld1_u16(weights.data()+i));
    uint8x8x4_t pixels;
    if(vmaxvq_u16(edge_weight)==0) {
     for(unsigned c=0;c<3;c++)pixels.val[2-c]=vmovn_u16(rgb.val[c]);
     pixels.val[3]=vdup_n_u8(0);vst4_u8(reinterpret_cast<uint8_t*>(display.data()+y*800+x),pixels);
     continue;
    }
    auto top=vld3q_s16(a[x].data()),bottom=vld3q_s16(b[x].data());
    for(unsigned c=0;c<3;c++) {
     auto residual=vmlaq_n_s16(vmulq_n_s16(top.val[c],5-ty.fraction),bottom.val[c],ty.fraction);
     auto low=vmulq_n_s32(vmull_s16(vget_low_s16(residual),vreinterpret_s16_u16(vget_low_u16(edge_weight))),strength);
     auto high=vmulq_n_s32(vmull_s16(vget_high_s16(residual),vreinterpret_s16_u16(vget_high_u16(edge_weight))),strength);
     auto correction=mc_style_detail::rounded_correction8(low,high,residual);
     pixels.val[2-c]=vqmovun_s16(vaddq_s16(vreinterpretq_s16_u16(rgb.val[c]),correction));
    }
    pixels.val[3]=vdup_n_u8(0);
    vst4_u8(reinterpret_cast<uint8_t*>(display.data()+y*800+x),pixels);
   }
#else
   for(unsigned x=0;x<800;x++) {
    unsigned i=(y/2)*400+x/2;
    if(!weights[i]){display[y*800+x]=original(source[i]);continue;}
    uint32_t rgb=0;
    for(unsigned c=0;c<3;c++) {
     int residual=(5-ty.fraction)*a[x][c]+ty.fraction*b[x][c];
     // Maximum magnitude 255*25*256*256 = 417792000, within int32.
     int correction=rounded<25*256*256>(residual*int(strength)*int(weights[i]));
     int value=std::clamp(channel565(source[i],c)+128+correction,0,255);
     rgb|=uint32_t(value)<<(16-8*c);
    }
    display[y*800+x]=rgb;
   }
#endif
  }
 }
};
}
