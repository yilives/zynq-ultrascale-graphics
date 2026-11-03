// SPDX-License-Identifier: MIT
#include "cnn_cpu.hpp"
#include "pl_frames.hpp"
#include "frame_resample.hpp"
#include "present_queue.hpp"
#include "mc_style_fusion.hpp"
#include "mc_snapshot_copy.hpp"
#include "frame_pipeline.hpp"
#include <cstdio>
#include <algorithm>
#include <cmath>
#include <iostream>
#include <memory>
#include <sys/file.h>
using rix_cnn::Frame;using rix_cnn::Model;
using rix_pl::Map;using rix_pl::Clock;
static void save(const std::string&p,const void*data,size_t n){std::ofstream f(p,std::ios::binary);f.write(static_cast<const char*>(data),n);if(!f)throw std::runtime_error("file write failed: "+p);}
struct Fd{int fd;Fd(const char*p,int flags):fd(open(p,flags,0600)){if(fd<0)throw std::runtime_error(std::string("open failed: ")+p);}~Fd(){close(fd);} };
static bool neural_device_tree(){
 std::ifstream f("/proc/device-tree/neural-style@a0030000/compatible",std::ios::binary);std::string v((std::istreambuf_iterator<char>(f)),{});
 return v==std::string("rasterix,cnn-int8-v1\0",21)||v==std::string("rasterix,cnn-int8-v2\0",21);
}
static bool scale5_device_tree(){
 std::ifstream f("/proc/device-tree/neural-style@a0030000/rasterix,neural-scale5x",std::ios::binary);unsigned char b[4]{};
 f.read(reinterpret_cast<char*>(b),4);return f&&b[0]==0&&b[1]==0&&b[2]==0&&b[3]==1;
}
class Hardware {
 Fd mem;Map regs;
 void status(unsigned mask){
  auto end=Clock::now()+std::chrono::seconds(5);
  // Finish an in-flight frame on SIGTERM; reset/restore at a frame boundary.
  // Hardware faults and deadlines still fail instead of reporting success.
  for(;;){auto v=regs.read(0xc);if(v&16)throw std::runtime_error("CNN hardware fault");if((v&mask)==mask)return;if(Clock::now()>end)throw std::runtime_error("CNN hardware timeout");}
 }
public:
 uint32_t cycles=0,expected_cycles=1843200,version=1,capabilities=0;
 explicit Hardware(const Model&m):mem("/dev/mem",O_RDWR|O_SYNC),regs(mem.fd,0xa0030000,65536){
  auto magic=regs.read(0);
  if((magic!=0x4e4e5331&&magic!=0x4e4e5332)||regs.read(4)!=((96u<<16)|160))throw std::runtime_error("NNS shape/capability mismatch");
  if(magic==0x4e4e5332){version=2;expected_cycles=regs.read(0x38);capabilities=regs.read(0x3c);
   if(expected_cycles!=414738||(capabilities&1)==0)throw std::runtime_error("NNS2 pipeline profile mismatch");}
  regs.write(8,2);regs.write(8,4);
  for(unsigned i=0;i<1776;i++){unsigned address=i<1728?i:(i<1752?2048+i-1728:2080+i-1752);regs.write(0x20,address);regs.write(0x24,m.words[i]);}
  regs.write(8,8);status(8);
 }
 ~Hardware(){regs.write(8,2);}
 Frame infer(const Frame&input){
  if(input.size()!=15360)throw std::runtime_error("PL backend requires 160x96");
  regs.write(8,1);status(2);
  auto*mmio=reinterpret_cast<volatile uint32_t*>(regs.p);
  // /dev/mem O_SYNC is Device memory on A53. Ordered, volatile accesses to
  // this one peripheral cannot be merged/reordered; drain once at phase
  // boundaries instead of a global DSB after each of 15,360 pixels. The AXI
  // slave accepts writes throughout LOAD and throttles the CPU via AW/W/B.
  for(auto&p:input){uint32_t rgb=uint8_t(int(p[0])+128)|(uint32_t(uint8_t(int(p[1])+128))<<8)|(uint32_t(uint8_t(int(p[2])+128))<<16);mmio[0x10/4]=rgb;}
  rix_pl::barrier();
  status(4);Frame result(15360);
  auto output_deadline=Clock::now()+std::chrono::seconds(5);
  for(auto&p:result){
   // Retain the per-pixel valid check: OUTREAD introduces a BRAM read cycle
   // after every pop, so blindly reading DATA again is not a valid protocol.
   for(;;){auto v=mmio[0xc/4];if(v&16)throw std::runtime_error("CNN output fault");if(v&4)break;
    if(Clock::now()>output_deadline)throw std::runtime_error("CNN output timeout");}
   uint32_t rgb=mmio[0x18/4];for(unsigned c=0;c<3;c++)p[c]=int((rgb>>(c*8))&255)-128;
  }
  rix_pl::barrier();
  auto end=Clock::now()+std::chrono::seconds(1);while(regs.read(0xc)&1){if(Clock::now()>end)throw std::runtime_error("CNN did not retire last pixel");}
  cycles=regs.read(0x28);
  if(regs.read(0x30)!=15360||regs.read(0x34)!=15360||cycles!=expected_cycles)throw std::runtime_error("CNN frame accounting mismatch");
  return result;
 }
};
int main(int argc,char**argv){try{
 std::string model,input,output,backend="cpu-int8",dump,present_mode="overlap",composition="neural",frame_pipeline="serial",snapshot_copy="paired";unsigned w=160,h=96,strength=128,snapshot_workers=4;bool live=false,dump_last=false,strength_set=false;double seconds=10,hold=0;
 std::vector<rix_frames::McStyleFusion::Rect> protected_rects;
 auto number=[](const std::string&s,unsigned max){
  if(s.empty()||s.find_first_not_of("0123456789")!=std::string::npos)throw std::runtime_error("invalid unsigned number");
  auto n=std::stoull(s);if(n>max)throw std::runtime_error("number outside range");return unsigned(n);
 };
 for(int i=1;i<argc;i++){std::string k=argv[i];auto value=[&](){if(++i==argc)throw std::runtime_error("missing argument");return std::string(argv[i]);};
  if(k=="--model")model=value();else if(k=="--input")input=value();else if(k=="--output")output=value();else if(k=="--backend")backend=value();
  else if(k=="--width")w=std::stoul(value());else if(k=="--height")h=std::stoul(value());else if(k=="--seconds")seconds=std::stod(value());
  else if(k=="--hold-last-seconds")hold=std::stod(value());else if(k=="--dump-prefix")dump=value();else if(k=="--live")live=true;
  else if(k=="--present-mode")present_mode=value();
  else if(k=="--frame-pipeline")frame_pipeline=value();
  else if(k=="--snapshot-copy")snapshot_copy=value();
  else if(k=="--snapshot-workers")snapshot_workers=number(value(),4);
  else if(k=="--composition")composition=value();
  else if(k=="--strength"){strength=number(value(),256);strength_set=true;}
  else if(k=="--dump-last")dump_last=true;
  else if(k=="--protect-rect"){
   auto s=value();unsigned v[4];size_t lo=0;
   for(unsigned j=0;j<4;j++){auto end=s.find(',',lo);if((j<3)==(end==std::string::npos))throw std::runtime_error("invalid protected rectangle fields");v[j]=number(s.substr(lo,end==std::string::npos?end:end-lo),400);lo=end+1;}
   unsigned x=v[0],y=v[1],rw=v[2],rh=v[3];
   if(!rw||!rh||x>=400||y>=240||rw>400-x||rh>240-y)throw std::runtime_error("invalid protected source rectangle");
   protected_rects.push_back({x,y,rw,rh});
  }
  else if(k=="--help"){std::cout<<"rix-neural-style --model oil.cnn|anime.cnn --backend cpu-int8|pl-int8 [--live --seconds 10 --hold-last-seconds 20 --dump-prefix /tmp/test --dump-last] [--composition neural|mc-residual --strength 0..256 --protect-rect x,y,w,h] | [--input HWC8.bin --output HWC8.bin --width 160 --height 96]\nBoth models are trained tiny students, not the full PC teachers. MC residual uses an owned full source copy, FPGA CNN and ARM detail fusion. Protected rectangles retain original pixels; they are not a native HUD layer.\n";return 0;}
  else throw std::runtime_error("unknown option: "+k);
 }
 if(backend!="cpu-int8"&&backend!="pl-int8")throw std::runtime_error("backend must be cpu-int8 or pl-int8");
 if(present_mode!="overlap"&&present_mode!="blocking")throw std::runtime_error("present-mode must be overlap or blocking");
 if(frame_pipeline!="serial"&&frame_pipeline!="overlap")throw std::runtime_error("frame-pipeline must be serial or overlap");
 if(snapshot_copy!="paired"&&snapshot_copy!="neon")throw std::runtime_error("snapshot-copy must be paired or neon");
 if(snapshot_workers!=1&&snapshot_workers!=2&&snapshot_workers!=4)throw std::runtime_error("snapshot-workers must be 1, 2 or 4");
 if(composition!="neural"&&composition!="mc-residual")throw std::runtime_error("composition must be neural or mc-residual");
 const bool mc_residual=composition=="mc-residual";
 if(strength>256||(!live&&(mc_residual||dump_last||!protected_rects.empty()))||(!mc_residual&&(strength_set||!protected_rects.empty())))throw std::runtime_error("invalid composition options");
 if(!w||!h||w>400||h>240||!std::isfinite(seconds)||seconds<=0||seconds>3600||!std::isfinite(hold)||hold<0||hold>120)throw std::runtime_error("invalid dimensions/duration");
 if((live||backend=="pl-int8")&&(w!=160||h!=96))throw std::runtime_error("live/PL requires 160x96");
 Model weights(model);
 // Mandatory DT capability guard, before mapping/probing a new PL address.
 if(backend=="pl-int8"){
  if(!neural_device_tree())throw std::runtime_error("NNS1/NNS2 device tree is absent; refusing to probe new FPGA registers");
 }
 std::unique_ptr<Fd> lock;
 if(live||backend=="pl-int8"){lock=std::make_unique<Fd>("/tmp/rix-superres.lock",O_CREAT|O_RDWR);if(flock(lock->fd,LOCK_EX|LOCK_NB))throw std::runtime_error("another postprocessor is running");}
 signal(SIGINT,rix_pl::stop);signal(SIGTERM,rix_pl::stop);
 std::unique_ptr<Hardware> hw;if(backend=="pl-int8")hw=std::make_unique<Hardware>(weights);
 auto inference=[&](const Frame&a){return hw?hw->infer(a):rix_cnn::infer(a,w,h,weights);};
 if(!live){
  Frame a(size_t(w)*h);std::ifstream f(input,std::ios::binary);f.read(reinterpret_cast<char*>(a.data()),a.size()*8);if(!f||f.peek()!=EOF)throw std::runtime_error("input must be exact signed HWC8 tensor");
  auto start=Clock::now();Frame b=inference(a);double elapsed=std::chrono::duration<double>(Clock::now()-start).count();save(output,b.data(),b.size()*8);
  std::cout<<"{\"backend\":\""<<backend<<"\",\"seconds\":"<<elapsed<<",\"cnn_cycles\":"<<(hw?hw->cycles:0)<<",\"engine_version\":"<<(hw?hw->version:0)<<"}\n";return 0;
 }
 if(access("/proc/device-tree/rasterix-frame-snapshot/rasterix,snapshot-version",F_OK))throw std::runtime_error("SNP1 device tree is required");
 Fd mem("/dev/mem",O_RDWR|O_SYNC);Map regs(mem.fd,0xa0010000,65536),pl(mem.fd,0xa1000000,0x1000000);
 if(regs.read(0x50)!=0x50535431||regs.read(0x74)!=0x534e5031||regs.read(0x88)!=0xa1400000||regs.read(0x90)!=384000)throw std::runtime_error("PST1/SNP1 layout mismatch");
 uint32_t saved=regs.read(0x54);
 bool pl_scale5=false;
 if(scale5_device_tree()&&neural_device_tree()){
  Map nn_cap(mem.fd,0xa0030000,65536);
  if(nn_cap.read(0)==0x4e4e5332)pl_scale5=(nn_cap.read(0x3c)&2)!=0;
 }
 if(mc_residual)pl_scale5=false; // Full-detail composition uses native 800x480 banks.
 struct Restore{Map&r;uint32_t value;~Restore(){r.write(0x54,value);}}restore{regs,saved};
 rix_frames::Resampler resample;
 rix_frames::McStyleFusion fusion;
 rix_pl::Snapshot snapshot(regs,pl);std::vector<uint16_t> source(96000),candidate_source(96000);Frame small(15360),styled(15360);
 rix_pl::PresentQueue<Map> presentation(regs,pl_scale5?3:2,present_mode=="overlap");
 std::vector<uint32_t> display(pl_scale5?15360:384000),diagnostic(pl_scale5&&!dump.empty()?384000:0);
 unsigned frames=0,retries=0,last_bank=0,last_source_frame=0;double copy=0,prepare=0,compute=0,present=0,scale=0,write=0,wait=0,read=0,prefetch=0,diagnostic_seconds=0;
 struct SourceRead{bool ready=false;uint32_t frame=0;double elapsed=0,wait=0,read=0,prefetch=0;};
 // Declared after every referenced buffer/map. Its destructor joins first on
 // all exception paths, before leases, CPU buffers or MMIO mappings disappear.
 rix_frames::FramePipeline<SourceRead> next_source;
 unsigned source_reads=0,discarded_sources=0;double foreground_wait=0;
 auto read_source=[&](){
  SourceRead result;auto began=Clock::now();snapshot.wait_seconds=0;snapshot.read_seconds=0;
  bool success=snapshot.read(candidate_source,mc_residual?nullptr:resample.source_rows.data(),snapshot_workers,
                             snapshot_copy=="neon"?rix_pl::copy_snapshot_neon:rix_pl::copy_snapshot);
  result.elapsed=std::chrono::duration<double>(Clock::now()-began).count();result.wait=snapshot.wait_seconds;result.read=snapshot.read_seconds;
  if(success){result.frame=snapshot.frame;began=Clock::now();result.ready=snapshot.request();result.prefetch=std::chrono::duration<double>(Clock::now()-began).count();}
  return result;
 };
 auto account_source=[&](const SourceRead&r){source_reads++;copy+=r.elapsed;wait+=r.wait;read+=r.read;prefetch+=r.prefetch;};
 auto dump_frame=[&](){
  auto began=Clock::now();
  save(dump+".input.bin",small.data(),small.size()*8);save(dump+".output.bin",styled.data(),styled.size()*8);
  if(mc_residual)save(dump+".source565.bin",source.data(),source.size()*2);
  if(pl_scale5){resample.upscale(styled,diagnostic);save(dump+".display.bin",diagnostic.data(),diagnostic.size()*4);save(dump+".native.bin",display.data(),display.size()*4);}
  else save(dump+".display.bin",display.data(),display.size()*4);
  std::ofstream meta(dump+".frame.json");meta<<"{\"source_frame\":"<<last_source_frame<<",\"composition\":\""<<composition<<"\",\"strength\":"<<strength<<",\"owned_source_copy\":true,\"paired_input_output\":true,\"protected_rectangles\":[";
  for(size_t i=0;i<protected_rects.size();i++){const auto&r=protected_rects[i];if(i)meta<<',';meta<<'['<<r.x<<','<<r.y<<','<<r.width<<','<<r.height<<']';}meta<<"]}\n";
  meta.close();if(!meta)throw std::runtime_error("frame metadata write failed");
  diagnostic_seconds+=std::chrono::duration<double>(Clock::now()-began).count();
 };
 auto start=Clock::now();
 while(!rix_pl::stopped()&&std::chrono::duration<double>(Clock::now()-start).count()<seconds){
  auto a=Clock::now();SourceRead incoming=next_source.pending()?next_source.take():read_source();
  foreground_wait+=std::chrono::duration<double>(Clock::now()-a).count();account_source(incoming);
  if(!incoming.ready){retries++;continue;}
  // Keep source/input/output/display paired even if SIGTERM interrupts the
  // next snapshot read or prefetch. Only a fully accepted candidate replaces it.
  source.swap(candidate_source);
  // The worker owns Snapshot and only the next CPU buffer. Main uses the
  // accepted frame ID returned by value, never Snapshot fields during a read.
  if(frame_pipeline=="overlap"&&!rix_pl::stopped())next_source.start(read_source);
  a=Clock::now();resample.downsample(source,small);prepare+=std::chrono::duration<double>(Clock::now()-a).count();
  a=Clock::now();styled=inference(small);compute+=std::chrono::duration<double>(Clock::now()-a).count();
  auto present_start=Clock::now();a=present_start;
  if(mc_residual)fusion.compose(source,small,styled,display,strength,protected_rects);
  else if(pl_scale5){for(unsigned i=0;i<15360;i++)display[i]=(uint32_t(int(styled[i][0])+128)<<16)|(uint32_t(int(styled[i][1])+128)<<8)|uint32_t(int(styled[i][2])+128);}
  else resample.upscale(styled,display);
  scale+=std::chrono::duration<double>(Clock::now()-a).count();
  unsigned bank=presentation.acquire();auto*dst=static_cast<char*>(pl.p)+bank*0x200000;
  a=Clock::now();rix_pl::write_words(dst,display.data(),display.size());write+=std::chrono::duration<double>(Clock::now()-a).count();
  // Neutral legacy color style: do not add poster/sepia to neural output.
  presentation.submit(bank);
  present+=std::chrono::duration<double>(Clock::now()-present_start).count();frames++;last_bank=bank;last_source_frame=incoming.frame;
  if(!dump.empty()&&!dump_last)dump_frame();
  if(frames==1||frames%30==0)std::cout<<"NEURAL_FRAME "<<frames<<" source="<<last_source_frame<<" cycles="<<(hw?hw->cycles:0)<<std::endl;
 }
 if(next_source.pending()){account_source(next_source.take());discarded_sources++;}
 snapshot.release(); // Never hold the prefetched lease during QA/hold-last.
 if(!dump.empty()&&dump_last&&frames)dump_frame();
 // Count the final frame only after scanout acknowledges it, including on
 // SIGTERM or the duration boundary. The hold/readback path sees that frame.
 auto final_wait=Clock::now();presentation.finish();present+=std::chrono::duration<double>(Clock::now()-final_wait).count();
 if(presentation.submitted()!=frames||presentation.completed()!=frames)throw std::runtime_error("display frame accounting mismatch");
 double flip=presentation.wait_seconds();
 double elapsed=std::chrono::duration<double>(Clock::now()-start).count();
 std::cout<<"{\"backend\":\""<<backend<<"\",\"processed_frames\":"<<frames<<",\"processed_fps\":"<<frames/elapsed<<",\"elapsed_seconds\":"<<elapsed
 <<",\"snapshot_seconds\":"<<copy<<",\"snapshot_wait_seconds\":"<<wait<<",\"snapshot_read_seconds\":"<<read<<",\"prefetch_seconds\":"<<prefetch
 <<",\"prepare_seconds\":"<<prepare<<",\"inference_seconds\":"<<compute<<",\"present_seconds\":"<<present<<",\"scale_seconds\":"<<scale<<",\"write_seconds\":"<<write<<",\"flip_seconds\":"<<flip
 <<",\"snapshot_bytes_per_frame\":"<<(mc_residual?384000:307200)<<",\"snapshot_read_workers\":"<<snapshot_workers<<",\"snapshot_prefetch\":true,\"snapshot_retries\":"<<retries
 <<",\"last_source_frame\":"<<last_source_frame<<",\"engine_version\":"<<(hw?hw->version:0)<<",\"cnn_cycles_per_frame\":"<<(hw?hw->cycles:0)
 <<",\"display_backend\":\""<<(mc_residual?"arm-mc-residual-nearest2x":(pl_scale5?"pl-bilinear-5x":"arm-bilinear-5x"))<<"\",\"display_write_bytes\":"<<display.size()*4
 <<",\"composition\":\""<<composition<<"\",\"strength\":"<<strength<<",\"owned_source_copy\":true,\"diagnostic_seconds\":"<<diagnostic_seconds
 <<",\"frame_pipeline\":\""<<frame_pipeline<<"\",\"snapshot_copy\":\""<<snapshot_copy<<"\",\"snapshot_read_attempts\":"<<source_reads<<",\"unused_prefetched_sources\":"<<discarded_sources
 <<",\"foreground_snapshot_wait_seconds\":"<<foreground_wait<<",\"phase_times_overlap\":"<<(frame_pipeline=="overlap"?"true":"false")
 <<",\"present_mode\":\""<<present_mode<<"\",\"present_submitted_frames\":"<<presentation.submitted()<<",\"present_completed_frames\":"<<presentation.completed()<<"}"<<std::endl;
 std::cout<<"NEURAL_PRESENTATION mode="<<present_mode<<" submitted="<<presentation.submitted()<<" completed="<<presentation.completed()<<std::endl;
 if(!frames)throw std::runtime_error("no neural frames processed");
 if(!dump.empty()){
  std::vector<uint32_t> actual(display.size());rix_pl::read_words(static_cast<char*>(pl.p)+last_bank*0x200000,actual.data(),actual.size());rix_pl::barrier();
  if(actual!=display)throw std::runtime_error("PL display full-frame readback mismatch");
  std::cout<<"NEURAL_DISPLAY_READBACK_PASS bytes="<<display.size()*4<<std::endl;
 }
 if(hold){std::cout<<"NEURAL_OUTPUT_HELD "<<hold<<std::endl;auto until=Clock::now()+std::chrono::duration<double>(hold);while(!rix_pl::stopped()&&Clock::now()<until)usleep(1000);}
 return 0;
 }catch(const std::exception&e){std::cerr<<"rix-neural-style: "<<e.what()<<'\n';return 1;}}
