// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "java_prepared_arrays.hpp"
#include <atomic>
#include <cstdint>
#include <memory>

namespace java_queued {
inline bool enabled() {
    static const bool value=[] {const char* p=std::getenv("RIX_JAVA_QUEUED_ARRAYS");return p&&p[0]=='1'&&p[1]=='\0';}();
    return value;
}
// The owner keeps every array referenced by View alive. View captures missing
// attributes at call time; matrices and other state remain in the command stream.
struct Batch {
    std::shared_ptr<const void> owner;
    java_prepared::View view;
    std::size_t count,sourceBytes,first=0;
    Batch(std::shared_ptr<const void> keep,const java_prepared::View& input,
          std::size_t n,std::size_t bytes):owner(std::move(keep)),view(input),count(n),sourceBytes(bytes) {}
};
using BatchPtr=std::shared_ptr<const Batch>;
// Producer-owned retention, one instance per CPU command buffer. Clear only
// after streamDisplayList has joined the previous reader of that buffer.
class Retained {
public:
    static constexpr std::size_t byteLimit=32*1024*1024, countLimit=4096;
    bool needsDrain(const Batch& batch) const {
        return !batches.empty()&&(batches.size()>=countLimit||bytes>=byteLimit||batch.sourceBytes>byteLimit-bytes);
    }
    void add(const BatchPtr& batch){batches.push_back(batch);bytes+=batch->sourceBytes;}
    void removeLast(){bytes-=batches.back()->sourceBytes;batches.pop_back();}
    void clear(){batches.clear();bytes=0;}
    std::size_t size()const{return batches.size();}
private:
    std::vector<BatchPtr> batches;
    std::size_t bytes=0;
};
struct Statistics {
    std::atomic<unsigned long long> submitted{0},submittedVertices{0},consumed{0},consumedVertices{0},retentionDrains{0};
};
inline Statistics& statistics(){static Statistics value;return value;}
inline void flushStatistics(){
    const char* path=std::getenv("RIX_JAVA_QUEUED_STATS");if(!path)return;
    if(FILE* file=std::fopen(path,"w")){
        const auto& s=statistics();
        std::fprintf(file,"{\"enabled\":%s,\"submitted_batches\":%llu,\"submitted_vertices\":%llu,\"consumed_batches\":%llu,\"consumed_vertices\":%llu,\"retention_drains\":%llu}\n",
            enabled()?"true":"false",s.submitted.load(),s.submittedVertices.load(),s.consumed.load(),s.consumedVertices.load(),s.retentionDrains.load());
        std::fclose(file);
    }
}
inline bool logging(){static const bool value=[] {if(!std::getenv("RIX_JAVA_QUEUED_STATS"))return false;(void)statistics();std::atexit(flushStatistics);return true;}();return value;}
inline void submitted(std::size_t n){if(logging()){statistics().submitted.fetch_add(1,std::memory_order_relaxed);statistics().submittedVertices.fetch_add(n,std::memory_order_relaxed);}}
inline void consumed(std::size_t n){if(logging()){statistics().consumed.fetch_add(1,std::memory_order_relaxed);statistics().consumedVertices.fetch_add(n,std::memory_order_relaxed);}}
inline void drained(){if(logging())statistics().retentionDrains.fetch_add(1,std::memory_order_relaxed);}
} // namespace java_queued
