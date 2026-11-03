// SPDX-License-Identifier: MIT
#pragma once
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <type_traits>
#include <vector>
#if defined(__aarch64__)
#include <arm_neon.h>
#endif
namespace rix_cnn {
using Pixel=std::array<int8_t,8>;
using Frame=std::vector<Pixel>;
struct Model {
 std::array<uint32_t,1776> words;
 explicit Model(const std::string&path){
  std::ifstream f(path,std::ios::binary);char magic[8];uint32_t count;
  f.read(magic,8);f.read(reinterpret_cast<char*>(&count),4);f.read(reinterpret_cast<char*>(words.data()),words.size()*4);
  if(!f||f.peek()!=EOF||memcmp(magic,"RIXCNN1\0",8)||count!=1776)throw std::runtime_error("invalid RIXCNN1 model");
  for(int i=1728;i<1752;i++)if(int64_t(int32_t(words[i]))<-(1LL<<28)||int64_t(int32_t(words[i]))>(1LL<<28))throw std::runtime_error("bias exceeds INT32 contract");
  for(int i=1752;i<1776;i++)if(words[i]>20)throw std::runtime_error("invalid requantization shift");
 }
};
inline int8_t requantize(int32_t value,unsigned shift,bool final){
 int64_t magnitude=value<0?-int64_t(value):int64_t(value);
 int64_t q=(magnitude+(shift?(1LL<<(shift-1)):0))>>shift;if(value<0)q=-q;
 if(q>127)q=127;if(q<(final?-128:0))q=final?-128:0;return int8_t(q);
}
inline Frame infer(const Frame&input,unsigned w,unsigned h,const Model&m){
 if(!w||!h||w>400||h>240||input.size()!=size_t(w)*h)throw std::runtime_error("invalid tensor dimensions");
 Frame a=input,b(input.size());
 for(unsigned layer=0;layer<3;layer++){
#if defined(__aarch64__)
  int8x8_t packed[8][9];
  bool constant_tail=true;
  bool rgb_only=true;
  for(unsigned oc=0;oc<8;oc++)for(unsigned tap=0;tap<9;tap++){
   Pixel weights;
   unsigned rgb_magnitude=0;
   for(unsigned ic=0;ic<8;ic++){
    weights[ic]=int8_t(m.words[layer*576+oc*72+tap*8+ic]);
    if(oc>=3 && weights[ic])constant_tail=false;
    if(ic>=3 && weights[ic])rgb_only=false;
    if(ic<3)rgb_magnitude+=weights[ic]<0?-int(weights[ic]):int(weights[ic]);
   }
   // The three products may share an INT16 accumulator only when their
   // worst-case absolute sum fits, including an INT8 input of -128.
   if(rgb_magnitude>255)rgb_only=false;
   packed[oc][tap]=vld1_s8(weights.data());
  }
  int8x8_t rgb_weights[9][3];
  if(rgb_only)for(unsigned tap=0;tap<9;tap++)for(unsigned ic=0;ic<3;ic++){
   Pixel channels;
   for(unsigned oc=0;oc<8;oc++)
    channels[oc]=int8_t(m.words[layer*576+oc*72+tap*8+ic]);
   rgb_weights[tap][ic]=vld1_s8(channels.data());
  }
  Pixel constants{};
  if(constant_tail)for(unsigned oc=3;oc<8;oc++)
   constants[oc]=requantize(int32_t(m.words[1728+layer*8+oc]),m.words[1752+layer*8+oc],layer==2);
  auto convolve=[&](auto outputs,unsigned lo,unsigned hi){
   for(unsigned y=lo;y<hi;y++){
    const Pixel* rows[]={a.data()+(y?y-1:y)*w,a.data()+y*w,a.data()+(y+1<h?y+1:y)*w};
    for(unsigned x=0;x<w;x++){
     const unsigned columns[]={x?x-1:x,x,x+1<w?x+1:x};
     int8x8_t samples[9];
     for(unsigned ky=0;ky<3;ky++)for(unsigned kx=0;kx<3;kx++)
      samples[ky*3+kx]=vld1_s8(rows[ky][columns[kx]].data());
     Pixel& pixel=b[y*w+x];
     if constexpr(decltype(outputs)::value==3)pixel=constants;
     for(unsigned oc=0;oc<decltype(outputs)::value;oc++){
      int32x4_t partial=vdupq_n_s32(0);
      // Widen each adjacent pair before adding: two INT8 products can exceed INT16.
      for(unsigned tap=0;tap<9;tap++)
       partial=vpadalq_s16(partial,vmull_s8(samples[tap],packed[oc][tap]));
      const int32_t sum=int32_t(m.words[1728+layer*8+oc])+vaddvq_s32(partial);
      pixel[oc]=requantize(sum,m.words[1752+layer*8+oc],layer==2);
     }
    }
   }
  };
  auto convolve_rgb=[&](unsigned lo,unsigned hi){
   for(unsigned y=lo;y<hi;y++){
    const Pixel* rows[]={a.data()+(y?y-1:y)*w,a.data()+y*w,a.data()+(y+1<h?y+1:y)*w};
    for(unsigned x=0;x<w;x++){
     const unsigned columns[]={x?x-1:x,x,x+1<w?x+1:x};
     auto low=vdupq_n_s32(0),high=vdupq_n_s32(0);
     for(unsigned ky=0;ky<3;ky++)for(unsigned kx=0;kx<3;kx++){
      const Pixel& sample=rows[ky][columns[kx]];
      const auto* weights=rgb_weights[ky*3+kx];
      auto products=vmull_s8(weights[0],vdup_n_s8(sample[0]));
      products=vmlal_s8(products,weights[1],vdup_n_s8(sample[1]));
      products=vmlal_s8(products,weights[2],vdup_n_s8(sample[2]));
      low=vaddw_s16(low,vget_low_s16(products));
      high=vaddw_s16(high,vget_high_s16(products));
     }
     int32_t sums[8];
     vst1q_s32(sums,low);
     vst1q_s32(sums+4,high);
     for(unsigned oc=0;oc<8;oc++){
      const int32_t sum=int32_t(m.words[1728+layer*8+oc])+sums[oc];
      b[y*w+x][oc]=requantize(sum,m.words[1752+layer*8+oc],layer==2);
     }
    }
   }
  };
  auto work=[&](unsigned lo,unsigned hi){
   // Only omit multiply-accumulates for outputs whose full kernel is zero.
   if(constant_tail)convolve(std::integral_constant<unsigned,3>{},lo,hi);
   else if(rgb_only)convolve_rgb(lo,hi);
   else convolve(std::integral_constant<unsigned,8>{},lo,hi);
  };
#else
  auto work=[&](unsigned lo,unsigned hi){
   for(unsigned y=lo;y<hi;y++)for(unsigned x=0;x<w;x++)for(unsigned oc=0;oc<8;oc++){
    int32_t sum=int32_t(m.words[1728+layer*8+oc]);
    for(int ky=0;ky<3;ky++)for(int kx=0;kx<3;kx++){
     int xx=int(x)+kx-1,yy=int(y)+ky-1;xx=xx<0?0:(xx>=int(w)?w-1:xx);yy=yy<0?0:(yy>=int(h)?h-1:yy);
     const Pixel&p=a[yy*w+xx];const uint32_t*coef=m.words.data()+layer*576+oc*72+(ky*3+kx)*8;
     for(unsigned ic=0;ic<8;ic++)sum+=int32_t(p[ic])*int32_t(int8_t(coef[ic]));
    }
    b[y*w+x][oc]=requantize(sum,m.words[1752+layer*8+oc],layer==2);
   }
  };
#endif
  std::array<std::thread,3> workers;
  for(unsigned i=0;i<3;i++)workers[i]=std::thread(work,h*i/4,h*(i+1)/4);
  work(h*3/4,h);for(auto&t:workers)t.join();a.swap(b);
 }
 return a;
}
}
