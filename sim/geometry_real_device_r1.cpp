// Hardware acceptance adapter, never linked into the game library.
// No CPU geometry implementation is linked as the kernel entry point.
#include "protocol.hpp"
#include "rix-geometry.h"
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <atomic>
#include <cstring>
#include <stdexcept>
#include <string>
#include <cstdio>
#include <cerrno>
namespace {
struct NativeDevice {
 int fd=-1;uint32_t*pool=nullptr;uint64_t calls=0;
 NativeDevice(){
  fd=::open("/dev/rix-geometry",O_RDWR|O_CLOEXEC|O_NOFOLLOW);if(fd<0)throw std::runtime_error("geometry open errno="+std::to_string(errno));
  struct stat st{};if(fstat(fd,&st)||!S_ISCHR(st.st_mode))throw std::runtime_error("not geometry character device");
  rix_geometry_info info{},expected={rixgeo::MAGIC,rixgeo::ABI,rixgeo::POOL_WORDS*4,rixgeo::MAX_VERTICES,
   rixgeo::STATE_WORDS,rixgeo::VERTEX_OFFSET,rixgeo::CARRY_OFFSET,rixgeo::OUTPUT_OFFSET,rixgeo::RECORD_WORDS,rixgeo::MAX_RECORDS,0x4a324731,0};
  if(ioctl(fd,RIX_GEOMETRY_INFO,&info)||std::memcmp(&info,&expected,sizeof(info)))throw std::runtime_error("native geometry ABI/profile mismatch");
  void*p=mmap(nullptr,rixgeo::POOL_WORDS*4,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
  if(p==MAP_FAILED)throw std::runtime_error("geometry mmap failed");pool=static_cast<uint32_t*>(p);
 }
 ~NativeDevice(){if(pool)munmap(pool,rixgeo::POOL_WORDS*4);if(fd>=0)::close(fd);std::printf("NATIVE_GEOMETRY_DEVICE_CLOSED hardware_ioctl_calls=%llu\n",(unsigned long long)calls);}
};
}
extern "C" uint64_t rix_geometry_hls(uint32_t*memory,uint32_t mode,uint32_t count,uint32_t sequence){
 if(!memory||(mode!=1&&mode!=2)||!count||count>rixgeo::MAX_VERTICES||!sequence)throw std::runtime_error("invalid native checker request");
 static NativeDevice device;
 std::memcpy(device.pool,memory,rixgeo::STATE_WORDS*4);
 std::memcpy(device.pool+rixgeo::VERTEX_OFFSET,memory+rixgeo::VERTEX_OFFSET,count*rixgeo::VERTEX_WORDS*4);
 rix_geometry_job job{};job.mode=mode;job.count=count;job.sequence=sequence;
 std::atomic_thread_fence(std::memory_order_seq_cst);
 if(ioctl(device.fd,RIX_GEOMETRY_SUBMIT,&job))throw std::runtime_error("native geometry ioctl errno="+std::to_string(errno));
 ++device.calls;std::atomic_thread_fence(std::memory_order_seq_cst);
 if(job.reserved||job.reserved_out[0]||job.reserved_out[1]||job.records>rixgeo::MAX_RECORDS)throw std::runtime_error("native geometry invalid result");
 std::memcpy(memory+rixgeo::CARRY_OFFSET,device.pool+rixgeo::CARRY_OFFSET,256*4);
 if(!job.status)std::memcpy(memory+rixgeo::OUTPUT_OFFSET,device.pool+rixgeo::OUTPUT_OFFSET,job.records*rixgeo::RECORD_WORDS*4);
 return (uint64_t(job.status)<<32)|job.records;
}
