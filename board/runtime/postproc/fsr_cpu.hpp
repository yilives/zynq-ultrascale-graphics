// SPDX-License-Identifier: MIT
#pragma once
#include "fsr_cpu_types.hpp"
#include <vector>
#include <thread>
#include <atomic>
#include <stdexcept>
namespace fsr_cpu {
inline const std::vector<AF3>*source;
inline const std::vector<AF3>*easu;
inline float fsr_source(int x,int y,int channel){
 const AF3 p=(*source)[std::clamp(y,0,239)*400+std::clamp(x,0,399)];
 return channel==0?p.x:channel==1?p.y:p.z;
}
inline AF4 FsrRcasLoadF(ASU2 p){AF3 c=(*easu)[std::clamp(p.y,0,479)*800+std::clamp(p.x,0,799)];return AF4(c.x,c.y,c.z,1);}
inline void FsrRcasInputF(float&,float&,float&){}
#include "fsr1_cpu_generated.hpp"
template<class F> void rows(F f){
 std::thread workers[4];for(int t=0;t<4;t++)workers[t]=std::thread([=]{for(int y=t;y<480;y+=4)f(y);});
 for(auto&t:workers)t.join();
}
inline std::vector<uint32_t> upscale(const std::vector<uint16_t>&input,int mode){
 std::vector<AF3> lr(96000),hr(384000);std::vector<uint32_t>output(384000);
 for(int i=0;i<96000;i++){uint16_t p=input[i];lr[i]=AF3(((p>>11)&31)/31.f,((p>>5)&63)/63.f,(p&31)/31.f);}
 source=&lr;easu=&hr;
 if(mode==2)rows([&](int y){for(int x=0;x<800;x++)FsrEasuF(hr[y*800+x],x,y);});
 else rows([&](int y){for(int x=0;x<800;x++){
  if(mode==0)hr[y*800+x]=lr[(y/2)*400+x/2];
  else {float sx=(x+.5f)*.5f-.5f,sy=(y+.5f)*.5f-.5f;int bx=floorf(sx),by=floorf(sy);float u=sx-bx,v=sy-by;
   auto at=[&](int xx,int yy){return lr[std::clamp(yy,0,239)*400+std::clamp(xx,0,399)];};
   hr[y*800+x]=at(bx,by)*((1-u)*(1-v))+at(bx+1,by)*(u*(1-v))+at(bx,by+1)*((1-u)*v)+at(bx+1,by+1)*(u*v);
  }
 }});
 AU4 con;con.x=AU1_AF1(exp2f(-0.2f));
 std::atomic<unsigned> invalid{0};
 rows([&](int y){for(int x=0;x<800;x++){
  AF3 p=hr[y*800+x];if(mode==2)FsrRcasF(p.x,p.y,p.z,I2(x,y),con);
  auto q=[&](float c){if(!std::isfinite(c)){invalid++;c=0;}return unsigned(std::clamp(c,0.f,1.f)*255.f+.5f);};
  output[y*800+x]=(q(p.x)<<16)|(q(p.y)<<8)|q(p.z);
 }});
 if(invalid)throw std::runtime_error("Non-finite FSR output");
 return output;
}
}
