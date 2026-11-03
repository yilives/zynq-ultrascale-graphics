// SPDX-License-Identifier: MIT
// Compatibility oracle: retain the released floating-point coordinate and
// rounding rules, independently of the optimized integer implementation.
#include "frame_resample.hpp"
#include "pl_frames.hpp"
#include <cmath>
#include <iostream>
#include <random>
using rix_cnn::Frame;
static Frame legacy(const Frame&a,unsigned iw,unsigned ih,unsigned ow,unsigned oh){
 Frame b(size_t(ow)*oh);
 for(unsigned y=0;y<oh;y++)for(unsigned x=0;x<ow;x++){
  double px=std::max(0.0,(x+0.5)*iw/ow-0.5),py=std::max(0.0,(y+0.5)*ih/oh-0.5);
  unsigned xx=unsigned(px),yy=unsigned(py),nx=std::min(xx+1,iw-1),ny=std::min(yy+1,ih-1);double fx=px-xx,fy=py-yy;
  for(unsigned c=0;c<3;c++)b[y*ow+x][c]=int8_t(std::clamp(int(std::round((1-fy)*((1-fx)*a[yy*iw+xx][c]+fx*a[yy*iw+nx][c])+fy*((1-fx)*a[ny*iw+xx][c]+fx*a[ny*iw+nx][c]))),-128,127));
 }
 return b;
}
int main(){try{
 rix_frames::Resampler resample;std::mt19937 random(0x534e5031);
 if(std::count(resample.source_rows.begin(),resample.source_rows.end(),true)!=192)throw std::runtime_error("snapshot row count changed");
 size_t checked=0;
 for(unsigned pattern=0;pattern<14;pattern++){
  std::vector<uint16_t> source(96000);Frame rgb(96000),small(15360);
  for(unsigned i=0;i<96000;i++){
   uint16_t v=pattern==0?uint16_t(i):pattern==1?uint16_t((i+i/400)%2?0xffff:0):uint16_t(random());source[i]=v;
   unsigned r=v>>11,g=(v>>5)&63,b=v&31;
   rgb[i][0]=int((r<<3)|(r>>2))-128;rgb[i][1]=int((g<<2)|(g>>4))-128;rgb[i][2]=int((b<<3)|(b>>2))-128;
  }
  Frame expected=legacy(rgb,400,240,160,96);resample.downsample(source,small);
  if(small!=expected)throw std::runtime_error("downsample differs from released bilinear");
  // Poison unread rows: no consumed source pixel may depend on them.
  for(unsigned y=0;y<240;y++)if(!resample.source_rows[y])std::fill_n(source.data()+y*400,400,uint16_t(random()));
  resample.downsample(source,small);if(small!=expected)throw std::runtime_error("sparse snapshot omitted a required row");
  for(unsigned i=0;i<15360;i++)for(unsigned c=0;c<3;c++)small[i][c]=pattern<2?int8_t((i+c)%2?127:-128):int8_t(random());
  auto expanded=legacy(small,160,96,800,480);std::vector<uint32_t> display(384000);resample.upscale(small,display);
  for(unsigned i=0;i<384000;i++){
   uint32_t pixel=(uint32_t(int(expanded[i][0])+128)<<16)|(uint32_t(int(expanded[i][1])+128)<<8)|uint32_t(int(expanded[i][2])+128);
   if(pixel!=display[i])throw std::runtime_error("upscale differs from released bilinear");
  }
  checked+=15360*8+384000*3;
 }
 alignas(32) static uint32_t source[32],dest[32],actual[32];for(auto&v:source)v=random();
 rix_pl::write_words(dest,source,32);rix_pl::read_words(dest,actual,32);
 if(memcmp(source,actual,sizeof(source)))throw std::runtime_error("paired copy changed data");
 bool rejected=false;try{rix_pl::write_words(dest+1,source,8);}catch(const std::exception&){rejected=true;}
 if(!rejected)throw std::runtime_error("unaligned device write accepted");
#ifdef __aarch64__
 for(int first=-3200;first<=3175;first+=8){
  int16_t n[8],q[8];for(int i=0;i<8;i++)n[i]=std::min(first+i,3175);
  vst1q_s16(q,rix_frames::rounded25(vld1q_s16(n)));
  for(unsigned i=0;i<8;i++)if(q[i]!=rix_frames::rounded<25>(n[i]))throw std::runtime_error("NEON divide differs from exact signed rounding");
 }
 std::cout<<"FRAME_NEON_EXACT_DIVIDE_PASS range=-3200:3175\n";
#endif
 alignas(32) static uint32_t snapshot[96000];std::vector<uint16_t> copied(96000);
 for(auto&v:snapshot)v=random();
 for(unsigned workers:{1u,2u,4u}){
  std::fill(copied.begin(),copied.end(),0x1234);rix_pl::copy_snapshot(snapshot,copied,resample.source_rows.data(),workers);
  for(unsigned y=0;y<240;y++)for(unsigned x=0;x<400;x++){
   auto p=snapshot[y*400+x];uint16_t expected=resample.source_rows[y]?uint16_t(((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&0x1f)):0x1234;
   if(copied[y*400+x]!=expected)throw std::runtime_error("parallel snapshot row partition mismatch");
  }
 }
 std::cout<<"FRAME_RESAMPLE_COMPATIBILITY_PASS patterns=14 values="<<checked<<" source_rows=192/240\n";
 std::cout<<"FRAME_PARALLEL_COPY_PASS workers=1,2,4\n";
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
