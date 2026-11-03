// SPDX-License-Identifier: MIT
#pragma once
#include "frame_resample.hpp"
#include "mc_style_fusion.hpp"

namespace rix_frames {
#ifdef __aarch64__
// |value|<=12800. floor((abs(value)+50)/100) equals
// floor(((abs(value)+50)>>2)/25). The latter numerator <=3212;
// ceil(65536/25)=2622 is exact over this range (error <1/25).
inline int16x8_t rounded100_poly(int16x8_t value){
 auto magnitude=vshrq_n_u16(vaddq_u16(vreinterpretq_u16_s16(vabsq_s16(value)),vdupq_n_u16(50)),2);
 auto q=vcombine_u16(vshrn_n_u32(vmull_n_u16(vget_low_u16(magnitude),2622),16),vshrn_n_u32(vmull_n_u16(vget_high_u16(magnitude),2622),16));
 auto signed_q=vreinterpretq_s16_u16(q);
 return vbslq_s16(vcltq_s16(value,vdupq_n_s16(0)),vnegq_s16(signed_q),signed_q);
}
#endif
// CNN RGB is unchanged. Add bounded, same-frame source luminance detail after
// exact 2.5x interpolation; keep the CNN's colour transform. ARM composition.
class NativeStyle400Poly {
 using RGB=std::array<int16_t,3>;
 Axis<96,240> vertical;
 std::vector<RGB> styled_rows=std::vector<RGB>(96*400);
 std::vector<RGB> original_rows=std::vector<RGB>(96*400);
 static void horizontal(const rix_cnn::Frame&frame,std::vector<RGB>&rows){
  // After clamping the first pixel, the 160->400 phase pattern repeats every
  // five output pixels and advances by two input pixels. Same rational taps.
  for(unsigned y=0;y<96;y++)for(unsigned c=0;c<3;c++){
   auto*row=rows.data()+y*400;row[0][c]=10*int(frame[y*160][c]);
   for(unsigned i=0;i<79;i++){
    int a=frame[y*160+2*i][c],b=frame[y*160+2*i+1][c],next=frame[y*160+2*i+2][c];
    int step=b-a,value=10*a+step;
    row[5*i+1][c]=value;row[5*i+2][c]=value+4*step;row[5*i+3][c]=value+8*step;
    step=next-b;value=10*b+3*step;
    row[5*i+4][c]=value;row[5*i+5][c]=value+4*step;
   }
   int a=frame[y*160+158][c],b=frame[y*160+159][c],step=b-a,value=10*a+step;
   row[396][c]=value;row[397][c]=value+4*step;row[398][c]=value+8*step;row[399][c]=10*b;
  }
 }
 static uint32_t original(uint16_t pixel){
  return (uint32_t(channel565(pixel,0)+128)<<16)|(uint32_t(channel565(pixel,1)+128)<<8)|uint32_t(channel565(pixel,2)+128);
 }
#ifdef __aarch64__
 static int16x8_t rounded_luma(int32x4_t low,int32x4_t high){
  auto round=[](int32x4_t value){
   auto magnitude=vshrq_n_s32(vaddq_s32(vabsq_s32(value),vdupq_n_s32(128)),8);
   return vbslq_s32(vcltq_s32(value,vdupq_n_s32(0)),vnegq_s32(magnitude),magnitude);
  };
  return vcombine_s16(vmovn_s32(round(low)),vmovn_s32(round(high)));
 }
#endif
public:
 using Rect=McStyleRect;
 void compose(const std::vector<uint16_t>&source,const rix_cnn::Frame&input,
              const rix_cnn::Frame&styled,std::vector<uint32_t>&display,
              unsigned gain=192,const std::vector<Rect>&rectangles={}){
  if(source.size()!=96000||input.size()!=15360||styled.size()!=15360||display.size()!=96000||gain>256)
   throw std::runtime_error("invalid luminance detail buffers/gain");
  for(const auto&r:rectangles)if(!r.width||!r.height||r.x>=400||r.y>=240||r.width>400-r.x||r.height>240-r.y)
   throw std::runtime_error("invalid luminance detail rectangle");
  horizontal(styled,styled_rows);if(gain)horizontal(input,original_rows);
  for(unsigned y=0;y<240;y++){
   auto tap=vertical.taps[y];auto*a=styled_rows.data()+tap.lo*400;auto*b=styled_rows.data()+tap.hi*400;
   auto*p=original_rows.data()+tap.lo*400;auto*q=original_rows.data()+tap.hi*400;
#ifdef __aarch64__
   for(unsigned x=0;x<400;x+=8){
    auto top=vld3q_s16(a[x].data()),bottom=vld3q_s16(b[x].data());
    int16x8x3_t colour;
    for(unsigned c=0;c<3;c++)colour.val[c]=vaddq_s16(rounded100_poly(vmlaq_n_s16(vmulq_n_s16(top.val[c],10-tap.fraction),bottom.val[c],tap.fraction)),vdupq_n_s16(128));
    int16x8_t correction=vdupq_n_s16(0);
    if(gain){
     auto lo=vld3q_s16(p[x].data()),hi=vld3q_s16(q[x].data());
     auto orig=mc_style_detail::expand565(vld1q_u16(source.data()+y*400+x));
     auto original_y=vdupq_n_u16(0),small_y=vdupq_n_u16(0);
     const uint16_t coefficients[3]={77,150,29};
     for(unsigned c=0;c<3;c++){
      auto small=vaddq_s16(rounded100_poly(vmlaq_n_s16(vmulq_n_s16(lo.val[c],10-tap.fraction),hi.val[c],tap.fraction)),vdupq_n_s16(128));
      original_y=vmlaq_n_u16(original_y,orig.val[c],coefficients[c]);
      small_y=vmlaq_n_u16(small_y,vreinterpretq_u16_s16(small),coefficients[c]);
     }
     auto low=vreinterpretq_s32_u32(vsubl_u16(vget_low_u16(original_y),vget_low_u16(small_y)));
     auto high=vreinterpretq_s32_u32(vsubl_u16(vget_high_u16(original_y),vget_high_u16(small_y)));
     auto detail=vminq_s16(vmaxq_s16(rounded_luma(low,high),vdupq_n_s16(-48)),vdupq_n_s16(48));
     auto magnitude=vshrq_n_u16(vaddq_u16(vmulq_n_u16(vreinterpretq_u16_s16(vabsq_s16(detail)),gain),vdupq_n_u16(128)),8);
     auto signed_magnitude=vreinterpretq_s16_u16(magnitude);
     correction=vbslq_s16(vcltq_s16(detail,vdupq_n_s16(0)),vnegq_s16(signed_magnitude),signed_magnitude);
    }
    uint8x8x4_t pixels;
    for(unsigned c=0;c<3;c++)pixels.val[2-c]=vqmovun_s16(vaddq_s16(colour.val[c],correction));
    pixels.val[3]=vdup_n_u8(0);vst4_u8(reinterpret_cast<uint8_t*>(display.data()+y*400+x),pixels);
   }
#else
   for(unsigned x=0;x<400;x++){
    int correction=0;
    if(gain){
     int numerator=0;const int coefficients[3]={77,150,29};
     for(unsigned c=0;c<3;c++){
      int low=rounded<100>((10-tap.fraction)*p[x][c]+tap.fraction*q[x][c])+128;
      numerator+=(channel565(source[y*400+x],c)+128-low)*coefficients[c];
     }
     correction=rounded<256>(std::clamp(rounded<256>(numerator),-48,48)*int(gain));
    }
    uint32_t pixel=0;
    for(unsigned c=0;c<3;c++){
     int value=rounded<100>((10-tap.fraction)*a[x][c]+tap.fraction*b[x][c])+128;
     pixel|=uint32_t(std::clamp(value+correction,0,255))<<(16-8*c);
    }
    display[y*400+x]=pixel;
   }
#endif
  }
  // Only explicit caller-supplied source-space regions are protected. This is
  // not engine HUD detection. Preserve each source pixel at native resolution.
  for(const auto&r:rectangles)for(unsigned y=r.y;y<r.y+r.height;y++)for(unsigned x=r.x;x<r.x+r.width;x++){
   display[y*400+x]=original(source[y*400+x]);
  }
 }
};
}
