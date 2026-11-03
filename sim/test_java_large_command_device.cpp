// SPDX-License-Identifier: GPL-3.0-or-later
#include "java_large_command_device.hpp"
#include <array>
#include <cassert>
#include <iostream>
struct Fake final:rr::IDevice{
 std::array<std::vector<uint8_t>,7>b;std::vector<uint8_t>received;unsigned packets=0;int pending=-1;uint32_t size=0;unsigned stores=0,reads=0;
 Fake(){for(auto&v:b)v.resize(1024);}
 tcb::span<uint8_t>requestDisplayListBuffer(uint8_t i)override{return{b.at(i)};}
 uint8_t getDisplayListBufferCount()const override{return 7;}
 void blockUntilDeviceIsIdle()override{if(pending>=0){received.insert(received.end(),b[pending].begin(),b[pending].begin()+size);pending=-1;}}
 void streamDisplayList(uint8_t i,uint32_t n)override{assert(pending<0);assert(n<=1024);pending=i;size=n;++packets;}
 bool writeToDeviceMemory(tcb::span<const uint8_t>,uint32_t a)override{assert(a==128);++stores;return true;}
 bool readFromDeviceMemory(tcb::span<uint8_t>,uint32_t a)override{assert(a==128);++reads;return true;}
};
template<class F>void reject(F fn){bool yes=false;try{fn();}catch(const std::exception&){yes=true;}assert(yes);}
void word(std::vector<uint8_t>&b,uint32_t w){const auto*p=reinterpret_cast<const uint8_t*>(&w);b.insert(b.end(),p,p+4);}
int main(){
 Fake raw;rr::java_large::CommandDevice d(raw,true);std::vector<uint8_t>commands;
 for(unsigned i=0;i<8;++i){word(commands,0x10000003);word(commands,i);word(commands,0x300000c0);commands.resize(commands.size()+192,uint8_t(i));}
 word(commands,0x40000100);commands.resize(commands.size()+256,12);word(commands,0x50080002);word(commands,0x60800000);word(commands,0x60800800);word(commands,0x20000014);
 assert(commands.size()>1024&&commands.size()<2048);
 auto dst=d.requestDisplayListBuffer(3);assert(dst.size()==2048);std::memcpy(dst.data(),commands.data(),commands.size());d.streamDisplayList(3,commands.size());std::fill(dst.begin(),dst.end(),0xaa);d.blockUntilDeviceIsIdle();assert(raw.received==commands&&raw.packets==2);
 auto stats=d.statistics();assert(stats.splits==1&&stats.copies==2&&stats.copiedBytes==commands.size());
 std::array<uint8_t*,7>addresses{};for(unsigned i=0;i<7;++i)addresses[i]=d.requestDisplayListBuffer(i).data();for(unsigned i=0;i<7;++i)assert(addresses[i]==d.requestDisplayListBuffer(i).data());assert(d.statistics().allocatedBytes==7*2048);
 reject([&]{d.requestDisplayListBuffer(7);});reject([&]{d.streamDisplayList(3,2049);});
 std::fill(dst.begin(),dst.end(),0);uint32_t bad=0xb0000000;std::memcpy(dst.data()+1500,&bad,4);const auto before=raw.packets;reject([&]{d.streamDisplayList(3,1800);});assert(raw.packets==before);
 uint32_t tri=0x300000c0;std::fill(dst.begin(),dst.end(),0);std::memcpy(dst.data()+1700,&tri,4);reject([&]{d.streamDisplayList(3,1800);});assert(raw.packets==before);
 std::vector<uint8_t>texture(2048);assert(d.writeToDeviceMemory({texture},128));assert(d.readFromDeviceMemory({texture},128));assert(raw.stores==1&&raw.reads==1);
 Fake offraw;rr::java_large::CommandDevice off(offraw,false);assert(off.requestDisplayListBuffer(0).data()==offraw.b[0].data());off.streamDisplayList(0,8);off.blockUntilDeviceIsIdle();assert(off.statistics().allocatedBytes==0);
 std::cout<<"JAVA_CACHED_DEVICE_PASS passthrough=1 exact_bytes=1 async_slot_reuse=1 stable_shadow=1 bounds=1 texture_passthrough=1\nJAVA_LARGE_COMMAND_DEVICE_PASS boundary_splits=1 atomic_validation=1 bounded_capacity=1 no_framebuffer_insertion=1\n";
}
