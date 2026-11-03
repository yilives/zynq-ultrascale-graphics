// SPDX-License-Identifier: MIT
#pragma once
#include "cnn_fsr_pl.hpp"
#include <type_traits>

namespace rix_cnn_fsr_poll {
using rix_cnn_fsr::require;
struct Wait {
 static auto now(){return rix_pl::Clock::now();}
 static void pause(){usleep(100);}
};
struct Failure {
 [[noreturn]] static void stop(const char*why){rix_cnn_fsr::fail_stop(why);}
};

// One AP transaction, owned until DONE even during exception unwinding.
// Registers outlive this owner. Signals never cancel a hardware AXI master.
template<class Registers,class Timing=Wait,class Fault=Failure> class Pending {
 Registers&r;
 bool active=false,done_seen=false;
 uint32_t wanted_tag=0,wanted_return=0;
 decltype(Timing::now()) started{};
public:
 struct Completion{uint64_t residency_us=0,foreground_wait_us=0;};
 uint64_t started_count=0,completed_count=0,status_reads=0;
 explicit Pending(Registers&regs):r(regs){}
 Pending(const Pending&)=delete;
 Pending&operator=(const Pending&)=delete;
 ~Pending()noexcept{
  try{if(active)finish();invalidate();}
  catch(...){Fault::stop("FSR drain/invalidate failed during teardown; retaining ownership");}
 }
 bool inflight()const noexcept{return active;}
 void begin(unsigned mode,uint32_t source,uint32_t output,uint32_t tag,uint32_t expected_tag,unsigned expected_return=0){
  require(!active,"FSR command already pending");
  const auto control=r.read(0);
  if(!(control&4)||(control&0x81))Fault::stop("FSR is not idle or auto-restart is enabled");
  r.read(0x3c); // Read-clear a stale result-valid before the new transaction.
  r.write(0x18,mode);r.write(0x20,source);r.write(0x28,output);r.write(0x30,tag);
  wanted_tag=expected_tag;wanted_return=expected_return;
  active=true;done_seen=false;started=Timing::now();started_count++;r.write(0,1);
 }
 // AP_DONE is read-clear: once observed, only finish() may consume it.
 bool ready(){
  require(active,"No FSR command is pending");
  if(!done_seen){
   const auto control=r.read(0);status_reads++;
   if(control&0x80)Fault::stop("FSR auto-restart enabled while command pending");
   done_seen=control&2;
   if(!done_seen&&Timing::now()-started>std::chrono::seconds(10))Fault::stop("FSR AXI completion timeout: cold boot required");
  }
  return done_seen;
 }
 Completion finish(){
  require(active,"No FSR command is pending");
  const auto wait_started=Timing::now();
  while(!ready())Timing::pause();
  // DONE certifies AXI retirement. Check return/tag before any bank submission.
  active=false;done_seen=false;rix_pl::barrier();completed_count++;
  require(r.read(0x10)==wanted_return,"FSR command returned an error");
  require((r.read(0x3c)&1)&&r.read(0x38)==wanted_tag,"FSR result tag mismatch");
  const auto now=Timing::now();
  return {uint64_t(std::chrono::duration_cast<std::chrono::microseconds>(now-started).count()),
          uint64_t(std::chrono::duration_cast<std::chrono::microseconds>(now-wait_started).count())};
 }
 uint32_t call(unsigned mode,uint32_t source,uint32_t output,uint32_t tag,uint32_t expected_tag,unsigned expected_return=0){
  begin(mode,source,output,tag,expected_tag,expected_return);return uint32_t(finish().residency_us);
 }
 void invalidate(){call(2,0,0,0,0);}
};

// Member order makes the pending owner drain before the mapping is unmapped.
struct Kernel {
 rix_pl::Map registers;
 Pending<rix_pl::Map> command;
 explicit Kernel(int fd):registers(fd,0xa0040000,65536),command(registers){}
 Kernel(const Kernel&)=delete;
 Kernel&operator=(const Kernel&)=delete;
 bool inflight()const noexcept{return command.inflight();}
 void begin(unsigned mode,uint32_t source,uint32_t output,uint32_t tag,uint32_t expected_tag,unsigned expected_return=0){command.begin(mode,source,output,tag,expected_tag,expected_return);}
 bool ready(){return command.ready();}
 auto finish(){return command.finish();}
 uint32_t call(unsigned mode,uint32_t source,uint32_t output,uint32_t tag,uint32_t expected_tag,unsigned expected_return=0){return command.call(mode,source,output,tag,expected_tag,expected_return);}
 void invalidate(){command.invalidate();}
};
}
