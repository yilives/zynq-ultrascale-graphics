// SPDX-License-Identifier: MIT
#include "mc_style_fusion.hpp"
#include <chrono>
#include <iostream>
#include <random>

static void require(bool value,const char*message){if(!value)throw std::runtime_error(message);}
static int colour(uint16_t p,unsigned c){return rix_frames::channel565(p,c)+128;}
static uint32_t base(uint16_t p){return (colour(p,0)<<16)|(colour(p,1)<<8)|colour(p,2);}
static int rounded64(int64_t n,int64_t den){return int(n<0?-((-n+den/2)/den):(n+den/2)/den);}
static unsigned edge(const std::vector<uint16_t>&s,unsigned x,unsigned y){
 unsigned d=0;const auto p=s[y*400+x];
 for(unsigned c=0;c<3;c++)for(int axis=0;axis<4;axis++){
  int xx=int(x)+(axis==0)-(axis==1),yy=int(y)+(axis==2)-(axis==3);
  if(xx>=0&&xx<400&&yy>=0&&yy<240)d=std::max(d,unsigned(std::abs(colour(p,c)-colour(s[yy*400+xx],c))));
 }
 return d<=8?256:(d>=64?0:(64-d)*256/56);
}
static uint32_t oracle(const std::vector<uint16_t>&source,const rix_cnn::Frame&a,
 const rix_cnn::Frame&b,unsigned x,unsigned y,unsigned strength){
 int nx=std::max(0,int(x)-2),ny=std::max(0,int(y)-2);
 unsigned x0=nx/5,x1=std::min(x0+1,159u),y0=ny/5,y1=std::min(y0+1,95u);
 int fx=nx%5,fy=ny%5;uint32_t result=0;
 for(unsigned c=0;c<3;c++){
  auto delta=[&](unsigned xx,unsigned yy){return int(b[yy*160+xx][c])-int(a[yy*160+xx][c]);};
  int64_t correction=(5-fy)*((5-fx)*delta(x0,y0)+fx*delta(x1,y0))+fy*((5-fx)*delta(x0,y1)+fx*delta(x1,y1));
  correction*=int64_t(strength)*edge(source,x/2,y/2);
  int value=std::clamp(colour(source[(y/2)*400+x/2],c)+rounded64(correction,25*256*256),0,255);
  result|=uint32_t(value)<<(16-8*c);
 }
 return result;
}
int main(int argc,char**argv){try{
 rix_frames::McStyleFusion fusion;
 std::vector<uint16_t> source(96000);rix_cnn::Frame input(15360),styled(15360);
 std::vector<uint32_t> display(384000);std::mt19937 rng(1764);unsigned checks=0;
#ifdef __aarch64__
 // Exercise every rounding transition and random full-range signed
 // numerators directly, independently of image interpolation coefficients.
#ifdef RIX_MC_FUSION_FACTORED_NEON
 for(unsigned i=0;i<20000;i++) {
  int32_t values[4],actual[4];
  for(unsigned lane=0;lane<4;lane++) {
   int64_t magnitude=i<256*5?(i/5)*1638400LL+819200+int(i%5)-2:rng()%417792001;
   magnitude=std::min(magnitude,int64_t(417792000));
   values[lane]=int32_t((lane&1)?-magnitude:magnitude);
  }
  vst1q_s32(actual,rix_frames::mc_style_detail::rounded_correction4(vld1q_s32(values)));
  for(unsigned lane=0;lane<4;lane++){require(actual[lane]==rounded64(values[lane],1638400),"NEON signed division oracle");checks++;}
 }
 for(unsigned i=0;i<20000;i++) {
  int32_t values[8];int16_t signs[8],actual[8];
  for(unsigned lane=0;lane<8;lane++) {
   int64_t magnitude=i<256*5?(i/5)*1638400LL+819200+int(i%5)-2:rng()%417792001;
   magnitude=std::min(magnitude,int64_t(417792000));
   values[lane]=int32_t((lane&1)?-magnitude:magnitude);signs[lane]=values[lane]<0?-1:0;
  }
  vst1q_s16(actual,rix_frames::mc_style_detail::rounded_correction8(vld1q_s32(values),vld1q_s32(values+4),vld1q_s16(signs)));
  for(unsigned lane=0;lane<8;lane++){require(actual[lane]==rounded64(values[lane],1638400),"NEON factored signed division oracle");checks++;}
 }
#endif
#endif
 for(auto&p:source)p=uint16_t(rng());
 for(auto&p:input)for(auto&c:p)c=int8_t(rng());
 styled=input;
 fusion.compose(source,input,styled,display,128);
 for(unsigned y=0;y<480;y++)for(unsigned x=0;x<800;x++){require(display[y*800+x]==base(source[(y/2)*400+x/2]),"zero residual identity");checks++;}
 for(auto&p:styled)for(auto&c:p)c=int8_t(rng());
 fusion.compose(source,input,styled,display,0);
 for(unsigned y=0;y<480;y++)for(unsigned x=0;x<800;x++){require(display[y*800+x]==base(source[(y/2)*400+x/2]),"zero strength identity");checks++;}
 // Smooth RGB565 ramps exercise non-zero fractional edge weights, positive
 // and negative 9-bit residuals, signed rounding and border interpolation.
 for(unsigned y=0;y<240;y++)for(unsigned x=0;x<400;x++)source[y*400+x]=uint16_t((((x/2)%32)<<11)|(((y/2)%64)<<5)|((x+y)%32));
 for(unsigned strength: {1u,73u,128u,256u}){
  fusion.compose(source,input,styled,display,strength);
  for(unsigned i=0;i<10000;i++){unsigned x=rng()%800,y=rng()%480;require(display[y*800+x]==oracle(source,input,styled,x,y,strength),"independent residual oracle");checks++;}
 }
 const std::vector<std::vector<rix_frames::McStyleFusion::Rect>> masks={
  {{0,0,400,34},{0,192,400,48},{194,114,12,12}},
  {{0,0,400,240}},
  {{0,0,400,1},{0,239,400,1},{0,117,399,1},{399,117,1,1}},
  {{0,29,400,3},{0,30,400,4},{2,42,3,117}}
 };
 for(const auto&mask:masks)for(unsigned strength:{1u,128u,256u}) {
  fusion.compose(source,input,styled,display,strength,mask);
  for(unsigned i=0;i<4000;i++) {
   unsigned x=rng()%800,y=rng()%480;bool protected_pixel=false;
   for(const auto&r:mask)protected_pixel|=x/2>=r.x&&x/2<r.x+r.width&&y/2>=r.y&&y/2<r.y+r.height;
   uint32_t expected=protected_pixel?base(source[(y/2)*400+x/2]):oracle(source,input,styled,x,y,strength);
   require(display[y*800+x]==expected,"protected-row sparse fusion oracle");checks++;
  }
 }
 std::fill(source.begin(),source.end(),0x8410);
 for(auto&p:input)p.fill(-128);
 for(auto&p:styled)p.fill(127);
 fusion.compose(source,input,styled,display,256,{{10,20,30,40}});
 require(display[0]==0xffffff,"positive saturation");checks++;
 for(unsigned y=40;y<120;y++)for(unsigned x=20;x<80;x++){require(display[y*800+x]==base(0x8410),"protected rectangle exact identity");checks++;}
 require(display[40*800+19]==0xffffff&&display[40*800+80]==0xffffff,"rectangle boundary");checks++;
 for(auto&p:input)p.fill(127);
 for(auto&p:styled)p.fill(-128);
 fusion.compose(source,input,styled,display,256);require(display[0]==0,"negative saturation");checks++;
 for(unsigned y=0;y<240;y++)for(unsigned x=0;x<400;x++)source[y*400+x]=x<200?0x2104:0xdefb;
 for(auto&p:input)p.fill(0);
 for(auto&p:styled)p.fill(32);
 fusion.compose(source,input,styled,display,256);
 for(unsigned y=0;y<480;y++)for(unsigned x=398;x<402;x++){require(display[y*800+x]==base(source[(y/2)*400+x/2]),"high contrast edge exact protection");checks++;}
 require(display[100*800+200]!=base(source[50*400+100]),"flat surface must retain style correction");checks++;
 auto rejects=[&](auto run){bool rejected=false;try{run();}catch(const std::runtime_error&){rejected=true;}require(rejected,"invalid parameters must reject");checks++;};
 rejects([&]{fusion.compose(source,input,styled,display,257);});
 rejects([&]{fusion.compose(source,input,styled,display,128,{{399,0,2,1}});});
 rejects([&]{fusion.compose(source,input,styled,display,128,{{0,0,0,1}});});
 rejects([&]{std::vector<uint16_t>short_source(95999);fusion.compose(short_source,input,styled,display);});
 rejects([&]{rix_cnn::Frame short_frame(15359);fusion.compose(source,short_frame,styled,display);});
 rejects([&]{std::vector<uint32_t>short_display(383999);fusion.compose(source,input,styled,short_display);});
 std::vector<rix_frames::McStyleFusion::Rect> benchmark_mask;
 if(argc==2) {
  std::string prefix=argv[1];
  auto load=[&](const std::string&path,void*dst,size_t bytes){
   std::ifstream f(path,std::ios::binary);f.read(static_cast<char*>(dst),bytes);
   require(bool(f)&&f.peek()==EOF,"benchmark fixture length");
  };
  load(prefix+".source565.bin",source.data(),source.size()*sizeof(source[0]));
  load(prefix+".input.bin",input.data(),input.size()*sizeof(input[0]));
  load(prefix+".output.bin",styled.data(),styled.size()*sizeof(styled[0]));
  benchmark_mask={{0,0,400,34},{0,192,400,48},{194,114,12,12}};
 }
 auto start=std::chrono::steady_clock::now();uint64_t checksum=0;
 for(unsigned i=0;i<40;i++){fusion.compose(source,input,styled,display,128,benchmark_mask);checksum+=display[i];}
 double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count()/40;
 std::cout<<"{\"passed\":true,\"checks\":"<<checks<<",\"host_ms_per_frame\":"<<ms<<",\"checksum\":"<<checksum<<",\"fixture\":\""<<(argc==2?"captured-mc-default-mask":"synthetic-plane-no-mask")<<"\",\"performance_scope\":\"unit-test-process-only-not-live-game\",\"implementation\":\""
#ifdef __aarch64__
 <<"aarch64-neon"
#else
 <<"scalar"
#endif
 <<"\"}\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
