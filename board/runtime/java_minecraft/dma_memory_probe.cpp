// SPDX-License-Identifier: GPL-3.0-or-later
// CPU writes only an idle unused TX slot. No START_XFER/XFER/FINISH_XFER.
#include "dma-proxy.h"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <fcntl.h>
#include <stdexcept>
#include <string>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
static void require(bool b,const char*s){if(!b)throw std::runtime_error(s);}
int main(int argc,char**argv){try{
 require(argc==4&&geteuid()==0,"Trusted parent and three inherited locks required");
 const char*names[]={"/tmp/rasterix-game-launch.lock","/tmp/rix-superres.lock","/tmp/rix-mc-style-extract.lock"};
 for(int n=0;n<3;++n){int fd=std::stoi(argv[n+1]);struct stat a{},b{};require(fd>2&&fstat(fd,&a)==0&&stat(names[n],&b)==0&&a.st_dev==b.st_dev&&a.st_ino==b.st_ino&&flock(fd,LOCK_EX|LOCK_NB)==0,"Runtime lock mismatch");}
 int fd=open("/dev/dma_proxy_tx",O_RDWR|O_CLOEXEC|O_NOFOLLOW);require(fd>=0,"TX open failed");uint32_t abi=0;require(ioctl(fd,RIX_DMA_GET_ABI,&abi)==0&&abi==RIX_DMA_ABI_VERSION,"DMA ABI mismatch");
 const size_t mappedBytes=sizeof(channel_buffer)*TX_BUFFER_COUNT;void*map=mmap(nullptr,mappedBytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);require(map!=MAP_FAILED,"TX mapping failed");
 auto*buffers=static_cast<channel_buffer*>(map);require(TX_BUFFER_COUNT==8&&buffers[6].status!=PROXY_BUSY,"Probe requires idle unused slot 6");
 auto*target=reinterpret_cast<uint8_t*>(buffers[6].buffer);std::vector<uint8_t>backup(target,target+BUFFER_SIZE);std::vector<uint32_t>sourceWords(BUFFER_SIZE/4,0x5a5a5a5a),cachedWords(BUFFER_SIZE/4);
 auto*source=reinterpret_cast<uint8_t*>(sourceWords.data());auto*cached=reinterpret_cast<uint8_t*>(cachedWords.data());
 struct Restore{uint8_t*target;const std::vector<uint8_t>&backup;~Restore(){std::memcpy(target,backup.data(),backup.size());std::atomic_thread_fence(std::memory_order_seq_cst);}}restore{target,backup};
 // Source[0] changes per pass; compiler barrier prevents collapsing repeats.
 for(size_t bytes:{size_t(65536),size_t(BUFFER_SIZE)})for(bool scalar:{false,true})for(bool dma:{false,true}){
  uint8_t*dest=dma?target:cached;const unsigned repetitions=16;auto start=std::chrono::steady_clock::now();
  for(unsigned r=0;r<repetitions;++r){source[0]=uint8_t(r);if(scalar){auto*out=reinterpret_cast<volatile uint32_t*>(dest);auto*in=sourceWords.data();for(size_t k=0;k<bytes/4;++k)out[k]=in[k];}else std::memcpy(dest,source,bytes);asm volatile("":::"memory");}
  std::atomic_thread_fence(std::memory_order_seq_cst);double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();require(std::memcmp(dest,source,bytes)==0,"Memory copy mismatch");
  std::printf("{\"destination\":\"%s\",\"pattern\":\"%s\",\"bytes\":%zu,\"repetitions\":%u,\"seconds\":%.9f,\"mib_per_second\":%.3f}\n",dma?"dma_mmap":"cached_heap",scalar?"scalar32":"memcpy",bytes,repetitions,seconds,bytes*repetitions/1048576.0/seconds);
 }
 // Restore while mapping is still alive. No DMA ever starts.
 std::memcpy(target,backup.data(),backup.size());std::atomic_thread_fence(std::memory_order_seq_cst);require(std::memcmp(target,backup.data(),backup.size())==0,"Slot restoration failed");
 std::printf("DMA_MEMORY_PROBE_PASS no_dma_started=1 slot=6 original_bytes_restored=1 cached_heap_excludes_dma_cache_maintenance=1\n");
 // Mapping closes with process after the RAII restore destructor.
 (void)map;(void)fd;return 0;
}catch(const std::exception&e){std::fprintf(stderr,"DMA_MEMORY_PROBE_REFUSED %s\n",e.what());return 1;}}
