// SPDX-License-Identifier: MIT
#include "frame_pipeline.hpp"
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

using rix_frames::FramePipeline;
using Buffer=std::vector<uint32_t>;
static unsigned checks=0;
static void check(bool result,const char*description){
 ++checks;if(!result)throw std::runtime_error(description);
}
template<class Function> static bool logic_error(Function action){
 try{action();}catch(const std::logic_error&){return true;}return false;
}
static void fill(Buffer&buffer,unsigned frame){
 uint32_t value=0x9e3779b9u^frame;
 for(auto&pixel:buffer){value^=value<<13;value^=value>>17;value^=value<<5;pixel=value;}
}
static uint64_t hash(const Buffer&buffer){
 uint64_t value=1469598103934665603ull;
 for(auto pixel:buffer){value^=pixel;value*=1099511628211ull;}
 return value;
}
static uint64_t oracle(unsigned frame){Buffer reference(1024);fill(reference,frame);return hash(reference);}
struct Read {bool success;unsigned frame;uint64_t fingerprint;std::thread::id worker;};
struct Gate {
 std::mutex mutex;std::condition_variable condition;bool arrived=false,opened=false;
 void arrive_and_wait(){std::unique_lock<std::mutex> guard(mutex);arrived=true;condition.notify_all();condition.wait(guard,[&]{return opened;});}
 bool await_arrival(){std::unique_lock<std::mutex> guard(mutex);return condition.wait_for(guard,std::chrono::seconds(5),[&]{return arrived;});}
 void open(){std::lock_guard<std::mutex> guard(mutex);opened=true;condition.notify_all();}
};
// Declared after a pipeline so an assertion failure still unblocks its job
// before the pipeline destructor waits. Tests must not depend on sleep timing.
struct ReleaseGate {Gate&gate;~ReleaseGate(){gate.open();}};

static void success_and_failure(){
 Buffer source(1024),candidate(1024);fill(source,7);
 const auto main_id=std::this_thread::get_id();
 Gate gate;FramePipeline<Read> next;ReleaseGate unblock{gate};
 check(!next.pending()&&!next.valid(),"new pipeline is empty");
 check(logic_error([&]{next.take();}),"empty take rejects");
 next.start([&]{fill(candidate,11);gate.arrive_and_wait();return Read{true,11,hash(candidate),std::this_thread::get_id()};});
 check(gate.await_arrival(),"async read really starts before take");
 check(next.pending()&&next.valid(),"unconsumed read is pending");
 check(hash(source)==oracle(7),"candidate writes cannot change current source");
 std::atomic<bool> duplicate_called{false};
 check(logic_error([&]{next.start([&]{duplicate_called=true;return Read{};});}),"duplicate start rejects");
 check(!duplicate_called,"rejected callable was not executed");
 gate.open();auto result=next.take();
 check(!next.pending(),"successful take consumes future");
 check(result.success&&result.frame==11&&result.fingerprint==oracle(11),"result metadata matches candidate");
 check(result.worker!=main_id,"explicit async uses another thread");
 source.swap(candidate);
 check(hash(source)==result.fingerprint,"accepting candidate pairs source and frame");

 Gate stopped;ReleaseGate unblock_stop{stopped};
 next.start([&]{fill(candidate,99);stopped.arrive_and_wait();return Read{false,99,hash(candidate),std::this_thread::get_id()};});
 check(stopped.await_arrival(),"stopped candidate was written before cancellation");
 check(hash(source)==oracle(11),"incomplete next read preserves submitted source");
 stopped.open();result=next.take();
 check(!result.success&&!next.pending(),"false result is consumed");
 // The caller deliberately does not swap an unsuccessful read.
 check(hash(source)==oracle(11),"SIGTERM-like failed read leaves last frame paired");

 next.start([]()->Read{throw std::runtime_error("injected read failure");});
 bool propagated=false;
 try{next.take();}catch(const std::runtime_error&error){propagated=std::string(error.what())=="injected read failure";}
 check(propagated,"worker exception reaches take caller");
 check(!next.pending(),"exceptional take consumes future");
 next.start([]{return Read{true,12,123,std::this_thread::get_id()};});
 check(next.take().frame==12,"pipeline is reusable after exception");
}

static void discard_and_owner_lifetime(){
 std::atomic<bool> joined{false},owner_released{false},release_before_join{false};
 Buffer source(1024),candidate(1024);fill(source,21);
 Gate gate;
 struct Owner {
  std::atomic<bool>&joined,&released,&bad;
  ~Owner(){if(!joined.load())bad=true;released=true;}
 };
 {
  Owner resource{joined,owner_released,release_before_join};
  FramePipeline<Read> next;ReleaseGate unblock{gate};
  next.start([&]{
   fill(candidate,22);gate.arrive_and_wait();
   if(owner_released.load())throw std::runtime_error("resource released during read");
   joined=true;return Read{true,22,hash(candidate),std::this_thread::get_id()};
  });
  check(gate.await_arrival(),"discard case has an outstanding real read");
  check(hash(source)==oracle(21),"duration exit keeps submitted source unchanged");
  // Simulate duration expiry: no take, no swap, no additional submitted frame.
 }
 check(joined&&owner_released&&!release_before_join,"pending destructor joins before captured owner release");
 check(hash(source)==oracle(21),"successful but unused prefetch was discarded");

 joined=false;owner_released=false;release_before_join=false;
 Gate failed;
 try{
  Owner resource{joined,owner_released,release_before_join};
  FramePipeline<Read> next;ReleaseGate unblock{failed};
  next.start([&]()->Read{
   failed.arrive_and_wait();joined=true;
   throw std::runtime_error("injected exception after lease acquisition");
  });
  check(failed.await_arrival(),"exception case has acquired fake lease");
  throw std::runtime_error("main stage failed");
 }catch(const std::runtime_error&error){
  check(std::string(error.what())=="main stage failed","destructor preserves original main-stage exception");
 }
 check(joined&&owner_released&&!release_before_join,"exception unwind joins before fake lease release");
}

static void repeated_handoffs(){
 Buffer source(1024),candidate(1024);FramePipeline<Read> next;
 unsigned accepted=0;
 for(unsigned frame=1;frame<=256;frame++){
  const auto previous=hash(source);
  next.start([&,frame]{fill(candidate,frame);return Read{frame%7!=0,frame,hash(candidate),std::this_thread::get_id()};});
  auto read=next.take();
  check(read.fingerprint==oracle(frame),"repeat result identifies its own frame");
  if(read.success){source.swap(candidate);accepted++;check(hash(source)==oracle(frame),"repeat accepted source matches frame");}
  else check(hash(source)==previous,"repeat rejected source preserves previous frame");
  check(!next.pending(),"repeat has exactly one consumed read");
 }
 check(accepted==220,"failed reads do not inflate accepted frame count");
}

int main(){try{
 success_and_failure();discard_and_owner_lifetime();repeated_handoffs();
 std::cout<<"{\"passed\":true,\"checks\":"<<checks<<",\"cases\":[\"gated-success\",\"stop-after-write\",\"duplicate-start\",\"worker-exception\",\"duration-discard\",\"unwind-owner-order\",\"256-handoffs\"]}\n";
 return 0;
}catch(const std::exception&error){std::cerr<<"frame pipeline test: "<<error.what()<<'\n';return 1;}}
