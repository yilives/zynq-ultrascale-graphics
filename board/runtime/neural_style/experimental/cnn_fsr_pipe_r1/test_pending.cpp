// SPDX-License-Identifier: MIT
#include "fsr_pending.hpp"
#include <map>
#include <string>
#include <iostream>
#include <vector>
static unsigned checks=0;
static void check(bool x,const char*why){checks++;if(!x)throw std::runtime_error(why);}
template<class F>static void rejected(F f){bool caught=false;try{f();}catch(const std::runtime_error&){caught=true;}check(caught,"unsafe operation was accepted");}
struct Clock {
 static inline int64_t us=0;
 static auto now(){return std::chrono::steady_clock::time_point(std::chrono::microseconds(us));}
 static void pause(){us+=100;}
};
struct Fault {[[noreturn]]static void stop(const char*why){throw std::runtime_error(why);}};
struct Registers {
 std::map<unsigned,uint32_t> values;
 std::vector<std::string> events;
 bool busy=false,done=false,valid=false,auto_restart=false;
 bool wrong_tag=false,bad_return=false,stuck=false;
 int64_t until=0;
 unsigned starts=0,finishes=0;
 uint32_t read(unsigned offset){
  if(busy&&!stuck&&Clock::us>=until){
   busy=false;done=true;valid=true;finishes++;events.push_back("done");
   values[0x10]=bad_return?7:(values[0x18]==99?2:0);
   values[0x38]=wrong_tag?values[0x30]+1:values[0x30];
  }
  if(offset==0){auto v=(busy?1u:4u)|(done?2u:0u)|(auto_restart?128u:0u);done=false;return v;}
  if(offset==0x3c){auto v=valid?1u:0u;valid=false;return v;}
  return values[offset];
 }
 void write(unsigned offset,uint32_t value){
  if(offset==0){check(value==1&&!busy,"start while busy");busy=true;done=false;until=Clock::us+800;
   starts++;events.push_back(values[0x18]==2?"invalidate":"start");
  }else{check(!busy,"argument changed before DONE");values[offset]=value;}
 }
};
using Pending=rix_cnn_fsr_pipe::Pending<Registers,Clock,Fault>;
int main(){try{
 static_assert(!std::is_copy_constructible_v<Pending>);
 {
  Registers r;Pending p(r);p.begin(1,0,0x21200000,42,42);
  check(p.inflight(),"pending state absent");const auto count=r.events.size();
  rejected([&]{p.begin(0,0,0,43,43);});check(r.events.size()==count,"rejected begin touched hardware");
  // Work on another independent accelerator while FSR runs; return late.
  Clock::us+=1500;auto c=p.finish();check(c.residency_us==1500&&c.foreground_wait_us==0,"deferred timing accounting");
  check(!p.inflight()&&p.started_count==p.completed_count,"completion accounting");
  rejected([&]{p.finish();});
  check(p.call(99,0,0,0,0,2)==800,"synchronous protocol regression");
 }
 {
  Registers r;{Pending p(r);p.begin(1,0,0x21000000,100,100);rix_pl::stop(SIGTERM);}
  check(r.starts==2&&r.finishes==2&&!r.busy,"destructor did not drain then invalidate");
  check(r.events==std::vector<std::string>({"start","done","invalidate","done"}),"invalidation preceded AXI retirement");
  rix_pl::stopped()=0;
 }
 for(bool tag:{false,true}){
  Registers r;Pending p(r);p.begin(1,0,0x21200000,1000,1000);r.wrong_tag=tag;r.bad_return=!tag;
  rejected([&]{p.finish();});check(!r.busy&&!p.inflight(),"error returned before AXI retirement");
  r.wrong_tag=r.bad_return=false;
 }
 {
  Registers r;Pending p(r);r.auto_restart=true;rejected([&]{p.begin(1,0,0,1,1);});
  check(r.starts==0,"auto-restart core was started");r.auto_restart=false;
  p.begin(1,0,0,2,2);r.stuck=true;Clock::us+=10000100;
  rejected([&]{p.finish();});check(p.inflight()&&r.busy,"timeout abandoned AXI owner");
  rejected([&]{p.begin(1,0,0,3,3);});r.stuck=false;p.finish();
 }
 // Unwinding must complete the transaction before the resource is destroyed.
 {
  Registers r;try{Pending p(r);p.begin(1,0,0x21000000,88,88);throw std::runtime_error("downstream failure");}catch(const std::runtime_error&){}
  check(!r.busy&&r.starts==r.finishes&&r.starts==2,"exception teardown left hardware active");
 }
 std::cout<<"{\"passed\":true,\"checks\":"<<checks<<",\"destructor_drains\":true,\"timeout_keeps_owner\":true,\"tag_faults_rejected\":true}\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
