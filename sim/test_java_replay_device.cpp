// SPDX-License-Identifier: GPL-3.0-or-later
#include "java_replay_device.hpp"
#include <array>
#include <cassert>
#include <iostream>
using rr::java_replay::Event;
struct Fake final:rr::IDevice {
    std::array<std::vector<uint8_t>,2>slots{std::vector<uint8_t>(4096),std::vector<uint8_t>(4096)};
    std::vector<Event>observed;int pending=-1;uint32_t size=0;
    tcb::span<uint8_t>requestDisplayListBuffer(uint8_t i)override{return{slots.at(i)};}
    uint8_t getDisplayListBufferCount()const override{return 2;}
    void blockUntilDeviceIsIdle()override{if(pending>=0){observed.push_back({1,uint32_t(pending),0,{slots[pending].begin(),slots[pending].begin()+size}});pending=-1;}}
    void streamDisplayList(uint8_t i,uint32_t n)override{blockUntilDeviceIsIdle();pending=i;size=n;}
    bool writeToDeviceMemory(tcb::span<const uint8_t>d,uint32_t a)override{blockUntilDeviceIsIdle();observed.push_back({2,0,a,{d.begin(),d.end()}});return true;}
    bool readFromDeviceMemory(tcb::span<uint8_t>,uint32_t)override{return true;}
};
template<class F>void rejected(F fn){bool threw=false;try{fn();}catch(const std::exception&){threw=true;}assert(threw);}
static void word(std::vector<uint8_t>&b,uint32_t w){const auto*p=reinterpret_cast<const uint8_t*>(&w);b.insert(b.end(),p,p+4);}
int main(){
    Fake raw;rr::java_replay::Device d(raw);d.begin();
    for(unsigned frame=0;frame<3;++frame){
        std::vector<uint8_t>texture{uint8_t(frame),1,2,3};assert(d.writeToDeviceMemory({texture},128+frame*4));
        std::vector<uint8_t>commands;word(commands,0x10000003);word(commands,0x12345678+frame);
        word(commands,0x300000c0);commands.resize(commands.size()+192,uint8_t(frame+17));
        word(commands,0x40000100);commands.resize(commands.size()+256,7);
        word(commands,0x50080002);word(commands,0x60800000);word(commands,0x60800800);
        word(commands,0x20000014);word(commands,0);
        auto target=d.requestDisplayListBuffer(frame%2);std::memcpy(target.data(),commands.data(),commands.size());
        d.streamDisplayList(frame%2,commands.size());d.blockUntilDeviceIsIdle();d.endFrame();
        texture[0]=99;std::fill(target.begin(),target.end(),0xaa);
    }
    assert(d.frames().size()==3&&d.swapsSubmitted()==3);
    auto expected=raw.observed;raw.observed.clear();
    for(const auto&f:d.frames())d.replay(f);
    assert(d.swapsSubmitted()==6&&raw.observed.size()==expected.size());
    for(std::size_t i=0;i<expected.size();++i){const auto&a=expected[i];const auto&b=raw.observed[i];assert(a.kind==b.kind&&a.index==b.index&&a.address==b.address&&a.bytes==b.bytes);}
    rejected([&]{d.begin();});
    for(uint32_t bad:{0xb0000000u,0x300000bcu,0x40000008u,0x50100000u}){std::vector<uint8_t>b;word(b,bad);rejected([&]{rr::java_replay::swapsIn({b});});}
    std::vector<uint8_t>shortTri;word(shortTri,0x300000c0);rejected([&]{rr::java_replay::swapsIn({shortTri});});
    Fake other;rr::java_replay::Device capture(other);capture.begin();std::vector<uint8_t>data(4);
    rejected([&]{capture.readFromDeviceMemory({data},0);});
    rejected([&]{capture.writeToDeviceMemory({data},0x02000000);});
    std::cout<<"JAVA_REPLAY_DEVICE_PASS ordered_store_stream=1 immutable_bytes=1 async_slot_reuse=1 swaps=1 parser_bounds=1 capture_phase=1\n";
}
