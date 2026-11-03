// SPDX-License-Identifier: MIT
// Default: ordinary host memory numerical tests. --live-leased: independent
// immutable SNP1 lease per pair, no display writes, requires a running source.
#include "mc_snapshot_copy.hpp"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <random>
#include <string>
#include <sys/file.h>

static uint16_t golden(uint32_t p) {
 return uint16_t(((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&31));
}
struct Aligned {
 uint32_t*p=nullptr;
 Aligned(){if(posix_memalign(reinterpret_cast<void**>(&p),32,384000))throw std::runtime_error("aligned allocation failed");}
 ~Aligned(){free(p);}
};
static void host() {
 Aligned raw;std::mt19937 random(0x4d435332);
 std::vector<uint16_t> result(96000),baseline(96000);unsigned long checks=0;
 // Exhaust every RGB24 value, with varying ignored X byte. This validates
 // NEON narrowing and all discarded channel bits, rather than only RGB565.
 for(unsigned rgb=0;rgb<0x1000000;rgb+=8) {
  for(unsigned j=0;j<8;j++)raw.p[j]=(rgb+j)|(((rgb*1664525u+j)&255)<<24);
  rix_pl::mc_snapshot_detail::copy8(raw.p,result.data());
  for(unsigned j=0;j<8;j++){if(result[j]!=golden(raw.p[j]))throw std::runtime_error("exhaustive RGB24 conversion mismatch");checks++;}
 }
 for(unsigned i=0;i<96000;i++)raw.p[i]=random();
 std::array<bool,240> rows{};for(unsigned y=0;y<240;y++)rows[y]=y%5!=0;
 for(unsigned workers:{1u,2u,4u})for(bool sparse:{false,true}) {
  std::fill(result.begin(),result.end(),0x5aa5);std::fill(baseline.begin(),baseline.end(),0x5aa5);
  rix_pl::copy_snapshot(raw.p,baseline,sparse?rows.data():nullptr,workers);
  rix_pl::copy_snapshot_neon(raw.p,result,sparse?rows.data():nullptr,workers);
  for(unsigned i=0;i<96000;i++) {
   auto expected=sparse&&!rows[i/400]?uint16_t(0x5aa5):golden(raw.p[i]);
   if(result[i]!=expected||baseline[i]!=expected)throw std::runtime_error("full/sparse frame copy mismatch");checks++;
  }
 }
 auto reject=[&](auto f){bool caught=false;try{f();}catch(const std::runtime_error&){caught=true;}if(!caught)throw std::runtime_error("invalid layout accepted");checks++;};
 reject([&](){rix_pl::copy_snapshot_neon(raw.p+1,result);});
 reject([&](){rix_pl::copy_snapshot_neon(nullptr,result);});
 reject([&](){rix_pl::copy_snapshot_neon(raw.p,result,nullptr,3);});
 std::vector<uint16_t> short_buffer(95999);
 reject([&](){rix_pl::copy_snapshot_neon(raw.p,short_buffer);});
 std::cout<<"{\"passed\":true,\"checks\":"<<checks<<",\"implementation\":\""
#ifdef __aarch64__
 <<"aarch64-neon-register-pack"
#else
 <<"scalar-host-fallback"
#endif
 <<"\",\"scope\":\"ordinary aligned memory, not Device throughput\"}\n";
}
static void live() {
 signal(SIGINT,rix_pl::stop);signal(SIGTERM,rix_pl::stop);
 if(access("/proc/device-tree/rasterix-frame-snapshot/rasterix,snapshot-version",F_OK))throw std::runtime_error("SNP1 device tree required");
 int lock=open("/tmp/rix-superres.lock",O_CREAT|O_RDWR,0600);
 if(lock<0||flock(lock,LOCK_EX|LOCK_NB))throw std::runtime_error("postprocessor is running");
 int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0)throw std::runtime_error("open /dev/mem");
 rix_pl::Map regs(fd,0xa0010000,65536),pl(fd,0xa1000000,0x1000000);
 if(regs.read(0x50)!=0x50535431||regs.read(0x74)!=0x534e5031||regs.read(0x88)!=0xa1400000||regs.read(0x90)!=384000)throw std::runtime_error("PST1/SNP1 layout mismatch");
 if(regs.read(0x7c)&3)throw std::runtime_error("snapshot is already owned");
 rix_pl::Snapshot lease(regs,pl);std::vector<uint16_t> old(96000),candidate(96000);
 uint32_t expirations=regs.read(0x8c); // SNP1 lease expiration counter.
 struct Sample{unsigned workers,frame,order;double legacy,neon;};std::vector<Sample> samples;
 for(unsigned workers:{1u,2u,4u})for(unsigned rep=0;rep<6;rep++) {
  if(!lease.request())throw std::runtime_error("snapshot request stopped");
  auto deadline=rix_pl::Clock::now()+std::chrono::seconds(3);
  while(!lease.owned()) {
   if(rix_pl::stopped())throw std::runtime_error("benchmark stopped before copy");
   if(rix_pl::Clock::now()>deadline)throw std::runtime_error("source is not presenting snapshots");usleep(1000);
  }
  uint32_t frame=regs.read(0x84);double timing[2]{};
  for(unsigned position=0;position<2;position++) {
   unsigned which=(position+(rep&1))&1;
   auto began=rix_pl::Clock::now();
   if(which)rix_pl::copy_snapshot_neon(static_cast<const char*>(pl.p)+0x400000,candidate,nullptr,workers);
   else rix_pl::copy_snapshot(static_cast<const char*>(pl.p)+0x400000,old,nullptr,workers);
   rix_pl::barrier();timing[which]=std::chrono::duration<double>(rix_pl::Clock::now()-began).count();
   if(!lease.owned()||regs.read(0x84)!=frame||regs.read(0x8c)!=expirations)throw std::runtime_error("snapshot lease/frame changed during A/B");
   if(rix_pl::stopped())throw std::runtime_error("benchmark stopped after copy drain");
  }
  if(old!=candidate)throw std::runtime_error("leased Device copy mismatch");
  lease.release();if(rep)samples.push_back({workers,frame,rep&1,timing[0],timing[1]});
 }
 std::cout<<"{\"passed\":true,\"scope\":\"same immutable leased SNP1 frame per alternating pair; one warmup plus five samples per worker count; full384000B reads; no display writes\",\"samples\":[";
 for(size_t i=0;i<samples.size();i++){const auto&s=samples[i];if(i)std::cout<<',';std::cout<<"{\"workers\":"<<s.workers<<",\"frame\":"<<s.frame<<",\"first_neon\":"<<s.order<<",\"legacy_seconds\":"<<s.legacy<<",\"neon_seconds\":"<<s.neon<<'}';}
 std::cout<<"],\"full_frame_matches\":true,\"lease_expirations\":"<<expirations<<"}\n";
 close(fd);close(lock);
}
int main(int argc,char**argv){try{
 if(argc==1)host();
 else if(argc==2&&std::string(argv[1])=="--live-leased")live();
 else throw std::runtime_error("usage: test-mc-snapshot-copy [--live-leased]");
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
