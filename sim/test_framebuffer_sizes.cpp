// SPDX-License-Identifier: GPL-3.0-or-later
#include <cstdint>
#include "renderer/commands/FramebufferCmd.hpp"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <iomanip>

int main(int argc,char** argv) {
    constexpr unsigned width=400,height=240,strip=width*height/3;
    static_assert(rr::RenderConfig::getDisplayLines()==3);
    rr::FramebufferCmd clear{true,false,false,strip};clear.enableMemset();
    rr::FramebufferCmd commit{true,false,false,strip};commit.commitFramebuffer();
    rr::FramebufferCmd swap{true,false,false,width*height};swap.swapFramebuffer();swap.enableVSync();
    assert(clear.getFramebufferSizeInPixel()==32000);
    assert(commit.getFramebufferSizeInPixel()==32000);
    assert(swap.getFramebufferSizeInPixel()==96000);
    assert(commit.getCommitFramebuffer()&&swap.getSwapFramebuffer()&&swap.getEnableVSync());
    const auto legacy=rr::RenderConfig::getAlignedSize(width*height);
    assert(legacy==96256&&legacy!=swap.getFramebufferSizeInPixel());
    if(argc==2) {
        std::ofstream output(argv[1]);
        for(const auto* cmd:{&clear,&commit,&swap})
            output<<std::hex<<std::setfill('0')<<std::setw(8)<<cmd->command()<<'\n';
        assert(output.good());
    }
    std::puts("FRAMEBUFFER_EXACT_PIXELS_PASS: legacy swap 96256 rejected by 96000-pixel bridge; strip clear/commit 32000, swap 96000");
}
