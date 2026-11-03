// SPDX-License-Identifier: MIT
// Fixed-data A/B of PL DDR transfers, with no display switch. Run idle.
#include "frame_resample.hpp"
#include "pl_frames.hpp"
#include <iostream>
#include <random>
#include <sys/file.h>
int main(){try{
 if(access("/proc/device-tree/neural-style@a0030000/compatible",F_OK))throw std::runtime_error("NNS1 device tree required");
 int lock=open("/tmp/rix-superres.lock",O_CREAT|O_RDWR,0600);
 if(lock<0||flock(lock,LOCK_EX|LOCK_NB))throw std::runtime_error("postprocessor is running");
 int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0)throw std::runtime_error("open /dev/mem");
 rix_pl::Map regs(fd,0xa0010000,65536),pl(fd,0xa1000000,0x1000000);
 if(regs.read(0x50)!=0x50535431||regs.read(0x54)!=regs.read(0x58))throw std::runtime_error("display is not stable");
 unsigned bank=((regs.read(0x58)>>9)&1)^1;
 auto*dest=static_cast<char*>(pl.p)+bank*0x200000;
 std::vector<uint32_t> data(384000),actual(384000);std::mt19937 random(0x4e4e5331);for(auto&v:data)v=random()&0xffffff;
 rix_frames::Resampler plan;std::vector<uint16_t> small(96000);
 std::vector<double> scalar,paired,full,sparse,two,four;
 auto read=[&](bool skip,unsigned workers=1){
  auto start=rix_pl::Clock::now();
  rix_pl::copy_snapshot(dest,small,skip?plan.source_rows.data():nullptr,workers);
  rix_pl::barrier();double seconds=std::chrono::duration<double>(rix_pl::Clock::now()-start).count();
  for(unsigned y=0;y<240;y++)if(!skip||plan.source_rows[y])for(unsigned x=0;x<400;x++){
   auto p=data[y*400+x];if(small[y*400+x]!=uint16_t(((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&0x1f)))throw std::runtime_error("read data mismatch");
  }
  return seconds;
 };
 for(unsigned repetition=0;repetition<6;repetition++)for(unsigned index=0;index<2;index++){
  bool use_pairs=(index+(repetition&1))&1;
  auto start=rix_pl::Clock::now();
  if(use_pairs)rix_pl::write_words(dest,data.data(),data.size());
  else{auto*dst=reinterpret_cast<volatile uint64_t*>(dest);for(unsigned i=0;i<192000;i++){uint64_t v;memcpy(&v,data.data()+i*2,8);dst[i]=v;}rix_pl::barrier();}
  double elapsed=std::chrono::duration<double>(rix_pl::Clock::now()-start).count();
  rix_pl::read_words(dest,actual.data(),actual.size());rix_pl::barrier();
  if(actual!=data)throw std::runtime_error("full write readback mismatch");
  if(repetition)(use_pairs?paired:scalar).push_back(elapsed);
  double elapsed_read=read(use_pairs);if(repetition)(use_pairs?sparse:full).push_back(elapsed_read);
  if(use_pairs)for(unsigned index=0;index<2;index++){
   unsigned workers=((index+(repetition&1))&1)?4:2;
   double seconds=read(true,workers);if(repetition)(workers==2?two:four).push_back(seconds);
  }
 }
 auto array=[](const char*name,const std::vector<double>&values){std::cout<<'"'<<name<<"\":[";for(size_t i=0;i<values.size();i++){if(i)std::cout<<',';std::cout<<values[i];}std::cout<<']';};
 std::cout<<"{\"scope\":\"idle GPU; fixed XRGB tensor; alternating order; one warmup plus five measured repetitions; inactive HR bank; no display switch\",\"display_bytes\":1536000,\"snapshot_bytes_before\":384000,\"snapshot_bytes_after\":307200,";
 array("scalar_write_seconds",scalar);std::cout<<',';array("paired_write_seconds",paired);std::cout<<',';array("full_read_seconds",full);std::cout<<',';array("sparse_read_seconds",sparse);
 std::cout<<',';array("two_core_read_seconds",two);std::cout<<',';array("four_core_read_seconds",four);
 std::cout<<",\"all_bit_exact\":true,\"passed\":true}\n";
 close(fd);close(lock);return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
