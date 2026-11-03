// SPDX-License-Identifier: GPL-3.0-or-later
#include "java_replay_device.hpp"
#include <cassert>
#include <iostream>
struct Memory final:rr::IDevice{
    std::vector<uint8_t>slot=std::vector<uint8_t>(4096);
    std::vector<rr::java_replay::Event>writes;
    tcb::span<uint8_t>requestDisplayListBuffer(uint8_t i)override{assert(i==0);return{slot};}
    uint8_t getDisplayListBufferCount()const override{return 1;}
    void blockUntilDeviceIsIdle()override{}
    void streamDisplayList(uint8_t i,uint32_t n)override{assert(i==0&&n==4);}
    bool writeToDeviceMemory(tcb::span<const uint8_t>d,uint32_t a)override{writes.push_back({2,0,a,{d.begin(),d.end()}});return true;}
    bool readFromDeviceMemory(tcb::span<uint8_t>,uint32_t)override{return true;}
};
int main(){
    Memory raw;rr::java_replay::Device d(raw);d.enableResourceShadow();
    std::vector<uint8_t>a(65536,3),b(2048,4),changed(65536,9);
    d.writeToDeviceMemory({a},0x800000);d.writeToDeviceMemory({b},0x812000);d.begin();
    for(unsigned i=0;i<3;++i){
        d.writeToDeviceMemory({changed},0x800000);d.writeToDeviceMemory({changed.data(),2048},0x812000);
        // A newly allocated page has no valid initial contents to restore.
        d.writeToDeviceMemory({changed.data(),2048},0x818000);
        uint32_t swap=0x20000014;std::memcpy(raw.slot.data(),&swap,4);d.streamDisplayList(0,4);d.endFrame();
    }
    assert(d.restoreBytes()==65536+2048&&d.resourceRestore().size()==2);
    raw.writes.clear();d.restoreResources();assert(raw.writes.size()==2);
    assert(raw.writes[0].address==0x800000&&raw.writes[0].bytes==a);
    assert(raw.writes[1].address==0x812000&&raw.writes[1].bytes==b);
    for(const auto&f:d.frames())d.replay(f);
    d.restoreResources();assert(raw.writes.back().bytes==b);
    std::cout<<"JAVA_REPLAY_SHADOW_PASS initial_versions=1 cyclic_restore=1 bounded_64k=1 new_pages_not_fabricated=1\n";
}
