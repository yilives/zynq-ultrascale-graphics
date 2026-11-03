// SPDX-License-Identifier: MIT
#pragma once
#include "pl_frames.hpp"
#include <fstream>
#include <sstream>
#include <iostream>
#include <sys/stat.h>
namespace rix_cnn_fsr {
using namespace rix_pl;
inline void require(bool condition,const char*why){if(!condition)throw std::runtime_error(why);}
inline std::string line(const char*path){std::ifstream f(path);std::string s;std::getline(f,s);require(bool(f),"identity unavailable");return s;}
inline void gate(){
 require(geteuid()==0,"root required");
 require(access("/tmp/rix-fsr-pl.quarantine",F_OK)!=0,"FSR is quarantined");
 int fd=open("/tmp/rix-cnn-group-r1/active-receipt.txt",O_RDONLY|O_NOFOLLOW);require(fd>=0,"NGR1 active receipt absent");
 struct stat st{};bool valid=fstat(fd,&st)==0&&S_ISREG(st.st_mode)&&st.st_uid==0&&!(st.st_mode&0077)&&st.st_size>0&&st.st_size<512;
 if(!valid){close(fd);throw std::runtime_error("invalid NGR1 receipt permissions");}
 std::string text(size_t(st.st_size),'\0');auto count=read(fd,text.data(),text.size());close(fd);require(count==ssize_t(text.size()),"short NGR1 receipt");
 std::istringstream stream(text);std::string format,boot,bit,source,extra;
 require(bool(std::getline(stream,format))&&bool(std::getline(stream,boot))&&bool(std::getline(stream,bit))&&bool(std::getline(stream,source))&&!std::getline(stream,extra),"invalid NGR1 receipt");
 require(format=="RIX_CNN_GROUP_ACTIVE_V1"&&boot==line("/proc/sys/kernel/random/boot_id")&&
  bit=="c7e5f78f059a68e679b8f2fed7a1284d81ea5f3fdd8fd93c2351b51f0fe8e4d2"&&
  source=="7dfef24c11c2799e3a212774859bb349f28507aa1f0b587e86b26508a7b34c31","FSR requires this boot's verified NGR1 image");
}
[[noreturn]] inline void fail_stop(const char*why){
 sigset_t blocked;sigfillset(&blocked);sigprocmask(SIG_BLOCK,&blocked,nullptr);
 int fd=open("/tmp/rix-fsr-pl.quarantine",O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW,0600);
 if(fd>=0){auto n=write(fd,why,strlen(why));if(n>=0)fsync(fd);close(fd);}
 unlink("/tmp/rix-cnn-group-r1/active-receipt.txt");
 std::cerr<<"CNN_FSR_QUARANTINE "<<why<<"; retaining hardware ownership until reset\n"<<std::flush;
 for(;;)pause();
}
struct Kernel {
 Map r;bool inflight=false;
 explicit Kernel(int fd):r(fd,0xa0040000,65536){}
 ~Kernel(){if(!inflight){try{invalidate();}catch(...){fail_stop("FSR invalidate failed during teardown");}}}
 uint32_t call(unsigned mode,uint32_t source,uint32_t output,uint32_t tag,uint32_t expected_tag,unsigned expected_return=0){
  require(!inflight,"FSR command already pending");
  uint32_t control=r.read(0);if(!(control&4)||(control&0x81))fail_stop("FSR is not idle or auto-restart is enabled");
  r.read(0x3c); // Clear the previous result-valid indication.
  r.write(0x18,mode);r.write(0x20,source);r.write(0x28,output);r.write(0x30,tag);
  inflight=true;auto start=Clock::now();r.write(0,1);
  // Signals request shutdown; they must never abandon an AXI reader/writer.
  while(!(r.read(0)&2)){
   if(Clock::now()-start>std::chrono::seconds(10)){
    fail_stop("FSR AXI completion timeout: cold boot is required before starting another client");
   }
   usleep(100);
  }
  inflight=false;barrier();
  require(r.read(0x10)==expected_return,"FSR command returned an error");
  require((r.read(0x3c)&1)&&r.read(0x38)==expected_tag,"FSR result tag mismatch");
  return uint32_t(std::chrono::duration_cast<std::chrono::microseconds>(Clock::now()-start).count());
 }
 void invalidate(){call(2,0,0,0,0);}
};
}
