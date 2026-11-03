// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "renderer/IDevice.hpp"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace rr::java_cached {
inline bool enabledFromEnv(){const char* v=std::getenv("RIX_JAVA_CACHED_COMMANDS");return v&&std::strcmp(v,"1")==0;}
// Only GPU command bodies are staged. The underlying DDU still owns headers,
// texture transfers, DMA-slot status, submission and completion semantics.
class CommandDevice final:public IDevice {
public:
    struct Statistics {unsigned long long submissions=0,bytes=0,copies=0,copiedBytes=0,waitNs=0,copyNs=0,allocatedBytes=0;};
    explicit CommandDevice(IDevice& raw,bool enabled=enabledFromEnv()):m_raw(raw),m_enabled(enabled),m_timed(std::getenv("RIX_JAVA_CACHED_COMMAND_STATS")!=nullptr),m_buffers(raw.getDisplayListBufferCount()){
        std::fprintf(stderr,"JAVA_CACHED_COMMAND_DEVICE enabled=%u buffers=%zu\n",unsigned(m_enabled),m_buffers.size());
    }
    tcb::span<uint8_t> requestDisplayListBuffer(uint8_t index) override {
        if(!m_enabled)return m_raw.requestDisplayListBuffer(index);
        if(index>=m_buffers.size())throw std::out_of_range("Cached command buffer index");
        auto raw=m_raw.requestDisplayListBuffer(index);auto& buffer=m_buffers[index];
        if(buffer.empty()){buffer.resize(raw.size());m_stats.allocatedBytes+=raw.size();}
        if(buffer.size()!=raw.size())throw std::runtime_error("Command buffer capacity changed");
        return {buffer};
    }
    void streamDisplayList(uint8_t index,uint32_t size) override {
        if(m_enabled){
            if(index>=m_buffers.size()||m_buffers[index].empty()||size>m_buffers[index].size())throw std::out_of_range("Cached command body size");
            // Completion must precede every write to the real DMA slot.
            const auto begin=m_timed?Clock::now():Clock::time_point{};
            m_raw.blockUntilDeviceIsIdle();
            const auto ready=m_timed?Clock::now():Clock::time_point{};
            auto destination=m_raw.requestDisplayListBuffer(index);
            if(destination.size()!=m_buffers[index].size())throw std::runtime_error("Command destination capacity changed");
            std::memcpy(destination.data(),m_buffers[index].data(),size);
            if(m_timed){m_stats.waitNs+=ns(ready-begin);m_stats.copyNs+=ns(Clock::now()-ready);}
            m_stats.copies++;m_stats.copiedBytes+=size;
        }
        m_raw.streamDisplayList(index,size);m_stats.submissions++;m_stats.bytes+=size;
    }
    uint8_t getDisplayListBufferCount() const override{return m_raw.getDisplayListBufferCount();}
    bool writeToDeviceMemory(tcb::span<const uint8_t> data,uint32_t address)override{return m_raw.writeToDeviceMemory(data,address);}
    bool readFromDeviceMemory(tcb::span<uint8_t> data,uint32_t address)override{return m_raw.readFromDeviceMemory(data,address);}
    void blockUntilDeviceIsIdle()override{m_raw.blockUntilDeviceIsIdle();}
    const Statistics& statistics()const{return m_stats;}
    void finishStatistics()const {
        const char* path=std::getenv("RIX_JAVA_CACHED_COMMAND_STATS");if(!path)return;
        FILE* file=std::fopen(path,"w");if(!file)throw std::runtime_error("Cannot write cached command statistics");
        std::fprintf(file,"{\"phase\":\"after_renderer_destroy\",\"enabled\":%s,\"submissions\":%llu,\"bytes\":%llu,\"copies\":%llu,\"copied_bytes\":%llu,\"wait_ns\":%llu,\"copy_ns\":%llu,\"allocated_bytes\":%llu}\n",m_enabled?"true":"false",m_stats.submissions,m_stats.bytes,m_stats.copies,m_stats.copiedBytes,m_stats.waitNs,m_stats.copyNs,m_stats.allocatedBytes);
        std::fclose(file);
    }
private:
    using Clock=std::chrono::steady_clock;
    static unsigned long long ns(Clock::duration duration){return std::chrono::duration_cast<std::chrono::nanoseconds>(duration).count();}
    IDevice& m_raw;const bool m_enabled,m_timed;
    std::vector<std::vector<uint8_t>> m_buffers;
    Statistics m_stats;
};
}
