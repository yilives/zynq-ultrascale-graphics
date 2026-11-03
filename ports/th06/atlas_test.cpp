// SPDX-License-Identifier: GPL-3.0-or-later
#include "AtlasTiles.hpp"
#include "AtlasImage.hpp"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <random>

using th06atlas::Vertex;
double area(const Vertex& a,const Vertex& b,const Vertex& c) {
    return std::fabs((double(b.position[0])-a.position[0])*(double(c.position[1])-a.position[1])-
                     (double(b.position[1])-a.position[1])*(double(c.position[0])-a.position[0]))*.5;
}
int main() {
    const uint8_t alphaTest[16]{255,0,0,255,0,255,0,0,0,0,255,0,0,0,0,0};
    uint8_t reduced[4]{};th06atlas::reduce2x(alphaTest,2,2,reduced,1,0,0,1,1);
    assert(reduced[0]==255&&reduced[1]==0&&reduced[2]==0&&reduced[3]==64);
    th06atlas::reduce2x(alphaTest,1,1,reduced,1,0,0,1,1);
    assert(reduced[0]==255&&reduced[3]==255);
    assert(th06atlas::wrap(-1,4)==3&&th06atlas::wrap(5,4)==1);
    assert(th06atlas::lastPage(0,128,128)==0&&th06atlas::lastPage(128,128,128)==1);
    std::mt19937 random(0x524958);
    std::uniform_real_distribution<float> coordinate(-255,767);
    unsigned emitted=0;
    for(unsigned trial=0;trial<3000;++trial) {
        std::array<Vertex,3> triangle;
        for(unsigned i=0;i<3;++i) {
            auto& v=triangle[i];v.uv[0]=coordinate(random);v.uv[1]=coordinate(random);
            // Affine, rotated/skewed geometry and interpolated depth/color must
            // survive clipping, including negative/repeated atlas coordinates.
            v.position[0]=v.uv[0]*.7f+v.uv[1]*.2f;
            v.position[1]=v.uv[0]*-.3f+v.uv[1]*.8f;
            v.position[2]=v.uv[0]*.001f+v.uv[1]*.0005f;
            v.color[0]=v.uv[0]*.001f;
        }
        double sum=0;
        th06atlas::split(triangle,128,128,[&](int x,int y,const auto& part) {
            ++emitted;sum+=area(part[0],part[1],part[2]);
            for(const auto& v:part) {
                assert(v.uv[0]>=0&&v.uv[0]<=1&&v.uv[1]>=0&&v.uv[1]<=1);
                const double u=(v.uv[0]+x)*128,w=(v.uv[1]+y)*128;
                assert(std::fabs(v.position[0]-(u*.7+w*.2))<.001);
                assert(std::fabs(v.position[1]-(-u*.3+w*.8))<.001);
                assert(std::fabs(v.position[2]-(u*.001+w*.0005))<.00001);
                assert(std::fabs(v.color[0]-u*.001)<.00001);
            }
        });
        const double original=area(triangle[0],triangle[1],triangle[2]);
        assert(std::fabs(sum-original)<std::max(.1,original*1.e-5));
    }
    std::printf("TH06_ATLAS_CLIP_TEST_PASS random_triangles=3000 emitted=%u\n",emitted);
}
