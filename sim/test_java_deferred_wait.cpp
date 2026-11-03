// SPDX-License-Identifier: GPL-3.0-or-later
#include "DeferredDeviceDataUploader.hpp"
#include "RenderConfigs.hpp"
#include <array>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>
struct Fake final:rr::IBusConnector{
 std::array<std::vector<uint8_t>,8>tx;std::vector<uint8_t>rx=std::vector<uint8_t>(4096);std::vector<std::vector<uint8_t>>seen;int pending=-1;unsigned length=0,waits=0;bool fail=false;
 Fake(){for(auto&v:tx)v.resize(4096);}
 void writeData(uint8_t i,uint32_t n,uint32_t offset=0)override{assert(!offset&&pending<0&&n<=4096);if(fail){fail=false;throw std::runtime_error("Injected send failure");}pending=i;length=n;}
 void readData(uint8_t,uint32_t n)override{assert(pending<0&&n<=rx.size());std::fill(rx.begin(),rx.end(),0x5a);}
 void blockUntilTransferIsComplete()override{++waits;if(pending>=0){seen.emplace_back(tx[pending].begin(),tx[pending].begin()+length);pending=-1;}}
 tcb::span<uint8_t>requestWriteBuffer(uint8_t i)override{return{tx.at(i)};}
 tcb::span<uint8_t>requestReadBuffer(uint8_t)override{return{rx};}
 uint8_t getWriteBufferCount()const override{return 8;}
 uint8_t getReadBufferCount()const override{return 1;}
};
int main(int argc,char**argv){
 const bool defer=argc>1&&std::strcmp(argv[1],"1")==0;setenv("RIX_JAVA_TEXTURE_DEDUP","1",1);setenv("RIX_JAVA_DEFER_TEXTURE_WAIT",defer?"1":"0",1);
 Fake b;rr::devicedatauploader::DeferredDeviceDataUploader d(b);const auto base=rr::RenderConfig::TEXTURE_POOL_OFFSET;std::vector<uint8_t>data(rr::RenderConfig::TEXTURE_PAGE_SIZE,0x37);
 assert(d.getDisplayListBufferCount()==7);assert(d.writeToDeviceMemory({data},base)&&b.pending==7);const auto before=b.waits;
 assert(d.writeToDeviceMemory({data},base));assert(b.waits-before==(defer?0:1));assert((b.pending==7)==defer);
 std::fill(data.begin(),data.end(),0x49);assert(d.writeToDeviceMemory({data},base));d.blockUntilDeviceIsIdle();assert(b.seen.size()==2);
 for(unsigned i=0;i<2;++i){assert(b.seen[i].size()==data.size()+8);for(std::size_t n=8;n<b.seen[i].size();++n)assert(b.seen[i][n]==(i?0x49:0x37));}
 assert(d.writeToDeviceMemory({data},base));auto command=d.requestDisplayListBuffer(0);std::fill(command.begin(),command.begin()+64,0);d.streamDisplayList(0,4);assert(b.pending==0);d.blockUntilDeviceIsIdle();
 std::vector<uint8_t>result(16);assert(d.readFromDeviceMemory({result},base));assert(result==std::vector<uint8_t>(16,0x5a)&&b.pending<0);
 b.fail=true;std::fill(data.begin(),data.end(),0x55);bool threw=false;try{d.writeToDeviceMemory({data},base);}catch(const std::runtime_error&){threw=true;}assert(threw);const auto sent=b.seen.size();assert(d.writeToDeviceMemory({data},base));d.blockUntilDeviceIsIdle();assert(b.seen.size()==sent+1);
 std::cout<<"JAVA_DEFERRED_WAIT_UNIT_PASS mode="<<defer<<" hit_during_dma=1 miss_fence=1 unchanged_payload=1 stream_fence=1 read_fence=1 failure_invalidation=1\n";
}
