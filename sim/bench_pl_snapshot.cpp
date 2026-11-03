// SPDX-License-Identifier: MIT
// Read-only diagnostic. Hold the API mutex and require an idle immutable slot.
#include <arm_neon.h>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <vector>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <unistd.h>
int main(){
 if(access("/proc/device-tree/rasterix-frame-snapshot/rasterix,snapshot-version",F_OK))return 2;
 int lock=open("/tmp/rix-superres.lock",O_CREAT|O_RDWR,0600);if(lock<0||flock(lock,LOCK_EX|LOCK_NB))return 3;
 int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0)return 4;
 auto regs=(volatile unsigned*)mmap(nullptr,65536,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0xa0010000);
 if(regs==MAP_FAILED||regs[0x74/4]!=0x534e5031||(regs[0x7c/4]&3))return 5;
 auto src=(const uint64_t*)mmap(nullptr,384000,PROT_READ,MAP_SHARED,fd,0xa1400000);if(src==MAP_FAILED)return 6;
 std::vector<uint64_t> reference(48000),out(48000);
 for(int mode=0;mode<4;mode++){
  auto start=std::chrono::steady_clock::now();
  for(int repeat=0;repeat<3;repeat++){
   if(mode==0)for(int i=0;i<48000;i++)out[i]=((volatile uint64_t*)src)[i];
   if(mode==1)for(int i=0;i<48000;i+=2){uint64x2_t v;asm volatile("ldr %q0, [%1]":"=w"(v):"r"(src+i):"memory");vst1q_u64(out.data()+i,v);}
   if(mode==2)for(int i=0;i<48000;i+=4){uint64x2_t a,b;asm volatile("ldp %q0, %q1, [%2]":"=&w"(a),"=&w"(b):"r"(src+i):"memory");vst1q_u64(out.data()+i,a);vst1q_u64(out.data()+i+2,b);}
   if(mode==3)for(int i=0;i<48000;i+=8)asm volatile("ld1 {v0.16b-v3.16b}, [%0]\n\tst1 {v0.16b-v3.16b}, [%1]"::"r"(src+i),"r"(out.data()+i):"v0","v1","v2","v3","memory");
   asm volatile("dsb sy":::"memory");
  }
  double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()/3;
  if(mode==0)reference=out;else if(reference!=out)return 7;
  printf("PL_SNAPSHOT_READ mode=%d seconds=%.6f MBps=%.3f exact_match=true\n",mode,seconds,.384/seconds);fflush(stdout);
 }
 return 0;
}
