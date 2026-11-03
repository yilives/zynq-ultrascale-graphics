// SPDX-License-Identifier: MIT
#include "native_style400.hpp"
#include <chrono>
#include <iostream>
#include <random>
static void check(bool x,const char*s){if(!x)throw std::runtime_error(s);}
static int round64(int64_t n,int d){return n<0?-int((-n+d/2)/d):int((n+d/2)/d);}
static int sample(const rix_cnn::Frame&f,unsigned x,unsigned y,unsigned c){
 int sx=std::max(0,int(4*x)-3),sy=std::max(0,int(4*y)-3);unsigned x0=sx/10,y0=sy/10,x1=std::min(x0+1,159u),y1=std::min(y0+1,95u);int fx=sx%10,fy=sy%10;
 int64_t n=int64_t(f[y0*160+x0][c])*(10-fx)*(10-fy)+int64_t(f[y0*160+x1][c])*fx*(10-fy)
  +int64_t(f[y1*160+x0][c])*(10-fx)*fy+int64_t(f[y1*160+x1][c])*fx*fy;
 return round64(n,100)+128;
}
static void load(const std::string&p,void*data,size_t bytes){std::ifstream f(p,std::ios::binary);f.read(static_cast<char*>(data),bytes);check(bool(f)&&f.peek()==EOF,"fixture length");}
int main(int argc,char**argv){try{
 rix_frames::NativeStyle400 fusion;std::vector<uint16_t>source(96000);rix_cnn::Frame input(15360),styled(15360);std::vector<uint32_t> output(96000);
 if(argc==4){std::string p=argv[1];load(p+".source565.bin",source.data(),192000);load(p+".input.bin",input.data(),122880);load(p+".output.bin",styled.data(),122880);
  fusion.compose(source,input,styled,output,std::stoul(argv[2]));std::ofstream f(argv[3],std::ios::binary);f.write(reinterpret_cast<const char*>(output.data()),384000);check(bool(f),"output failed");std::cout<<"{\"passed\":true,\"pixels\":96000}\n";return 0;}
 check(argc==1,"usage: test-native400 [prefix gain output]");std::mt19937 rng(20261103);unsigned checks=0;
#ifdef __aarch64__
 for(int i=-12800;i<=12700;i+=8){int16_t v[8],out[8];for(int j=0;j<8;j++)v[j]=int16_t(std::min(i+j,12700));vst1q_s16(out,rix_frames::rounded100(vld1q_s16(v)));
  for(int j=0;j<8;j++){check(out[j]==round64(v[j],100),"round100 exact range");checks++;}}
#endif
 for(auto&p:source)p=uint16_t(rng());for(auto&p:input)for(auto&c:p)c=int8_t(rng());for(auto&p:styled)for(auto&c:p)c=int8_t(rng());
 for(unsigned gain:{0u,1u,192u,256u}){
  fusion.compose(source,input,styled,output,gain);
  for(unsigned i=0;i<20000;i++){
   unsigned x=i<400?i:rng()%400,y=i<400?(i%2?239:0):rng()%240;int n=0;const int weights[]={77,150,29};
   for(unsigned c=0;c<3;c++)n+=(rix_frames::channel565(source[y*400+x],c)+128-sample(input,x,y,c))*weights[c];
   int correction=round64(std::clamp(round64(n,256),-48,48)*int(gain),256);uint32_t pixel=0;
   for(unsigned c=0;c<3;c++)pixel|=uint32_t(std::clamp(sample(styled,x,y,c)+correction,0,255))<<(16-8*c);
   check(output[y*400+x]==pixel,"native400 direct oracle");checks++;
  }
 }
 fusion.compose(source,input,styled,output,192,{{0,0,3,2},{399,239,1,1}});
 for(auto xy: {std::pair<unsigned,unsigned>{0,0},{2,1},{399,239}}){unsigned x=xy.first,y=xy.second;uint32_t p=0;
  for(unsigned c=0;c<3;c++)p|=uint32_t(rix_frames::channel565(source[y*400+x],c)+128)<<(16-8*c);check(output[y*400+x]==p,"rectangle protection");checks++;}
 auto began=std::chrono::steady_clock::now();for(unsigned i=0;i<40;i++)fusion.compose(source,input,styled,output,192);
 double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-began).count()/40;
 std::cout<<"{\"passed\":true,\"checks\":"<<checks<<",\"ms_per_frame\":"<<ms<<"}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
