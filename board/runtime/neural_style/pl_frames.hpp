// SPDX-License-Identifier: MIT
// SNP1 ownership and paired Device-memory reads adapted from rix_superres.cpp.
// The deployed FSR implementation is deliberately kept byte-for-byte intact.
#pragma once
#include <chrono>
#include <cstdint>
#include <cstring>
#include <csignal>
#include <fcntl.h>
#include <stdexcept>
#include <array>
#include <atomic>
#include <thread>
#include <sys/mman.h>
#include <unistd.h>
#include <vector>
namespace rix_pl {
using Clock=std::chrono::steady_clock;
static_assert(std::atomic<sig_atomic_t>::is_always_lock_free,"signal flag must be lock-free");
inline std::atomic<sig_atomic_t>& stopped(){static std::atomic<sig_atomic_t> value{0};return value;}
inline void stop(int){stopped()=1;}
inline void barrier(){
#ifdef __aarch64__
 asm volatile("dsb sy":::"memory");
#else
 __sync_synchronize();
#endif
}
struct Map {
 void*p;size_t bytes;
 Map(int fd,uint64_t base,size_t size,int protection=PROT_READ|PROT_WRITE):bytes(size){p=mmap(nullptr,size,protection,MAP_SHARED,fd,base);if(p==MAP_FAILED)throw std::runtime_error("mmap failed");}
 ~Map(){munmap(p,bytes);}
 uint32_t read(unsigned offset)const{barrier();return *reinterpret_cast<volatile uint32_t*>(static_cast<char*>(p)+offset);}
 void write(unsigned offset,uint32_t value){*reinterpret_cast<volatile uint32_t*>(static_cast<char*>(p)+offset)=value;barrier();}
};
// PL DDR is Device memory, not a cacheable memcpy target. Keep accesses
// explicit and 32-byte aligned; each pair remains within a 4 KiB page.
inline void read_words(const void*source,uint32_t*dest,size_t words){
 if(reinterpret_cast<uintptr_t>(source)%32||words%8)throw std::runtime_error("unaligned PL read");
#ifdef __aarch64__
 for(size_t i=0;i<words;i+=8){
  auto*src=static_cast<const char*>(source)+i*4;
  asm volatile("ldp q0, q1, [%0]\n\tstp q0, q1, [%1]"::"r"(src),"r"(dest+i):"v0","v1","memory");
 }
#else
 auto*src=static_cast<const volatile uint32_t*>(source);for(size_t i=0;i<words;i++)dest[i]=src[i];
#endif
}
inline void write_words(void*dest,const uint32_t*source,size_t words){
 if(reinterpret_cast<uintptr_t>(dest)%32||words%8)throw std::runtime_error("unaligned PL write");
#ifdef __aarch64__
 for(size_t i=0;i<words;i+=8){
  auto*dst=static_cast<char*>(dest)+i*4;
  asm volatile("ldp q0, q1, [%0]\n\tstp q0, q1, [%1]"::"r"(source+i),"r"(dst):"v0","v1","memory");
 }
#else
 auto*dst=static_cast<volatile uint32_t*>(dest);for(size_t i=0;i<words;i++)dst[i]=source[i];
#endif
 barrier();
}
inline void copy_snapshot(const void*source,std::vector<uint16_t>&in,const bool*rows=nullptr,unsigned workers=4){
 if(in.size()!=96000||reinterpret_cast<uintptr_t>(source)%32||(workers!=1&&workers!=2&&workers!=4))throw std::runtime_error("invalid snapshot copy layout");
 auto copy=[&](unsigned lo,unsigned hi){
  alignas(16) uint32_t words[8];
  for(unsigned y=lo;y<hi;y++){
   if(rows&&!rows[y])continue;
   for(unsigned i=y*400;i<(y+1)*400;i+=8){
    read_words(static_cast<const char*>(source)+i*4,words,8);
    for(unsigned j=0;j<8;j++){auto p=words[j];in[i+j]=((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&0x1f);}
   }
  }
  // Each CPU drains its Device reads before the owning thread can release
  // the lease. Threads only write disjoint rows of CPU memory.
  barrier();
 };
 std::array<std::thread,3> threads;
 try{
  for(unsigned i=0;i+1<workers;i++)threads[i]=std::thread(copy,240*i/workers,240*(i+1)/workers);
  copy(240*(workers-1)/workers,240);
 }catch(...){for(auto&t:threads)if(t.joinable())t.join();throw;}
 for(auto&t:threads)if(t.joinable())t.join();
}
struct Snapshot {
 Map&r;Map&pl;uint32_t token=0,frame=0;
 double wait_seconds=0,read_seconds=0;
 Snapshot(Map&regs,Map&memory):r(regs),pl(memory){}
 bool owned()const{return token&&r.read(0x80)==token&&(r.read(0x7c)&3)==3;}
 void release(){if(token&&r.read(0x80)==token&&(r.read(0x7c)&3))r.write(0x80,token);token=0;}
 ~Snapshot(){release();}
 bool request(){
  if(token)return true;
  auto deadline=Clock::now()+std::chrono::seconds(3);
  while(r.read(0x7c)&3){if(stopped())return false;if(Clock::now()>deadline)throw std::runtime_error("snapshot remains busy");usleep(1000);}
  if(stopped())return false;
  token=r.read(0x80)+1;if(!token)token=1;r.write(0x78,token);
  return true;
 }
 bool read(std::vector<uint16_t>&in,const bool*rows=nullptr,unsigned workers=4,
           void(*copy)(const void*,std::vector<uint16_t>&,const bool*,unsigned)=copy_snapshot){
  if(in.size()!=96000)throw std::runtime_error("invalid snapshot buffer");
  auto started=Clock::now(),deadline=started+std::chrono::seconds(3);
  if(!request())return false;
  while(!owned()){
   if(stopped()){release();return false;}
   if(r.read(0x80)==token&&(r.read(0x7c)&3)==0){release();return false;}
   if(Clock::now()>deadline)throw std::runtime_error("snapshot timeout");usleep(1000);
  }
  frame=r.read(0x84);auto copy_started=Clock::now();wait_seconds=std::chrono::duration<double>(copy_started-started).count();
  copy(static_cast<const char*>(pl.p)+0x400000,in,rows,workers);
  barrier();read_seconds=std::chrono::duration<double>(Clock::now()-copy_started).count();
  if(!owned()){release();return false;}release();return !stopped();
 }
};
}
