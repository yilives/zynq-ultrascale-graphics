// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <cstdint>

namespace th06atlas {
// Straight-alpha output from a premultiplied box average avoids dark fringes
// around sprites. Only the changed source rectangle needs rebuilding.
inline void reduce2x(const uint8_t* source,unsigned width,unsigned height,uint8_t* output,
                     unsigned outputWidth,unsigned x0,unsigned y0,unsigned x1,unsigned y1) {
    for(unsigned y=y0;y<y1;++y)for(unsigned x=x0;x<x1;++x) {
        unsigned alpha=0,color[3]{};
        for(unsigned dy=0;dy<2;++dy)for(unsigned dx=0;dx<2;++dx) {
            const auto* p=source+(size_t(std::min(height-1,y*2+dy))*width+std::min(width-1,x*2+dx))*4;
            alpha+=p[3];for(unsigned c=0;c<3;++c)color[c]+=unsigned(p[c])*p[3];
        }
        auto* p=output+(size_t(y)*outputWidth+x)*4;
        for(unsigned c=0;c<3;++c)p[c]=alpha?(color[c]+alpha/2)/alpha:0;
        p[3]=(alpha+2)/4;
    }
}
}
