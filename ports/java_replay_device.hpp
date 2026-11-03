// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "renderer/IDevice.hpp"
#include <cstdint>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <vector>

namespace rr::java_replay {
// Parse only the real two-TMU GPU command stream, never CPU virtual opcodes.
inline uint32_t swapsIn(tcb::span<const uint8_t> data){
    if(data.size()%4)throw std::runtime_error("Replay command alignment");
    std::size_t p=0;uint32_t swaps=0;
    while(p<data.size()){
        uint32_t w;std::memcpy(&w,data.data()+p,4);p+=4;
        const uint32_t op=w>>28;std::size_t bytes=0;
        switch(op){
        case 0:break;
        case 1:bytes=4;break;
        case 2:if((w&0x14)==0x14)++swaps;break;
        case 3:bytes=w&0x0fffffff;if(bytes!=192)throw std::runtime_error("Replay requires exact dual-TMU triangle layout");break;
        case 4:bytes=w&0x0fffffff;if(bytes!=256)throw std::runtime_error("Replay fog payload");break;
        case 5:bytes=std::size_t(w&0x7ffff)*4;if(((w>>19)&3)>1)throw std::runtime_error("Replay TMU index");break;
        default:throw std::runtime_error("Replay unsupported GPU opcode");
        }
        if(bytes>data.size()-p)throw std::runtime_error("Replay truncated GPU payload");p+=bytes;
    }
    return swaps;
}
struct Event {uint32_t kind,index,address;std::vector<uint8_t> bytes;};
struct Frame {std::vector<Event> events;uint32_t swaps=0;};
// Ordinary capture memory owns all bytes. Original DDU owns DMA headers and
// slot completion. No resource/renderer ABI or floating-point changes.
class Device final:public IDevice {
public:
    static constexpr std::size_t byteLimit=64*1024*1024,eventLimit=8192;
    explicit Device(IDevice& raw):m_raw(raw){}
    void enableResourceShadow(){if(m_swaps||m_shadowEnabled)throw std::runtime_error("Replay resource shadow phase");m_shadowEnabled=true;m_memory.resize(24*1024*1024);m_valid.resize(12288);m_dirty.resize(12288);}
    tcb::span<uint8_t> requestDisplayListBuffer(uint8_t i)override{return m_raw.requestDisplayListBuffer(i);}
    uint8_t getDisplayListBufferCount()const override{return m_raw.getDisplayListBufferCount();}
    void blockUntilDeviceIsIdle()override{m_raw.blockUntilDeviceIsIdle();}
    void streamDisplayList(uint8_t i,uint32_t size)override{
        std::lock_guard<std::mutex> lock(m_lock);
        auto source=m_raw.requestDisplayListBuffer(i);
        if(size>source.size())throw std::out_of_range("Replay source size");
        const auto swaps=swapsIn({source.data(),size});
        if(m_recording){append(1,i,0,{source.data(),size});m_current.swaps+=swaps;}
        m_raw.streamDisplayList(i,size);m_swaps+=swaps;
    }
    bool writeToDeviceMemory(tcb::span<const uint8_t> data,uint32_t address)override{
        std::lock_guard<std::mutex> lock(m_lock);
        if(m_shadowEnabled){
            if(address<0x00800000||address>=0x02000000||data.size()>0x02000000-address||address%2048||data.size()%2048)throw std::runtime_error("Replay shadow requires complete texture pages");
            const auto first=(address-0x00800000)/2048;
            for(std::size_t p=0;p<data.size()/2048;++p){m_valid[first+p]=1;if(m_recording)m_dirty[first+p]=1;}
            std::memcpy(m_memory.data()+address-0x00800000,data.data(),data.size());
        }
        if(m_recording)append(2,0,address,data);
        return m_raw.writeToDeviceMemory(data,address);
    }
    bool readFromDeviceMemory(tcb::span<uint8_t> data,uint32_t address)override{
        std::lock_guard<std::mutex> lock(m_lock);
        if(m_recording)throw std::runtime_error("Replay capture cannot hide device readback");
        return m_raw.readFromDeviceMemory(data,address);
    }
    // Caller joins both renderer queues before changing capture phase.
    void begin(){std::lock_guard<std::mutex> lock(m_lock);if(m_recording||!m_frames.empty())throw std::runtime_error("Replay capture already used");if(m_shadowEnabled){m_initial=m_memory;m_initialValid=m_valid;}m_recording=true;}
    void endFrame(){std::lock_guard<std::mutex> lock(m_lock);if(!m_recording||m_current.events.empty()||m_current.swaps!=1)throw std::runtime_error("Replay boundary is not one complete frame");m_frames.push_back(std::move(m_current));m_current=Frame{};if(m_frames.size()==3){m_recording=false;buildRestore();}}
    void cancel(){std::lock_guard<std::mutex> lock(m_lock);m_recording=false;}
    uint64_t swapsSubmitted()const{return m_swaps;}
    const std::vector<Frame>& frames()const{return m_frames;}
    std::size_t capturedBytes()const{return m_bytes;}
    const std::vector<Event>&resourceRestore()const{return m_restore;}
    std::size_t restoreBytes()const{std::size_t n=0;for(const auto&e:m_restore)n+=e.bytes.size();return n;}
    void restoreResources(){std::lock_guard<std::mutex> lock(m_lock);if(m_recording)throw std::runtime_error("Replay restore while recording");for(const auto&e:m_restore){m_raw.blockUntilDeviceIsIdle();if(!m_raw.writeToDeviceMemory({e.bytes},e.address))throw std::runtime_error("Replay initial resource restore failed");}m_raw.blockUntilDeviceIsIdle();}
    void replay(const Frame& frame){
        std::lock_guard<std::mutex> lock(m_lock);
        if(m_recording||frame.swaps!=1)throw std::runtime_error("Replay phase");
        for(const auto&e:frame.events){
            m_raw.blockUntilDeviceIsIdle();
            if(e.kind==1){
                auto dest=m_raw.requestDisplayListBuffer(e.index);
                if(e.bytes.size()>dest.size())throw std::out_of_range("Replay DMA capacity");
                std::memcpy(dest.data(),e.bytes.data(),e.bytes.size());
                const auto swaps=swapsIn({e.bytes});m_raw.streamDisplayList(e.index,e.bytes.size());m_swaps+=swaps;
            }else if(e.kind==2){if(!m_raw.writeToDeviceMemory({e.bytes},e.address))throw std::runtime_error("Replay texture write failed");}
            else throw std::runtime_error("Replay event kind");
        }
        m_raw.blockUntilDeviceIsIdle();
    }
private:
    void buildRestore(){
        if(!m_shadowEnabled)return;
        for(std::size_t p=0;p<m_dirty.size();){
            if(!m_dirty[p]||!m_initialValid[p]){++p;continue;}
            const auto first=p;while(p<m_dirty.size()&&p-first<32&&m_dirty[p]&&m_initialValid[p])++p;
            const auto begin=m_initial.begin()+first*2048,end=m_initial.begin()+p*2048;
            m_restore.push_back({2,0,uint32_t(0x00800000+first*2048),{begin,end}});
        }
    }
    void append(uint32_t kind,uint32_t index,uint32_t address,tcb::span<const uint8_t> bytes){
        if(m_events==eventLimit||bytes.size()>byteLimit-m_bytes)throw std::runtime_error("Replay capture bound exceeded");
        if(kind==2&&(address>0x02000000||bytes.size()>0x02000000-address))throw std::runtime_error("Replay memory range");
        m_current.events.push_back({kind,index,address,{bytes.begin(),bytes.end()}});m_bytes+=bytes.size();++m_events;
    }
    IDevice&m_raw;std::mutex m_lock;bool m_recording=false;uint64_t m_swaps=0;
    std::size_t m_bytes=0,m_events=0;Frame m_current;std::vector<Frame>m_frames;
    bool m_shadowEnabled=false;std::vector<uint8_t>m_memory,m_initial,m_valid,m_initialValid,m_dirty;std::vector<Event>m_restore;
};
}
