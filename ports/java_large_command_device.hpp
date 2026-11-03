// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "renderer/IDevice.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace rr::java_large {
inline bool enabledFromEnv(){const char*p=std::getenv("RIX_JAVA_CACHED_COMMANDS");return p&&std::strcmp(p,"1")==0;}
// Larger CPU-owned IF bands, transported by the unmodified DDU and DMA ABI.
// A packet boundary never inserts a framebuffer commit/load/swap or a NOP.
class CommandDevice final:public IDevice {
public:
    struct Statistics {uint64_t submissions=0,bytes=0,copies=0,copiedBytes=0,packets=0,splits=0,allocatedBytes=0,maxBody=0;};
    explicit CommandDevice(IDevice&raw,bool enabled=enabledFromEnv()):m_raw(raw),m_enabled(enabled),m_buffers(raw.getDisplayListBufferCount()){
        if(m_buffers.empty()||m_buffers.size()>7)throw std::runtime_error("Large command slot count");
        m_capacity=raw.requestDisplayListBuffer(0).size();
        if(m_capacity<512||m_capacity>1024*1024||m_capacity%4)throw std::runtime_error("Large command raw capacity");
        std::fprintf(stderr,"JAVA_CACHED_COMMAND_DEVICE enabled=%u buffers=%zu large_band=1\n",unsigned(m_enabled),m_buffers.size());
    }
    tcb::span<uint8_t>requestDisplayListBuffer(uint8_t i)override{
        if(i>=m_buffers.size())throw std::out_of_range("Large command index");
        if(!m_enabled)return m_raw.requestDisplayListBuffer(i);
        auto&b=m_buffers[i];if(b.empty()){b.resize(2*m_capacity);m_stats.allocatedBytes+=b.size();}return{b};
    }
    uint8_t getDisplayListBufferCount()const override{return m_raw.getDisplayListBufferCount();}
    void blockUntilDeviceIsIdle()override{m_raw.blockUntilDeviceIsIdle();}
    bool writeToDeviceMemory(tcb::span<const uint8_t>d,uint32_t a)override{return m_raw.writeToDeviceMemory(d,a);}
    bool readFromDeviceMemory(tcb::span<uint8_t>d,uint32_t a)override{return m_raw.readFromDeviceMemory(d,a);}
    void streamDisplayList(uint8_t i,uint32_t size)override{
        if(i>=m_buffers.size())throw std::out_of_range("Large command index");
        if(!m_enabled){if(size>m_capacity)throw std::out_of_range("Raw command size");m_raw.streamDisplayList(i,size);++m_stats.packets;}
        else{
            if(m_buffers[i].empty()||size>m_buffers[i].size()||size%4)throw std::out_of_range("Large command size");
            // Validate the entire oversized stream before the first submission.
            std::vector<std::size_t>ends;
            if(size<=m_capacity)ends.push_back(size);
            else{
                std::size_t p=0,begin=0,last=0;
                while(p<size){
                    const auto end=commandEnd(m_buffers[i],p,size);
                    if(end-p>m_capacity)throw std::runtime_error("One GPU command exceeds DMA capacity");
                    if(end-begin>m_capacity){if(last<=begin)throw std::runtime_error("No GPU boundary");ends.push_back(last);begin=last;}
                    p=end;last=end;
                }
                ends.push_back(size);
            }
            std::size_t begin=0;
            for(auto end:ends){
                m_raw.blockUntilDeviceIsIdle();auto target=m_raw.requestDisplayListBuffer(i);
                if(target.size()!=m_capacity)throw std::runtime_error("DMA command capacity changed");
                const auto n=end-begin;std::memcpy(target.data(),m_buffers[i].data()+begin,n);
                m_raw.streamDisplayList(i,uint32_t(n));++m_stats.copies;++m_stats.packets;m_stats.copiedBytes+=n;begin=end;
            }
            if(ends.size()>1)m_stats.splits+=ends.size()-1;
        }
        ++m_stats.submissions;m_stats.bytes+=size;if(size>m_stats.maxBody)m_stats.maxBody=size;
    }
    const Statistics&statistics()const{return m_stats;}
    void finishStatistics()const{
        const char*p=std::getenv("RIX_JAVA_CACHED_COMMAND_STATS");if(!p)return;FILE*f=std::fopen(p,"wx");if(!f)throw std::runtime_error("Large command statistics exist/cannot open");
        std::fprintf(f,"{\"phase\":\"after_renderer_destroy\",\"enabled\":%s,\"large_band\":true,\"submissions\":%llu,\"bytes\":%llu,\"copies\":%llu,\"copied_bytes\":%llu,\"dma_packets\":%llu,\"boundary_splits\":%llu,\"allocated_bytes\":%llu,\"raw_capacity\":%zu,\"logical_capacity\":%zu,\"max_body\":%llu}\n",m_enabled?"true":"false",(unsigned long long)m_stats.submissions,(unsigned long long)m_stats.bytes,(unsigned long long)m_stats.copies,(unsigned long long)m_stats.copiedBytes,(unsigned long long)m_stats.packets,(unsigned long long)m_stats.splits,(unsigned long long)m_stats.allocatedBytes,m_capacity,m_enabled?2*m_capacity:m_capacity,(unsigned long long)m_stats.maxBody);
        if(std::fclose(f))throw std::runtime_error("Large command statistics close");
    }
private:
    static std::size_t commandEnd(const std::vector<uint8_t>&b,std::size_t p,std::size_t size){
        if(size-p<4)throw std::runtime_error("GPU header truncated");uint32_t w;std::memcpy(&w,b.data()+p,4);p+=4;std::size_t n=0;
        switch(w>>28){
        case 0:case 2:break;
        case 1:n=4;break;
        case 3:n=w&0xfffffff;if(n!=192)throw std::runtime_error("GPU dual-TMU triangle layout");break;
        case 4:n=w&0xfffffff;if(n!=256)throw std::runtime_error("GPU fog layout");break;
        case 5:if(((w>>19)&3)>1)throw std::runtime_error("GPU texture unit");n=std::size_t(w&0x7ffff)*4;break;
        default:throw std::runtime_error("Unknown GPU opcode");
        }
        if(n>size-p)throw std::runtime_error("GPU payload truncated");return p+n;
    }
    IDevice&m_raw;bool m_enabled;std::size_t m_capacity;std::vector<std::vector<uint8_t>>m_buffers;Statistics m_stats;
};
}
