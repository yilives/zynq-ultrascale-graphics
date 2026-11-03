// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "plgpu-display.h"
#include <cerrno>
#include <chrono>
#include <cstdlib>
#include <fcntl.h>
#include <stdexcept>
#include <sys/ioctl.h>
#include <unistd.h>
namespace rr::boardopt {
class Presenter {
    int fd=-1;
    bool enabled() const {
        static const bool value=!std::getenv("RIX_PRESENT_SYNC")||std::getenv("RIX_PRESENT_SYNC")[0]!='0';
        return value;
    }
    plgpu_status status() {
        if(fd<0)fd=open("/dev/plgpu_display",O_RDWR|O_CLOEXEC);
        if(fd<0)throw std::runtime_error("open RasterIX presenter failed");
        plgpu_status state{};
        if(ioctl(fd,PLGPU_GET_STATUS,&state)||state.abi!=0x52495801||state.configuration!=0x9adb505e||state.status!=3||state.read_errors||state.write_errors||state.timeouts||state.scan_underflows||state.scan_errors)
            throw std::runtime_error("RasterIX presenter status or configuration fault");
        return state;
    }
    void waitFor(uint32_t id) {
        const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);
        for(;;) {
            auto state=status();
            if(state.presented&&static_cast<int32_t>(state.last_presented_id-id)>=0)return;
            if(std::chrono::steady_clock::now()>=deadline)throw std::runtime_error("RasterIX presentation wait failed");
            // The board kernel's 2 ms sleep rounds to a scheduler tick. Reuse
            // the 300 us userspace pacing already verified by the TH06 port.
            usleep(300);
        }
    }
public:
    ~Presenter(){if(fd>=0)close(fd);}
    bool asynchronous() const {
        static const bool value=std::getenv("RIX_PRESENT_STRATEGY")&&std::getenv("RIX_PRESENT_STRATEGY")[0]=='a';
        return value;
    }
    bool serial() const {
        static const bool value=std::getenv("RIX_PRESENT_STRATEGY")&&std::getenv("RIX_PRESENT_STRATEGY")[0]=='s';
        return value;
    }
    // Called after draining the previous submitted list, before submitting
    // this one. Use hardware IDs: a software swap count is not a GPU fence.
    void beforeSubmit() {
        wait();
    }
    void finish() {
        wait();
    }
    void wait() {
        if(!enabled())return;
        auto state=status();
        if(!state.presented && !state.frame_id)return;
        waitFor(state.frame_id);
    }
};
}
