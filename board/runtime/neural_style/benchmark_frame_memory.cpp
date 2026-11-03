// SPDX-License-Identifier: MIT
// Alternate read attributes on fixed, non-displayed PL RAM. All writes retain
// the released Device mapping and barriers. No MMIO is mapped Normal-NC.
#include "frame_memory.hpp"
#include "frame_resample.hpp"
#include <iostream>
#include <random>
#include <sys/file.h>
int main(){try{
 int lock=open("/tmp/rix-superres.lock",O_CREAT|O_RDWR,0600);if(lock<0||flock(lock,LOCK_EX|LOCK_NB))throw std::runtime_error("postprocessor running");
 int mem=open("/dev/mem",O_RDWR|O_SYNC);if(mem<0)throw std::runtime_error("open /dev/mem");
 int normal=rix_pl::frame_memory_fd();
 rix_pl::Map regs(mem,0xa0010000,65536),device(mem,RIX_FRAME_MEM_BASE,RIX_FRAME_MEM_BYTES),nc(normal,0,RIX_FRAME_MEM_BYTES,PROT_READ);
 if(regs.read(0x50)!=0x50535431||regs.read(0x54)!=regs.read(0x58))throw std::runtime_error("display unstable");
 auto saved=regs.read(0x58);unsigned offset=((((saved>>9)&1)^1)*0x200000);
 auto*target=static_cast<char*>(device.p)+offset;
 std::vector<uint32_t> data(384000),actual(384000),raw(96000);std::mt19937 random(0x52464d31);
 rix_frames::Resampler plan;std::vector<uint16_t> small(96000);std::vector<double> samples[6];
 for(unsigned repetition=0;repetition<6;repetition++){
  for(auto&v:data)v=random()&0xffffff;rix_pl::write_words(target,data.data(),data.size());
  // Read the entire 1.536 MB with each attribute after every fresh write.
  for(unsigned mode=0;mode<2;mode++){
   auto*source=static_cast<const char*>(mode?nc.p:device.p)+offset;
   rix_pl::read_words(source,actual.data(),actual.size());rix_pl::barrier();
   if(actual!=data)throw std::runtime_error("full-frame attribute readback mismatch");
  }
  for(unsigned index=0;index<6;index++){
   unsigned mode=(index+repetition)%6;auto*source=static_cast<const char*>(mode>=3?nc.p:device.p)+offset;
   unsigned workers=mode==0||mode==3?1:mode==1?2:4;
   rix_pl::barrier();auto start=rix_pl::Clock::now();
   auto copy=[&](unsigned lo,unsigned hi){
    for(unsigned y=lo;y<hi;y++)if(plan.source_rows[y]){
    if(mode==5){
     memcpy(raw.data()+y*400,source+y*1600,1600);
     for(unsigned x=0;x<400;x++){auto p=raw[y*400+x];small[y*400+x]=((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&0x1f);}
    }else{
     alignas(16) uint32_t words[8];
     for(unsigned x=0;x<400;x+=8){unsigned i=y*400+x;rix_pl::read_words(source+i*4,words,8);
      for(unsigned j=0;j<8;j++){auto p=words[j];small[i+j]=((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&0x1f);}
     }
    }
   }
   rix_pl::barrier();};
   std::vector<std::thread> threads;
   for(unsigned i=0;i+1<workers;i++)threads.emplace_back(copy,240*i/workers,240*(i+1)/workers);
   copy(240*(workers-1)/workers,240);for(auto&t:threads)t.join();
   rix_pl::barrier();double seconds=std::chrono::duration<double>(rix_pl::Clock::now()-start).count();
   for(unsigned y=0;y<240;y++)if(plan.source_rows[y])for(unsigned x=0;x<400;x++){
    auto p=data[y*400+x];if(small[y*400+x]!=uint16_t(((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&0x1f)))throw std::runtime_error("snapshot-sized read mismatch");
   }
   if(repetition)samples[mode].push_back(seconds);
  }
 }
 if(regs.read(0x58)!=saved||regs.read(0x54)!=saved)throw std::runtime_error("display changed during benchmark");
 const char*names[]={"device_pairs_seconds","device_pairs_two_seconds","device_pairs_four_seconds","normal_nc_pairs_seconds","normal_nc_pairs_four_seconds","normal_nc_memcpy_four_seconds"};
 std::cout<<"{\"scope\":\"idle GPU; same fixed data; rotated order; one warmup plus five samples; full cross-attribute readback after every write; released Device writes only\",\"snapshot_bytes\":307200,";
 for(unsigned mode=0;mode<6;mode++){if(mode)std::cout<<',';std::cout<<'"'<<names[mode]<<"\":[";for(unsigned i=0;i<samples[mode].size();i++){if(i)std::cout<<',';std::cout<<samples[mode][i];}std::cout<<']';}
 std::cout<<",\"all_bit_exact\":true,\"passed\":true}\n";
 close(normal);close(mem);close(lock);return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
