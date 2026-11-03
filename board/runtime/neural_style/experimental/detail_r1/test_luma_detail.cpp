// SPDX-License-Identifier: MIT
#include "luma_detail.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <random>

static void require(bool value,const char*message){if(!value)throw std::runtime_error(message);}
static int round64(int64_t n,int64_t denominator){return int(n<0?-((-n+denominator/2)/denominator):(n+denominator/2)/denominator);}
// Direct four-tap rational interpolation is independent of the separable,
// factored five-pixel schedule and the A53 NEON implementation.
static int interpolate(const rix_cnn::Frame&frame,unsigned x,unsigned y,unsigned c){
 unsigned xx=x<2?0:x-2,yy=y<2?0:y-2,x0=xx/5,y0=yy/5;
 unsigned x1=std::min(x0+1,159u),y1=std::min(y0+1,95u),fx=xx%5,fy=yy%5;
 int64_t n=int64_t(frame[y0*160+x0][c])*(5-fx)*(5-fy)+int64_t(frame[y0*160+x1][c])*fx*(5-fy)
          +int64_t(frame[y1*160+x0][c])*(5-fx)*fy+int64_t(frame[y1*160+x1][c])*fx*fy;
 return round64(n,25)+128;
}
static uint32_t oracle(const std::vector<uint16_t>&source,const rix_cnn::Frame&input,
 const rix_cnn::Frame&styled,unsigned x,unsigned y,unsigned gain){
 int64_t n=0;const int coefficients[3]={77,150,29};
 for(unsigned c=0;c<3;c++)n+=int64_t(rix_frames::channel565(source[(y/2)*400+x/2],c)+128-interpolate(input,x,y,c))*coefficients[c];
 int correction=round64(int64_t(std::clamp(round64(n,256),-48,48))*gain,256);uint32_t result=0;
 for(unsigned c=0;c<3;c++)result|=uint32_t(std::clamp(interpolate(styled,x,y,c)+correction,0,255))<<(16-8*c);
 return result;
}
static void load(const std::string&path,void*data,size_t bytes){
 std::ifstream file(path,std::ios::binary);file.read(static_cast<char*>(data),bytes);require(bool(file)&&file.peek()==EOF,"invalid fixture size");
}
int main(int argc,char**argv){try{
 rix_frames::LumaDetailFusion fusion;std::vector<uint16_t> source(96000);
 rix_cnn::Frame input(15360),styled(15360);std::vector<uint32_t> display(384000);
 if(argc==4){
  std::string prefix=argv[1];unsigned gain=std::stoul(argv[2]);
  load(prefix+".source565.bin",source.data(),source.size()*2);load(prefix+".input.bin",input.data(),input.size()*8);load(prefix+".output.bin",styled.data(),styled.size()*8);
  fusion.compose(source,input,styled,display,gain);
  std::ofstream out(argv[3],std::ios::binary);out.write(reinterpret_cast<const char*>(display.data()),display.size()*4);require(bool(out),"output write failed");
  std::cout<<"{\"passed\":true,\"fixture_pixels\":384000}\n";return 0;
 }
 require(argc==1,"usage: test-luma-detail [fixture-prefix gain output.bin]");
 std::mt19937 rng(20261102);unsigned checks=0;
 for(auto&pixel:source)pixel=uint16_t(rng());
 for(auto&pixel:input)for(auto&c:pixel)c=int8_t(rng());
 for(auto&pixel:styled)for(auto&c:pixel)c=int8_t(rng());
 const std::vector<rix_frames::McStyleRect> rectangles={{0,0,19,3},{399,239,1,1},{12,2,31,5}};
 for(unsigned gain:{0u,1u,64u,192u,256u}){
  fusion.compose(source,input,styled,display,gain);
  for(unsigned i=0;i<25000;i++){
   unsigned x=i<800?i:rng()%800,y=i<800?(i%2?479:0):rng()%480;
   require(display[y*800+x]==oracle(source,input,styled,x,y,gain),"direct interpolation/detail oracle");checks++;
  }
  fusion.compose(source,input,styled,display,gain,rectangles);
  for(const auto&r:rectangles)for(unsigned y=2*r.y;y<2*(r.y+r.height);y++)for(unsigned x=2*r.x;x<2*(r.x+r.width);x++){
   auto pixel=source[(y/2)*400+x/2];uint32_t expected=0;
   for(unsigned c=0;c<3;c++)expected|=uint32_t(rix_frames::channel565(pixel,c)+128)<<(16-8*c);
   require(display[y*800+x]==expected,"explicit rectangle protection");checks++;
  }
 }
 auto rejects=[&](auto callback){bool rejected=false;try{callback();}catch(const std::runtime_error&){rejected=true;}require(rejected,"invalid argument accepted");checks++;};
 rejects([&]{fusion.compose(source,input,styled,display,257);});
 rejects([&]{fusion.compose(source,input,styled,display,192,{{399,239,2,1}});});
 rejects([&]{std::vector<uint16_t> short_source(95999);fusion.compose(short_source,input,styled,display);});
 rejects([&]{rix_cnn::Frame short_input(15359);fusion.compose(source,short_input,styled,display);});
 auto began=std::chrono::steady_clock::now();uint64_t checksum=0;
 for(unsigned i=0;i<40;i++){fusion.compose(source,input,styled,display,192);checksum+=display[i];}
 double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-began).count()/40;
 std::cout<<"{\"passed\":true,\"checks\":"<<checks<<",\"ms_per_frame\":"<<ms<<",\"checksum\":"<<checksum<<",\"scope\":\"unit-process-only\"}\n";
 return 0;
}catch(const std::exception&error){std::cerr<<error.what()<<'\n';return 1;}}
