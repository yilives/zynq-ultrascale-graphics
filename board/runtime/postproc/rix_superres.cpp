// SPDX-License-Identifier: MIT
#include "fsr_cpu.hpp"
#include <chrono>
#include <csignal>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <unistd.h>
using Clock=std::chrono::steady_clock;
static volatile sig_atomic_t stopping=0;
static void stop(int){stopping=1;}
static void barrier(){
#ifdef __aarch64__
 asm volatile("dsb sy":::"memory");
#else
 __sync_synchronize();
#endif
}
struct Map {
 void* p;size_t size;
 Map(int fd,uint64_t base,size_t bytes):size(bytes){p=mmap(nullptr,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,base);if(p==MAP_FAILED)throw std::runtime_error("mmap failed");}
 ~Map(){munmap(p,size);}
 uint32_t read(unsigned offset)const{barrier();return *(volatile uint32_t*)((char*)p+offset);}
 void write(unsigned offset,uint32_t value){*(volatile uint32_t*)((char*)p+offset)=value;barrier();}
};
static void write_file(const std::string&path,const void*p,size_t bytes){std::ofstream f(path,std::ios::binary);f.write((const char*)p,bytes);if(!f)throw std::runtime_error("output write failed");}
static uint16_t pack565(uint32_t p){return ((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&0x1f);}
struct Snapshot {
 Map&r;Map&pl;uint32_t token=0,frame=0;double copy_seconds=0;
 Snapshot(Map&regs,Map&memory):r(regs),pl(memory){}
 bool owned()const{return token&&r.read(0x80)==token&&(r.read(0x7c)&3)==3;}
 void release(){
  if(token&&r.read(0x80)==token&&(r.read(0x7c)&3))r.write(0x80,token);
  token=0;
 }
 ~Snapshot(){release();}
 bool read(std::vector<uint16_t>&in,unsigned hold_ms=0){
  // An abandoned lease expires in hardware. Never steal a previous process's
  // token: its in-flight AXI writes may still be draining.
  auto deadline=Clock::now()+std::chrono::seconds(3);
  while(r.read(0x7c)&3){if(stopping)return false;if(Clock::now()>deadline)throw std::runtime_error("snapshot remains busy after watchdog");usleep(1000);}
  token=r.read(0x80)+1;if(!token)token=1;r.write(0x78,token);
  while(!owned()){
   if(stopping){release();return false;}
   if(r.read(0x80)==token&&(r.read(0x7c)&3)==0){release();return false;}
   if(Clock::now()>deadline)throw std::runtime_error("snapshot acquisition timeout");usleep(1000);
  }
  frame=r.read(0x84);auto started=Clock::now();
  auto copy=[&](std::vector<uint16_t>&v){
#ifdef __aarch64__
   // Measured on A53 Device memory: paired 128-bit LDP is much faster than
   // individual 64-bit LDR or a four-register LD1. Every Device read is
   // 32-byte aligned and stays inside the snapshot and a 4 KiB page.
   alignas(16) uint32_t words[8];
   for(int i=0;i<96000;i+=8){
    const char*src=(const char*)pl.p+0x400000+i*4;
    asm volatile("ldp q0, q1, [%0]\n\tstp q0, q1, [%1]"::"r"(src),"r"(words):"v0","v1","memory");
    for(int j=0;j<8;j++)v[i+j]=pack565(words[j]);
   }
#else
   volatile uint64_t*src=(volatile uint64_t*)((char*)pl.p+0x400000);
   for(int i=0;i<48000;i++){
    uint64_t pair=src[i];
    for(int j=0;j<2;j++)v[i*2+j]=pack565(pair>>(j*32));
   }
#endif
   barrier();
  };
  copy(in);copy_seconds=std::chrono::duration<double>(Clock::now()-started).count();
  if(hold_ms){
   auto until=Clock::now()+std::chrono::milliseconds(hold_ms);
   while(!stopping&&Clock::now()<until){if(!owned())throw std::runtime_error("snapshot lease expired during hold");usleep(1000);}
   std::vector<uint16_t> verify(96000);copy(verify);
   if(in!=verify)throw std::runtime_error("leased snapshot changed while game continued");
  }
  // Check after the complete read too: a preempted CPU must discard a lease
  // that expired during the copy. Release before the expensive FSR compute.
  if(!owned()){release();return false;}release();return !stopping;
 }
};
static int mode_id(const std::string&s){if(s=="nearest")return 0;if(s=="bilinear")return 1;if(s=="fsr1")return 2;if(s=="arm-asr")throw std::runtime_error("Arm ASR rendering backend unavailable: shader execution, motion vectors, 32-bit depth export and camera jitter integration are required; run rix-arm-asr-probe for the actual API check");throw std::runtime_error("mode must be nearest, bilinear or fsr1");}
static void selftest(){
 for(uint16_t color:{uint16_t(0),uint16_t(0xffff),uint16_t(0xf800),uint16_t(0x07e0),uint16_t(0x001f),uint16_t(0x8410)}){
  std::vector<uint16_t> in(96000,color);auto out=fsr_cpu::upscale(in,2);auto expected=fsr_cpu::upscale(in,0)[0];
  for(auto p:out)for(int shift:{0,8,16})if(std::abs(int((p>>shift)&255)-int((expected>>shift)&255))>2)throw std::runtime_error("FSR uniform-image preservation failed");
 }
 std::vector<uint16_t> edges(96000);for(int y=0;y<240;y++)for(int x=0;x<400;x++)edges[y*400+x]=((x+y)%23<11)?0xffff:0;
 auto a=fsr_cpu::upscale(edges,0),b=fsr_cpu::upscale(edges,1),c=fsr_cpu::upscale(edges,2);
 if(a==c||b==c)throw std::runtime_error("FSR edge image unexpectedly identical to simple scaler");
 std::cout<<"PASS FSR1 uniform colors, clamped boundaries, distinct edge response\n";
}
int main(int argc,char**argv){try{
 std::string input,output,mode="fsr1",capture,plmode,snapshot,source_output;double seconds=10,hold_last_seconds=0;bool live=false,test=false,status=false;int style=-1;unsigned hold_ms=0;
 for(int i=1;i<argc;i++){std::string k=argv[i];auto value=[&](){if(++i==argc)throw std::runtime_error("missing argument");return std::string(argv[i]);};
  if(k=="--input")input=value();else if(k=="--output")output=value();else if(k=="--mode")mode=value();else if(k=="--seconds")seconds=std::stod(value());
  else if(k=="--live")live=true;else if(k=="--selftest")test=true;else if(k=="--style")style=std::stoi(value());else if(k=="--capture")capture=value();else if(k=="--pl-mode")plmode=value();else if(k=="--status")status=true;
  else if(k=="--snapshot")snapshot=value();else if(k=="--snapshot-hold-ms")hold_ms=std::stoul(value());else if(k=="--source-output")source_output=value();else if(k=="--hold-last-seconds")hold_last_seconds=std::stod(value());else throw std::runtime_error("unknown option "+k);
 }
 if(test){selftest();return 0;}int id=mode_id(mode);
 if(!live&&capture.empty()&&plmode.empty()&&snapshot.empty()&&!status){
  std::vector<uint16_t> in(96000);std::ifstream f(input,std::ios::binary);f.read((char*)in.data(),192000);if(!f||f.peek()!=EOF)throw std::runtime_error("input must be exactly 400x240 RGB565 little endian");
  auto start=Clock::now();auto out=fsr_cpu::upscale(in,id);double elapsed=std::chrono::duration<double>(Clock::now()-start).count();write_file(output,out.data(),1536000);
  std::cout<<"{\"algorithm\":\""<<mode<<"\",\"backend\":\"CPU FP32 4 threads\",\"seconds\":"<<elapsed<<",\"fps\":"<<1/elapsed<<"}\n";return 0;
 }
 if(style < -1||style>3||seconds<=0||seconds>3600||hold_ms>5000||hold_last_seconds<0||hold_last_seconds>120)throw std::runtime_error("invalid style or duration");
 if(access("/proc/device-tree/touch-gpio@a0020000",F_OK))throw std::runtime_error("experimental postproc/touch device tree is required before accessing new registers");
 int mem=open("/dev/mem",O_RDWR|O_SYNC);if(mem<0)throw std::runtime_error("open /dev/mem failed (root required)");Map regs(mem,0xa0010000,65536);
 if(regs.read(0x50)!=0x50535431)throw std::runtime_error("PST1 hardware is required; refusing writes to baseline hardware");
 bool snapshot_hw=access("/proc/device-tree/rasterix-frame-snapshot/rasterix,snapshot-version",F_OK)==0;
 if(snapshot_hw&&(regs.read(0x74)!=0x534e5031||regs.read(0x88)!=0xa1400000||regs.read(0x90)!=384000))throw std::runtime_error("SNP1 hardware/memory layout mismatch");
 if(status){std::cout<<"{\"capability\":\"PST1\",\"requested\":"<<regs.read(0x54)<<",\"active\":"<<regs.read(0x58)<<",\"last_source\":"<<regs.read(0x5c)<<",\"leased_snapshot\":"<<(snapshot_hw?"true":"false");if(snapshot_hw)std::cout<<",\"snapshot_status\":"<<regs.read(0x7c)<<",\"snapshot_token\":"<<regs.read(0x80)<<",\"snapshot_frame\":"<<regs.read(0x84)<<",\"snapshot_expirations\":"<<regs.read(0x8c);std::cout<<"}\n";return 0;}
 int lock=-1;
 if(live||!plmode.empty()||!snapshot.empty()){
  lock=open("/tmp/rix-superres.lock",O_CREAT|O_RDWR,0600);
  if(lock<0||flock(lock,LOCK_EX|LOCK_NB))throw std::runtime_error("another postprocessor is running; stop it before changing display mode");
 }
 if(!plmode.empty()){
  int scale=mode_id(plmode);if(scale==2)throw std::runtime_error("PL supports nearest/bilinear; use --live --mode fsr1 for CPU FSR1");
  uint32_t word=scale|(regs.read(0x54)&0x130);if(style>=0)word=(word&~0x30u)|(style<<4);regs.write(0x54,word);
  auto deadline=Clock::now()+std::chrono::seconds(2);while(regs.read(0x58)!=word){if(Clock::now()>deadline)throw std::runtime_error("PL configuration timeout");usleep(1000);}
  std::cout<<"PL_POSTPROCESS_ACTIVE "<<word<<'\n';return 0;
 }
 if(!capture.empty()){
  uint32_t before=regs.read(0x64)&1;if((regs.read(0x68)&1)!=before)throw std::runtime_error("capture already busy");regs.write(0x64,1);auto deadline=Clock::now()+std::chrono::seconds(2);
  while((regs.read(0x68)&1)==before){if(Clock::now()>deadline)throw std::runtime_error("LCD capture timeout");usleep(1000);}
  std::vector<uint16_t> image(6000);for(int i=0;i<6000;i++){regs.write(0x6c,i);image[i]=regs.read(0x70);}
  write_file(capture,image.data(),image.size()*2);std::cout<<"LCD_CAPTURE_100x60_RGB565\n";return 0;
 }
 if(!snapshot_hw)throw std::runtime_error("SNP1 leased snapshot firmware/device tree is required for live CPU input; PS slot rereads are unsafe");
 Map pl(mem,0xa1000000,0x1000000);Snapshot lease(regs,pl);
 signal(SIGINT,stop);signal(SIGTERM,stop);std::vector<uint16_t> in(96000);
 if(!snapshot.empty()){
  if(!lease.read(in,hold_ms))throw std::runtime_error("no completed snapshot before expiry");
  write_file(snapshot,in.data(),192000);std::cout<<"{\"snapshot\":\"SNP1\",\"frame_id\":"<<lease.frame<<",\"held_ms\":"<<hold_ms<<",\"copy_seconds\":"<<lease.copy_seconds<<",\"released\":true}\n";return 0;
 }
 uint32_t saved=regs.read(0x54);struct Restore{Map&r;uint32_t v;~Restore(){r.write(0x54,v);}}restore{regs,saved};
 unsigned frames=0,retries=0;double compute=0,snapshot_copy=0;auto start=Clock::now();
 while(!stopping&&std::chrono::duration<double>(Clock::now()-start).count()<seconds){
  if(!lease.read(in)){retries++;continue;}snapshot_copy+=lease.copy_seconds;
  auto cstart=Clock::now();auto out=fsr_cpu::upscale(in,id);compute+=std::chrono::duration<double>(Clock::now()-cstart).count();
  unsigned bank=((regs.read(0x58)>>9)&1)^1;volatile uint64_t*dst=(volatile uint64_t*)((char*)pl.p+bank*0x200000);for(int i=0;i<192000;i++){uint64_t word;memcpy(&word,out.data()+i*2,8);dst[i]=word;}barrier();
  uint32_t word=2|(bank<<9)|(saved&0x130);if(style>=0)word=(word&~0x30u)|(style<<4);regs.write(0x54,word);
  auto deadline=Clock::now()+std::chrono::seconds(2);while(regs.read(0x58)!=word){if(stopping)break;if(Clock::now()>deadline)throw std::runtime_error("native frame switch timeout");usleep(1000);}
  frames++;if(!output.empty())write_file(output,out.data(),out.size()*4);if(!source_output.empty())write_file(source_output,in.data(),192000);
 }
 double elapsed=std::chrono::duration<double>(Clock::now()-start).count();std::cout<<"{\"algorithm\":\""<<mode<<"\",\"backend\":\"CPU FP32 4 threads\",\"processed_frames\":"<<frames<<",\"elapsed_seconds\":"<<elapsed<<",\"processed_fps\":"<<frames/elapsed<<",\"compute_seconds\":"<<compute<<",\"snapshot_retries\":"<<retries<<",\"source_ownership\":\"SNP1 leased PL snapshot\",\"snapshot_copy_seconds\":"<<snapshot_copy<<",\"last_source_frame\":"<<lease.frame<<"}\n";
 if(!frames)throw std::runtime_error("no leased GPU source frames processed");
 if(hold_last_seconds){
  std::cout<<"FSR_OUTPUT_HELD_FOR_CAPTURE "<<hold_last_seconds<<std::endl;
  auto until=Clock::now()+std::chrono::duration<double>(hold_last_seconds);
  while(!stopping&&Clock::now()<until)usleep(1000);
 }
 return 0;
 }catch(const std::exception&e){std::cerr<<"rix-superres: "<<e.what()<<'\n';return 1;}}
