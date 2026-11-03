// SPDX-License-Identifier: MIT
#pragma once
#include <future>
#include <stdexcept>
#include <utility>

namespace rix_frames {
// One background read, owned and controlled by the calling thread. The job
// itself must not call this object's methods. Declare this owner AFTER every
// buffer, Snapshot and mapping captured by its callable, so it joins before
// those resources are destroyed, including during exception unwinding.
template<class T> class FramePipeline {
 std::future<T> job;
public:
 FramePipeline()=default;
 FramePipeline(const FramePipeline&)=delete;
 FramePipeline& operator=(const FramePipeline&)=delete;
 FramePipeline(FramePipeline&&)=delete;
 FramePipeline& operator=(FramePipeline&&)=delete;
 ~FramePipeline(){if(job.valid())job.wait();}
 bool pending()const noexcept{return job.valid();}
 bool valid()const noexcept{return pending();}
 template<class Callable> void start(Callable&& callable){
  if(pending())throw std::logic_error("frame pipeline already has an unconsumed read");
  // Force a worker; a deferred future would serialize the stages at take().
  job=std::async(std::launch::async,std::forward<Callable>(callable));
 }
 T take(){
  if(!pending())throw std::logic_error("frame pipeline has no pending read");
  // get() consumes the future even when it propagates the worker exception.
  return job.get();
 }
};
}
