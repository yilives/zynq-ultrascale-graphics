// SPDX-License-Identifier: GPL-3.0-or-later
#include <cstdint>
#include "renderer/Renderer.hpp"
#include <array>
#include <cstdio>
#include <memory>
#include <stdexcept>

struct Device final:rr::IDevice {
    std::array<std::array<uint8_t,65536>,2> lists{};
    uint32_t address=0;
    void streamDisplayList(uint8_t,uint32_t) override {}
    bool writeToDeviceMemory(tcb::span<const uint8_t>,uint32_t) override {return true;}
    bool readFromDeviceMemory(tcb::span<uint8_t>,uint32_t addr) override {address=addr;return true;}
    void blockUntilDeviceIsIdle() override {}
    tcb::span<uint8_t> requestDisplayListBuffer(uint8_t i) override {return lists.at(i);}
    uint8_t getDisplayListBufferCount() const override {return 2;}
};
static void check(bool ok,const char* description) {
    if(!ok) throw std::runtime_error(description);
}
int main() {
    try {
        Device device;
        auto renderer=std::make_unique<rr::Renderer>(device);
        check(renderer->setRenderResolution(400,240),"Resolution setup failed");
        check(renderer->getFramebufferWidth()==400&&renderer->getFramebufferHeight()==240,"Readback dimensions mismatch");
        std::array<uint8_t,64> bytes{};
        for(unsigned frame=0;frame<4;frame++) {
            renderer->swapDisplayList();
            const auto front=frame%2?rr::RenderConfig::COLOR_BUFFER_LOC_2:rr::RenderConfig::COLOR_BUFFER_LOC_1;
            const auto back=frame%2?rr::RenderConfig::COLOR_BUFFER_LOC_1:rr::RenderConfig::COLOR_BUFFER_LOC_2;
            renderer->readFrontColorBuffer(bytes);
            check(device.address==front,"Front buffer does not follow the last presented frame");
            renderer->readBackColorBuffer(bytes);
            check(device.address==back,"Back buffer aliases the last presented frame");
        }
        std::puts("FRAMEBUFFER_ROLE_AND_READBACK_DIMENSIONS_PASS: alternating front/back, 400x240");
        return 0;
    } catch(const std::exception& error) {
        std::fprintf(stderr,"FRAMEBUFFER_ROLE_FAILURE: %s\n",error.what());return 1;
    }
}
