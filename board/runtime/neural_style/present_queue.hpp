// SPDX-License-Identifier: MIT
#pragma once
#include <chrono>
#include <cstdint>
#include <stdexcept>
#include <unistd.h>

namespace rix_pl {
struct FlipWait {
 static auto now(){return std::chrono::steady_clock::now();}
 static void pause(){usleep(1000);}
};

// PST1 acknowledges a bank only at accepted_prepare = prepare && scan_idle.
// The old reader has drained before that acknowledgement crosses back to PS.
// Keep at most one submitted bank: compute the next frame while it waits for
// scanout, then retire it BEFORE acquiring/writing the now inactive bank.
template<class Registers,class Wait=FlipWait> class PresentQueue {
 Registers&r;
 const uint32_t mode;
 const bool overlap;
 bool pending=false,reserved=false;
 unsigned reserved_bank=0;
 uint32_t word=0;
 uint64_t submitted_count=0,completed_count=0;
 double waited=0;
 void retire(){
  if(!pending)return;
  const auto started=Wait::now(),deadline=started+std::chrono::seconds(2);
  while(r.read(0x58)!=word){
   if(Wait::now()>=deadline)throw std::runtime_error("native output flip timeout");
   Wait::pause();
  }
  waited+=std::chrono::duration<double>(Wait::now()-started).count();
  pending=false;completed_count++;
 }
public:
 PresentQueue(Registers&regs,uint32_t display_mode,bool allow_overlap):r(regs),mode(display_mode),overlap(allow_overlap){
  if(mode!=2&&mode!=3)throw std::runtime_error("invalid neural display mode");
 }
 unsigned acquire(){
  if(reserved)throw std::runtime_error("display bank already reserved");
  retire();reserved_bank=((r.read(0x58)>>9)&1)^1;reserved=true;
  return reserved_bank;
 }
 void submit(unsigned bank){
  if(pending||!reserved||bank!=reserved_bank||bank>1)throw std::runtime_error("display bank ownership mismatch");
  if(((r.read(0x58)>>9)&1)==bank)throw std::runtime_error("display bank became active before submission");
  word=mode|(bank<<9);r.write(0x54,word);reserved=false;pending=true;submitted_count++;
  if(!overlap)retire();
 }
 void finish(){
  if(reserved)throw std::runtime_error("unsubmitted display bank");
  retire();
 }
 uint64_t submitted()const{return submitted_count;}
 uint64_t completed()const{return completed_count;}
 double wait_seconds()const{return waited;}
};
}
