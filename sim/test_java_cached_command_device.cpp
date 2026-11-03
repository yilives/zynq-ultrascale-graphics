// SPDX-License-Identifier: GPL-3.0-or-later
#include "java_cached_command_device.hpp"
#include <array>
#include <cassert>
#include <future>
#include <iostream>
#include <thread>
using namespace rr;
struct FakeDevice:IDevice{
    std::array<std::vector<uint8_t>,7> buffers;
    std::vector<std::vector<uint8_t>> captured;
    std::future<void> pending;bool busy=false;unsigned waits=0,stores=0,loads=0;
    explicit FakeDevice(std::size_t capacity){for(auto& b:buffers)b.resize(capacity,0xa5);}
    ~FakeDevice(){blockUntilDeviceIsIdle();}
    void streamDisplayList(uint8_t id,uint32_t size)override{
        assert(!busy);busy=true;
        pending=std::async(std::launch::async,[this,id,size]{std::this_thread::sleep_for(std::chrono::milliseconds(1));captured.emplace_back(buffers[id].begin(),buffers[id].begin()+size);});
    }
    void blockUntilDeviceIsIdle()override{waits++;if(pending.valid())pending.get();busy=false;}
    tcb::span<uint8_t> requestDisplayListBuffer(uint8_t id)override{assert(id<7&&!busy);return {buffers[id]};}
    uint8_t getDisplayListBufferCount()const override{return 7;}
    bool writeToDeviceMemory(tcb::span<const uint8_t>,uint32_t)override{stores++;return true;}
    bool readFromDeviceMemory(tcb::span<uint8_t>,uint32_t)override{loads++;return true;}
};
int main(){
    {FakeDevice raw(128);java_cached::CommandDevice pass(raw,false);auto buffer=pass.requestDisplayListBuffer(0);assert(buffer.data()==raw.buffers[0].data());buffer[0]=0x31;pass.streamDisplayList(0,1);pass.blockUntilDeviceIsIdle();assert(raw.captured[0]==std::vector<uint8_t>{0x31});assert(pass.statistics().copies==0&&pass.statistics().allocatedBytes==0);}
    for(std::size_t capacity:{std::size_t(257),std::size_t(1048568)}){
        FakeDevice raw(capacity);java_cached::CommandDevice cache(raw,true);
        auto a=cache.requestDisplayListBuffer(0),b=cache.requestDisplayListBuffer(1);
        assert(a.data()!=raw.buffers[0].data()&&b.data()!=raw.buffers[1].data());
        assert(cache.requestDisplayListBuffer(0).data()==a.data());
        std::vector<std::vector<uint8_t>> expected;
        for(unsigned round=0;round<12;round++){
            const unsigned id=round%2;auto out=id?b:a;const std::size_t count=round%3==0?capacity:round%3==1?3:65;
            for(std::size_t i=0;i<count;i++)out[i]=uint8_t(i*17+round);
            expected.emplace_back(out.begin(),out.begin()+count);
            cache.streamDisplayList(id,count);
            // Shadow reuse after copy must not corrupt the asynchronous reader.
            std::fill(out.begin(),out.begin()+count,0xcc);
        }
        cache.blockUntilDeviceIsIdle();assert(raw.captured==expected);
        const auto& stats=cache.statistics();assert(stats.submissions==12&&stats.copies==12&&stats.bytes==stats.copiedBytes&&stats.allocatedBytes==capacity*2);
        bool index=false,size=false;try{cache.requestDisplayListBuffer(7);}catch(const std::out_of_range&){index=true;}
        try{cache.streamDisplayList(0,capacity+1);}catch(const std::out_of_range&){size=true;}assert(index&&size);
        uint8_t bytes[8]{};assert(cache.writeToDeviceMemory({bytes,8},0)&&cache.readFromDeviceMemory({bytes,8},0));assert(raw.stores==1&&raw.loads==1);
    }
    std::cout<<"JAVA_CACHED_DEVICE_PASS passthrough=1 exact_bytes=1 async_slot_reuse=1 stable_shadow=1 bounds=1 texture_passthrough=1\n";
}
