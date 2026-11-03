// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "state_codec.hpp"
#include "rix-geometry.h"
#include "VertexParameter.hpp"
#include "renderer/commands/Op.hpp"
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <stdexcept>
#include <string>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
namespace rr::java_geometry {
class Device {
 bool enabled_=[](){const char*p=std::getenv("RIX_JAVA_FPGA_GEOMETRY");return p&&std::strcmp(p,"1")==0;}();
 int fd_=-1;uint32_t*pool_=nullptr;uint32_t sequence_=0,submitted_=0;
 uint64_t jobs_=0,vertices_=0,records_=0,draws_=0,cpuVertices_=0;
 void open(){
  if(fd_>=0)return;
  fd_=::open("/dev/rix-geometry",O_RDWR|O_CLOEXEC|O_NOFOLLOW);
  if(fd_<0)throw std::runtime_error("RIX_GEOMETRY device open: "+std::to_string(errno));
  struct stat st{};if(fstat(fd_,&st)||!S_ISCHR(st.st_mode))throw std::runtime_error("RIX_GEOMETRY requires character device");
  rix_geometry_info info{};
  if(ioctl(fd_,RIX_GEOMETRY_INFO,&info)||info.magic!=rixgeo::MAGIC||info.abi!=rixgeo::ABI||
     info.pool_bytes!=rixgeo::POOL_WORDS*4||info.max_vertices!=rixgeo::MAX_VERTICES||
     info.state_words!=rixgeo::STATE_WORDS||info.vertex_offset_words!=rixgeo::VERTEX_OFFSET||
     info.carry_offset_words!=rixgeo::CARRY_OFFSET||info.output_offset_words!=rixgeo::OUTPUT_OFFSET||
     info.record_words!=rixgeo::RECORD_WORDS||info.max_records!=rixgeo::MAX_RECORDS||info.profile_magic!=0x4a324731||info.reserved)
   throw std::runtime_error("RIX_GEOMETRY driver/profile ABI mismatch");
  void*p=mmap(nullptr,rixgeo::POOL_WORDS*4,PROT_READ|PROT_WRITE,MAP_SHARED,fd_,0);
  if(p==MAP_FAILED)throw std::runtime_error("RIX_GEOMETRY coherent mmap failed");pool_=static_cast<uint32_t*>(p);
 }
public:
 bool enabled()const{return enabled_;}
 void recordCpuVertices(unsigned count){cpuVertices_+=count;}
 Device()=default;Device(const Device&)=delete;Device&operator=(const Device&)=delete;
 ~Device(){
  const char*p=std::getenv("RIX_JAVA_GEOMETRY_STATS");
  if(p){FILE*f=std::fopen(p,"w");if(f){std::fprintf(f,"{\"phase\":\"after_renderer_destroy\",\"enabled\":%s,\"draws\":%llu,\"jobs\":%llu,\"vertices\":%llu,\"records\":%llu,\"CPU_geometry_vertices\":%llu}\n",enabled_?"true":"false",(unsigned long long)draws_,(unsigned long long)jobs_,(unsigned long long)vertices_,(unsigned long long)records_,(unsigned long long)cpuVertices_);std::fclose(f);}}
  if(pool_)munmap(pool_,rixgeo::POOL_WORDS*4);if(fd_>=0)::close(fd_);
 }
 void beginDraw(){if(!enabled_)return;open();if(++sequence_==0)throw std::runtime_error("RIX_GEOMETRY draw sequence exhausted");submitted_=0;++draws_;}
 template<class Fetch,class Emit>bool push(unsigned count,const Fetch&fetch,rr::vertextransformer::VertexTransformerData&context,
                                            bool scissor,const int32_t*box,uint32_t rasterMask,const Emit&emit){
  if(!enabled_||!sequence_||!pool_)throw std::runtime_error("RIX_GEOMETRY draw not initialized");
  uint32_t encoded[rixgeo::STATE_WORDS]={};int32_t clip[4];std::memcpy(clip,box,sizeof(clip));
  if(!rixgeo::state<false>(encoded,context,scissor,clip,rasterMask))throw std::runtime_error("RIX_GEOMETRY invalid state");
  std::memcpy(pool_,encoded,encoded[2]*4);
  unsigned chunk=1020;
  if(context.primitiveAssembler.mode==DrawMode::TRIANGLE_STRIP||context.primitiveAssembler.mode==DrawMode::TRIANGLE_FAN||
     context.primitiveAssembler.mode==DrawMode::QUAD_STRIP||context.primitiveAssembler.mode==DrawMode::POLYGON)chunk=512;
  if(context.primitiveAssembler.mode==DrawMode::POINTS||context.primitiveAssembler.mode==DrawMode::LINES||
     context.primitiveAssembler.mode==DrawMode::LINE_LOOP||context.primitiveAssembler.mode==DrawMode::LINE_STRIP)chunk=128;
  // Up to 7 user-plane fan triangles, each split into 7 frustum triangles:
  // 7*(7*3 band records + 1 stencil record) = 154 records/new strip vertex.
  if(context.planeClipper.enabledMask)chunk=64;
  for(unsigned start=0;start<count;){
   unsigned n=std::min(chunk,count-start);uint32_t*target=pool_+rixgeo::VERTEX_OFFSET;
   for(unsigned i=0;i<n;i++){
    const auto vertex=fetch(start+i);
    for(unsigned j=0;j<4;j++)*target++=rixgeo::bits(vertex.vertex[j]);
    for(unsigned j=0;j<4;j++)*target++=rixgeo::bits(vertex.color[j]);
    for(unsigned t=0;t<2;t++)for(unsigned j=0;j<4;j++)*target++=rixgeo::bits(vertex.tex[t][j]);
    for(unsigned j=0;j<3;j++)*target++=rixgeo::bits(vertex.normal[j]);*target++=rixgeo::bits(vertex.pointSize);
   }
   rix_geometry_job job{};job.mode=submitted_?2:1;job.count=n;job.sequence=sequence_;
   std::atomic_thread_fence(std::memory_order_seq_cst);
   if(ioctl(fd_,RIX_GEOMETRY_SUBMIT,&job))throw std::runtime_error("RIX_GEOMETRY ioctl errno="+std::to_string(errno));
   std::atomic_thread_fence(std::memory_order_seq_cst);
   if(job.status||job.records>rixgeo::MAX_RECORDS||job.reserved||job.reserved_out[0]||job.reserved_out[1])
    throw std::runtime_error("RIX_GEOMETRY job status="+std::to_string(job.status));
   ++jobs_;vertices_+=n;records_+=job.records;submitted_+=n;
   for(unsigned row=0;row<job.records;row++){
    const uint32_t*p=pool_+rixgeo::OUTPUT_OFFSET+row*64;
    if((p[0]!=49&&p[0]!=2)||!p[1]||(p[1]&~7u))throw std::runtime_error("RIX_GEOMETRY malformed output record");
    if(p[0]==49&&(p[2]!=0x300000c0||p[1]==7||(p[1]&(p[1]-1))))throw std::runtime_error("RIX_GEOMETRY malformed triangle output");
    if(p[0]==2&&(p[2]!=(op::RENDER_CONFIG|StencilReg::getAddr())||p[1]!=7))throw std::runtime_error("RIX_GEOMETRY malformed stencil output");
    if(!emit(p[1],p+2,p[0]))return false;
   }
   start+=n;
  }
  return true;
 }
};
}
