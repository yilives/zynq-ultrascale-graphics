// SPDX-License-Identifier: GPL-3.0-or-later
// Host-only syscall adapter. This header is never included by the ARM build.
#pragma once
#include <array>
#include <vector>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include "rix-geometry.h"
#include "state_codec.hpp"
#include <cerrno>
#include <cstring>
#include <stdexcept>
namespace geometry_mock {
inline std::vector<uint32_t>pool(rixgeo::POOL_WORDS);
inline bool opened=false;inline unsigned fault=0,submits=0;
}
inline int geometry_test_open(const char*name,int flags,...){
 if(std::strcmp(name,"/dev/rix-geometry")||geometry_mock::opened){errno=EBUSY;return -1;}
 if(!(flags&O_NOFOLLOW)||!(flags&O_CLOEXEC))throw std::runtime_error("Missing device path/exec protection");
 geometry_mock::opened=true;return 42;
}
inline int geometry_test_close(int fd){if(fd!=42)throw std::runtime_error("Mock fd");geometry_mock::opened=false;return 0;}
inline int geometry_test_fstat(int fd,struct stat*p){if(fd!=42)return -1;std::memset(p,0,sizeof(*p));p->st_mode=S_IFCHR;return 0;}
inline void*geometry_test_mmap(void*,size_t n,int,int,int fd,off_t offset){
 if(fd!=42||n!=rixgeo::POOL_WORDS*4||offset)throw std::runtime_error("Unbounded geometry mapping");
 return geometry_mock::pool.data();
}
inline int geometry_test_munmap(void*p,size_t n){if(p!=geometry_mock::pool.data()||n!=rixgeo::POOL_WORDS*4)throw std::runtime_error("Mock mapping");return 0;}
inline int geometry_test_ioctl(int fd,unsigned long op,void*arg){
 if(fd!=42)throw std::runtime_error("Mock ioctl fd");
 if(op==RIX_GEOMETRY_INFO){
  auto*p=static_cast<rix_geometry_info*>(arg);*p={rixgeo::MAGIC,rixgeo::ABI,rixgeo::POOL_WORDS*4,rixgeo::MAX_VERTICES,
   rixgeo::STATE_WORDS,rixgeo::VERTEX_OFFSET,rixgeo::CARRY_OFFSET,rixgeo::OUTPUT_OFFSET,rixgeo::RECORD_WORDS,rixgeo::MAX_RECORDS,0x4a324731,0};
  if(geometry_mock::fault==1)p->abi^=1;return 0;
 }
 if(op!=RIX_GEOMETRY_SUBMIT)throw std::runtime_error("Unexpected ioctl");
 auto*p=static_cast<rix_geometry_job*>(arg);
 if(p->reserved||p->reserved_out[0]||p->reserved_out[1]||!p->sequence||!p->count||p->count>2048)throw std::runtime_error("Bad submitted job");
 if(geometry_mock::fault==2){errno=ETIMEDOUT;return -1;}
 uint64_t result=rixgeo::rix_geometry_hls(geometry_mock::pool.data(),p->mode,p->count,p->sequence);++geometry_mock::submits;
 p->records=uint32_t(result);p->status=result>>32;
 if(p->records&&geometry_mock::fault==3)geometry_mock::pool[rixgeo::OUTPUT_OFFSET]=48;
 if(p->records&&geometry_mock::fault==4)geometry_mock::pool[rixgeo::OUTPUT_OFFSET+2]=0xdeadc0de;
 return 0;
}
#define open geometry_test_open
#define close geometry_test_close
#define fstat geometry_test_fstat
#define ioctl geometry_test_ioctl
#define mmap geometry_test_mmap
#define munmap geometry_test_munmap
#include "java_geometry_device_r1.hpp"
#undef open
#undef close
#undef fstat
#undef ioctl
#undef mmap
#undef munmap
inline unsigned geometry_bridge_cases=0;
template<class Case>void geometryBridgeCase(const Case&c,const rr::vertextransformer::VertexTransformerData&original,
                                           const std::array<std::vector<uint32_t>,3>&expected){
 setenv("RIX_JAVA_FPGA_GEOMETRY","1",1);unsetenv("RIX_JAVA_GEOMETRY_STATS");
 {
  rr::java_geometry::Device device;device.beginDraw();auto context=original;
  bool scissor=c.option==12;int32_t box[4]={scissor?180:0,scissor?100:0,scissor?20:400,scissor?30:240};
  std::array<std::vector<uint32_t>,3>actual;
  auto fetch=[&](unsigned i){const auto&v=c.vertices[i];rr::VertexParameter p;p.sourceIndex=i;p.vertex=rr::Vec4(v.position);p.color=rr::Vec4(v.color);p.normal=rr::Vec3(v.normal);p.pointSize=v.point_size;for(unsigned t=0;t<2;t++)p.tex[t]=rr::Vec4(v.texture[t]);return p;};
  auto emit=[&](uint32_t mask,const uint32_t*p,unsigned n){for(unsigned b=0;b<3;b++)if(mask&(1u<<b))actual[b].insert(actual[b].end(),p,p+n);return true;};
  if(!device.push(c.vertices.size(),fetch,context,scissor,box,c.option==7?1:3,emit)||actual!=expected)throw std::runtime_error("Geometry bridge output mismatch");
 }
 if(geometry_mock::opened)throw std::runtime_error("Geometry device was not closed");
 ++geometry_bridge_cases;
 if(std::strcmp(c.name,"inside")==0)for(unsigned fault:{1u,2u,3u,4u}){
  geometry_mock::fault=fault;bool refused=false;unsigned emitted=0;
  try{
   rr::java_geometry::Device device;device.beginDraw();auto context=original;bool scissor=false;int32_t box[4]={0,0,400,240};
   auto fetch=[&](unsigned i){const auto&v=c.vertices[i];rr::VertexParameter p;p.sourceIndex=i;p.vertex=rr::Vec4(v.position);p.color=rr::Vec4(v.color);p.normal=rr::Vec3(v.normal);p.pointSize=v.point_size;for(unsigned t=0;t<2;t++)p.tex[t]=rr::Vec4(v.texture[t]);return p;};
   device.push(c.vertices.size(),fetch,context,scissor,box,3,[&](uint32_t,const uint32_t*,unsigned){++emitted;return true;});
  }catch(const std::runtime_error&){refused=true;}
  if(!refused||emitted||geometry_mock::opened)throw std::runtime_error("Geometry bridge fault not contained");
  geometry_mock::fault=0;
 }
}
