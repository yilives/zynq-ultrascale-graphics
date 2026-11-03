// SPDX-License-Identifier: GPL-3.0-or-later
#include "DMAProxyBusConnector.hpp"
#include "kernel/dma-proxy/files/include/dma-proxy.h"
#include <atomic>
#include <cerrno>
#include <fcntl.h>
#include <stdexcept>
#include <string>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

namespace rr {
const std::size_t DMAProxyBusConnector::INVALID_BUFFER { BUFFER_COUNT };
static void checkedIoctl(int fd, unsigned long command, uint32_t& value) {
    int rc;
    do { rc=ioctl(fd,command,&value); } while(rc<0&&errno==EINTR);
    if(rc<0) throw std::runtime_error("dma-proxy ioctl errno="+std::to_string(errno));
}
DMAProxyBusConnector::DMAProxyBusConnector() {
    const char* tx[]={"dma_proxy_tx"};const char* rx[]={"dma_proxy_rx"};
    m_txChannel={nullptr,-1};m_rxChannel={nullptr,-1};
    openChannel(m_txChannel,tx);
    try { openChannel(m_rxChannel,rx); }
    catch(...) { munmap(m_txChannel.buf_ptr,sizeof(channel_buffer)*BUFFER_COUNT);close(m_txChannel.fd);throw; }
}
void DMAProxyBusConnector::openChannel(Channel& c,const char* names[]) {
    c.fd=open((std::string("/dev/")+names[0]).c_str(),O_RDWR|O_CLOEXEC);
    if(c.fd<0) throw std::runtime_error("open dma-proxy errno="+std::to_string(errno));
    try {
        uint32_t abi=0;checkedIoctl(c.fd,RIX_DMA_GET_ABI,abi);
        if(abi!=RIX_DMA_ABI_VERSION) throw std::runtime_error("dma-proxy ABI mismatch");
        auto p=mmap(nullptr,sizeof(channel_buffer)*BUFFER_COUNT,PROT_READ|PROT_WRITE,MAP_SHARED,c.fd,0);
        if(p==MAP_FAILED) throw std::runtime_error("mmap dma-proxy failed");
        c.buf_ptr=static_cast<channel_buffer*>(p);
    } catch(...) { close(c.fd);c.fd=-1;throw; }
}
DMAProxyBusConnector::~DMAProxyBusConnector() {
    try { waitForDma(); } catch(...) { /* close terminates and drains DMA */ }
    // Terminate before unmapping, including process shutdown after an error.
    if(m_txChannel.fd>=0) close(m_txChannel.fd);
    if(m_rxChannel.fd>=0) close(m_rxChannel.fd);
    if(m_txChannel.buf_ptr) munmap(m_txChannel.buf_ptr,sizeof(channel_buffer)*BUFFER_COUNT);
    if(m_rxChannel.buf_ptr) munmap(m_rxChannel.buf_ptr,sizeof(channel_buffer)*BUFFER_COUNT);
}
static void validate(uint8_t index,uint32_t size) {
    if(index>=BUFFER_COUNT||!size||size>BUFFER_SIZE||(size&3)) throw std::out_of_range("Invalid DMA index/length");
}
void DMAProxyBusConnector::writeData(uint8_t index,uint32_t size,uint32_t offset) {
    validate(index,size);
    if(offset) throw std::out_of_range("DMA offset is unsupported");
    waitForDma();uint32_t id=index;
    m_txChannel.buf_ptr[id].length=size;
    std::atomic_thread_fence(std::memory_order_release);
    checkedIoctl(m_txChannel.fd,START_XFER,id);
    m_busyBufferId=id;m_busyChannel=m_txChannel;
}
void DMAProxyBusConnector::readData(uint8_t index,uint32_t size) {
    validate(index,size);waitForDma();uint32_t id=index;
    m_rxChannel.buf_ptr[id].length=size;
    std::atomic_thread_fence(std::memory_order_release);
    checkedIoctl(m_rxChannel.fd,START_XFER,id);
    m_busyBufferId=id;m_busyChannel=m_rxChannel;
    waitForDma();
}
void DMAProxyBusConnector::waitForDma() {
    if(m_busyBufferId==INVALID_BUFFER) return;
    uint32_t id=static_cast<uint32_t>(m_busyBufferId);
    // Clear ownership even when FINISH reports an error; kernel has drained it.
    m_busyBufferId=INVALID_BUFFER;
    checkedIoctl(m_busyChannel.fd,FINISH_XFER,id);
    std::atomic_thread_fence(std::memory_order_acquire);
    if(m_busyChannel.buf_ptr[id].status!=PROXY_NO_ERROR) throw std::runtime_error("DMA completion error");
}
void DMAProxyBusConnector::blockUntilTransferIsComplete() { waitForDma(); }
tcb::span<uint8_t> DMAProxyBusConnector::requestWriteBuffer(uint8_t id) {
    if(id>=BUFFER_COUNT) throw std::out_of_range("TX buffer index");
    if(m_busyBufferId==id&&m_busyChannel.fd==m_txChannel.fd) waitForDma();
    return {reinterpret_cast<uint8_t*>(m_txChannel.buf_ptr[id].buffer),BUFFER_SIZE};
}
tcb::span<uint8_t> DMAProxyBusConnector::requestReadBuffer(uint8_t id) {
    if(id>=BUFFER_COUNT) throw std::out_of_range("RX buffer index");
    if(m_busyBufferId==id&&m_busyChannel.fd==m_rxChannel.fd) waitForDma();
    return {reinterpret_cast<uint8_t*>(m_rxChannel.buf_ptr[id].buffer),BUFFER_SIZE};
}
uint8_t DMAProxyBusConnector::getWriteBufferCount() const { return BUFFER_COUNT; }
uint8_t DMAProxyBusConnector::getReadBufferCount() const { return BUFFER_COUNT; }
}
