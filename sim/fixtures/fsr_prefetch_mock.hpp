// SPDX-License-Identifier: MIT
// Deterministic host adapters for the production prefetch scheduler/Kernel.
#pragma once
#include <algorithm>
#include <map>
#include <string>
#include <limits>
namespace fsr_prefetch_mock {
struct FailStop:std::runtime_error{using std::runtime_error::runtime_error;};
struct Event {std::string kind;uint64_t us;uint32_t tag;unsigned mode;};
struct Env {
 uint64_t now=0,kernel_done=0,copy_start=0,ready_at=0,state_entered=0,post_ack_at=0;
 uint64_t snapshot_delay=17000,load_duration=5500,stop_at=std::numeric_limits<uint64_t>::max();
 std::vector<uint64_t> compute_durations{97000};std::vector<uint32_t> forced_frames;
 std::vector<Event> events;std::map<unsigned,uint32_t> kernel_regs;
 uint32_t token=0,frame=0,status=0,expired=0,cached_tag=0,post=1,active=1,result_tag=0;
 unsigned mode=0,compute_count=0,snapshot_count=0,stop_after_compute=0;
 bool kernel_active=false,done_valid=false,quarantined=false,receipt_revoked=false;
 bool cancel_early_request=false,never_complete=false,never_drain=false,inject_load_expiry=false;
 bool throw_after_early_request=false;
 bool expire_before_load_start=false;
 bool canceled=false,load_lease_violation=false,bank_violation=false,cache_overlap=false;
 uint64_t early_request_at=0;
 void event(const std::string&kind,uint32_t tag=0){events.push_back({kind,now,tag,mode});}
 void update(){
  if(now>=stop_at&&!rix_pl::stopped()){rix_pl::stop(0);event("STOP");}
  if(post!=active&&now>=post_ack_at){active=post;event("POST_ACK",active);}
  if(status&&now-state_entered>=2000000){++expired;event("EXPIRE",token);if((status&3)==2){canceled=true;status|=0x100;state_entered=now;}else status=0;}
  if((status&3)==1&&now>=copy_start){status=2;state_entered=now;event("COPY_START",token);}
  if((status&3)==2&&now>=ready_at&&!never_drain){status=canceled?0:3;state_entered=now;canceled=false;event(status?"READY":"DRAIN_DONE",token);}
  if(cancel_early_request&&early_request_at&&now>=early_request_at+3000&&status){cancel_early_request=false;status=0;event("CANCEL",token);}
  if(kernel_active&&now>=kernel_done&&!never_complete){
   kernel_active=false;done_valid=true;result_tag=mode==2?0:cached_tag;event("K_DONE",result_tag);
   if(mode==1&&stop_after_compute&&compute_count>=stop_after_compute){rix_pl::stop(0);event("STOP");}
   if(mode==0&&inject_load_expiry){inject_load_expiry=false;status=0;++expired;event("EXPIRE_DURING_LOAD",token);}
  }
 }
};
inline Env*env=nullptr;
struct MockTime {
 static rix_pl::Clock::time_point now(){env->update();return rix_pl::Clock::time_point(std::chrono::microseconds(env->now));}
 static void sleep_us(unsigned us){env->now+=us;env->update();}
};
struct MockMap {
 uint64_t base;void*p=nullptr;
 MockMap(int,uint64_t address,size_t):base(address){}
 uint32_t read(unsigned reg){
  env->update();
  if(base==0xa0040000){
   if(reg==0){if(env->kernel_active)return 0;uint32_t value=4|(env->done_valid?2:0);return value;}
   if(reg==0x10)return 0;
   if(reg==0x38)return env->result_tag;
   if(reg==0x3c){bool valid=env->done_valid;env->done_valid=false;if(valid)env->event("TAG_VALIDATED",env->result_tag);return valid;}
   return env->kernel_regs[reg];
  }
  switch(reg){case 0x54:return env->post;case 0x58:return env->active;
   case 0x7c:return env->status;case 0x80:return env->token;case 0x84:return env->frame;
   case 0x8c:return env->expired;case 0x94:return 2000;default:return 0;}
 }
 void write(unsigned reg,uint32_t value){
  env->update();
  if(base==0xa0040000){
   env->kernel_regs[reg]=value;
   if(reg==0x30&&env->kernel_regs[0x18]==0&&env->expire_before_load_start){env->expire_before_load_start=false;env->status=0;++env->expired;env->event("EXPIRE_BEFORE_LOAD_START");}
   if(reg!=0)return;
   if(env->kernel_active){env->cache_overlap=true;throw std::runtime_error("mock overlapping HLS commands");}
   env->mode=env->kernel_regs[0x18];env->kernel_active=true;env->done_valid=false;
   unsigned mode=env->mode;
   if(mode==0){
    if(env->status!=3||env->frame!=env->kernel_regs[0x30])env->load_lease_violation=true;
    env->cached_tag=env->kernel_regs[0x30];env->kernel_done=env->now+env->load_duration;env->event("LOAD_START",env->cached_tag);
   }else if(mode==1){
    unsigned bank=(env->kernel_regs[0x28]-0x21000000)/0x200000;
    if(env->post!=env->active||bank==((env->active>>9)&1))env->bank_violation=true;
    size_t index=std::min<size_t>(env->compute_count,env->compute_durations.size()-1);
    env->kernel_done=env->now+env->compute_durations[index];++env->compute_count;env->event("COMPUTE_START",env->cached_tag);
   }else{env->cached_tag=0;env->kernel_done=env->now+100;env->event("INVALIDATE");}
   return;
  }
  if(reg==0x78){
   if(env->status||value==env->token)throw std::runtime_error("mock SNP request violated idle/token contract");
   env->token=value;env->status=1;env->state_entered=env->now;env->copy_start=env->now+1000;
   env->ready_at=env->now+env->snapshot_delay;++env->snapshot_count;
   size_t i=env->snapshot_count-1;
   env->frame=i<env->forced_frames.size()?env->forced_frames[i]:uint32_t(100+env->now/16667);
   if(env->kernel_active&&env->mode==1){env->early_request_at=env->now;env->event("PREFETCH_REQUEST",value);if(env->throw_after_early_request){env->throw_after_early_request=false;throw std::runtime_error("injected progress failure");}}
   else env->event("FALLBACK_REQUEST",value);
  }else if(reg==0x80){
   if(env->kernel_active&&env->mode==0)throw std::runtime_error("mock canceled in-flight LOAD");
   env->event("SNP_RELEASE",value);
   if(env->token==value){if((env->status&3)==2){env->canceled=true;env->status|=0x100;}else env->status=0;}
  }else if(reg==0x54){env->post=value;env->post_ack_at=env->now+16000;env->event("POST_SUBMIT",value);}
 }
};
}
