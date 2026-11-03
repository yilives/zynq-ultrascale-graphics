// SPDX-License-Identifier: GPL-3.0-or-later
// Run the real connector/DDU/three-strip renderer against a memory DMA device.
#include "DMAProxyBusConnector.hpp"
#include "RIXGL.hpp"
#include "vertexpipeline/VertexPipeline.hpp"
#include "StdThreadRunner.hpp"
#include "renderer/devicedatauploader/DeviceDataUploader.hpp"
#include "renderer/threadedvertextransformer/ThreadedVertexTransformer.hpp"
#include <array>
#include <cassert>
#include <cerrno>
#include <cstdarg>
#include <cstring>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include "kernel/dma-proxy/files/include/dma-proxy.h"

static channel_buffer* mapped[2]{};
static bool oldAbi=false;
static uint32_t lastTx=UINT32_MAX;
static constexpr size_t mapBytes=sizeof(channel_buffer)*BUFFER_COUNT;
extern "C" void* __real_mmap(void*,size_t,int,int,int,off_t);
extern "C" int __real_munmap(void*,size_t);
extern "C" int __wrap_open(const char* name,int,...) {
    if(!std::strcmp(name,"/dev/dma_proxy_tx")) return 100;
    if(!std::strcmp(name,"/dev/dma_proxy_rx")) return 101;
    errno=ENOENT;return -1;
}
extern "C" int __wrap_close(int fd) {assert(fd==100||fd==101);return 0;}
extern "C" void* __wrap_mmap(void* address,size_t length,int prot,int,int fd,off_t offset) {
    assert((fd==100||fd==101)&&length==mapBytes&&offset==0);
    auto p=__real_mmap(address,length,prot,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(p!=MAP_FAILED);mapped[fd-100]=static_cast<channel_buffer*>(p);return p;
}
extern "C" int __wrap_munmap(void* p,size_t length) {
    assert(length==mapBytes);
    for(auto& entry:mapped) if(entry==p) entry=nullptr;
    return __real_munmap(p,length);
}
extern "C" int __wrap_ioctl(int fd,unsigned long command,...) {
    va_list args;va_start(args,command);auto value=va_arg(args,uint32_t*);va_end(args);
    assert(fd==100||fd==101);
    if(command==RIX_DMA_GET_ABI) {*value=oldAbi?1:RIX_DMA_ABI_VERSION;return 0;}
    assert(*value<BUFFER_COUNT&&mapped[fd-100]);
    auto& buffer=mapped[fd-100][*value];
    if(command==START_XFER) {
        assert(buffer.length&&buffer.length<=BUFFER_SIZE&&!(buffer.length&3));
        buffer.status=PROXY_BUSY;if(fd==100) lastTx=*value;
    } else if(command==FINISH_XFER) buffer.status=PROXY_NO_ERROR;
    else {errno=ENOTTY;return -1;}
    return 0;
}

int main(int argc,char** argv) {
    oldAbi=argc>1&&std::string(argv[1])=="--old-abi";
    try {
        rr::DMAProxyBusConnector bus;
        assert(!oldAbi);
        if(BUFFER_COUNT==4) {
            bool reproduced=false;
            try {bus.requestWriteBuffer(4);} catch(const std::out_of_range& error) {
                reproduced=std::string(error.what())=="TX buffer index";
            }
            assert(reproduced);std::cout<<"DMA_OLD_FOUR_SLOT_FAILURE_REPRODUCED\n";
        }
        static_assert(rr::RenderConfig::getDisplayLines()==3);
        rr::devicedatauploader::DeviceDataUploader upload{bus};
        std::array<uint8_t,64> resource{};
        upload.writeToDeviceMemory({resource.data(),resource.size()},0x800000);
        bus.blockUntilTransferIsComplete();
        assert(lastTx==BUFFER_COUNT-1);
        std::unique_ptr<rr::threadedvertextransformer::ThreadedVertexTransformer> owner;
        rr::StdThreadRunner worker,transfer;
        owner=std::make_unique<rr::threadedvertextransformer::ThreadedVertexTransformer>(upload,worker,transfer);
        auto& device=*owner;
        assert(BUFFER_COUNT>=7&&upload.getDisplayListBufferCount()>=6);
        auto resourceSlot=bus.requestWriteBuffer(BUFFER_COUNT-1).data();
        for(uint8_t i=0;i<6;i++) assert(bus.requestWriteBuffer(i).data()!=resourceSlot);
        if(!rr::RIXGL::createInstance(device)) throw std::runtime_error("GL initialization failed");
        if(!rr::RIXGL::getInstance().setRenderResolution(400,240)) throw std::runtime_error("Framebuffer resolution setup failed");
        assert(rr::RIXGL::getInstance().pipeline().getFramebufferWidth()==400);
        assert(rr::RIXGL::getInstance().pipeline().getFramebufferHeight()==240);
        rr::RIXGL::destroy();device.deinit();
        bool txRejected=false,rxRejected=false;
        try {bus.requestWriteBuffer(BUFFER_COUNT);} catch(const std::out_of_range&) {txRejected=true;}
        try {bus.requestReadBuffer(BUFFER_COUNT);} catch(const std::out_of_range&) {rxRejected=true;}
        assert(txRejected&&rxRejected);
        std::cout<<"DMA_REAL_GL_INITIALIZATION_PASS: three strips, six command slots, independent resource slot "<<BUFFER_COUNT-1<<", ABI "<<RIX_DMA_ABI_VERSION<<", heap renderer bytes "<<sizeof(device)<<", config 0x"<<std::hex<<RIX_CONFIG_HASH32<<"\n";
        return 0;
    } catch(const std::out_of_range& error) {
        if(BUFFER_COUNT==4&&std::string(error.what())=="TX buffer index") {
            std::cout<<"DMA_OLD_FOUR_SLOT_FAILURE_REPRODUCED\n";return 0;
        }
        std::cerr<<error.what()<<'\n';return 1;
    } catch(const std::runtime_error& error) {
        if(BUFFER_COUNT==4&&std::string(error.what())=="Insufficient display-list buffer capacity") {
            std::cout<<"DMA_OLD_FOUR_SLOT_REJECTED_BEFORE_RENDER_INIT\n";return 0;
        }
        if(oldAbi&&std::string(error.what())=="dma-proxy ABI mismatch") {
            std::cout<<"DMA_OLD_ABI_REJECTED\n";return 0;
        }
        std::cerr<<error.what()<<'\n';return 1;
    }
}
