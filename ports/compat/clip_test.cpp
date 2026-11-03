// SPDX-License-Identifier: GPL-3.0-or-later
#include "transform/PlaneClipper.hpp"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <random>
using namespace rr;
using namespace rr::planeclipper;
static TransformingVertexParameter vertex(float x,float y) {
    TransformingVertexParameter p;
    p.vertex=Vec4{x,y,0,1};p.colorFront=Vec4{x,y,0,1};p.colorBack=p.colorFront;p.tex[0]=p.vertex;p.pointSize=1;
    return p;
}
int main() {
    PlaneClipperData data;
    data.equations={Vec4{1,0,0,1},Vec4{-1,0,0,1},Vec4{0,1,0,1},Vec4{0,-1,0,1},Vec4{1,1,0,1.25},Vec4{-1,-1,0,1.25}};
    data.enabledMask=63;
    PlaneClipperCalc calc(data);
    std::mt19937 random(931);
    std::uniform_real_distribution<float> coord(-4,4);
    unsigned checked=0;
    for(int n=0;n<5000;n++) {
        PlaneClipperCalc::ClipList a,b;
        for(int j=0;j<3;j++)a[j]=vertex(coord(random),coord(random));
        const auto clipped=calc.clipTriangle(a,b);
        assert(clipped.size()<=9);
        for(const auto& p:clipped) {
            for(const auto& e:data.equations)assert(p.vertex.dot(e)>=-0.00003f);
            assert(std::abs(p.vertex[0]-p.colorFront[0])<0.00002f);
            assert(std::abs(p.vertex[1]-p.tex[0][1])<0.00002f);
            checked++;
        }
    }
    PlaneClipperCalc::ClipList a,b;
    a[0]=vertex(-3,0);a[1]=vertex(3,0);
    auto line=calc.clipLine(a,b);
    assert(line.size()==2&&std::abs(line[0].vertex[0]+1)<0.00001f&&std::abs(line[1].vertex[0]-1)<0.00001f);
    a[0]=vertex(1,0);assert(calc.clipPoint(a,b).size()==1); // boundary retained
    a[0]=vertex(2,0);assert(calc.clipPoint(a,b).empty());
    a[0]=vertex(2,2);a[1]=vertex(3,3);assert(calc.clipLine(a,b).empty());
    data.enabledMask=0;a[0]=vertex(2,2);assert(calc.clipPoint(a,b).size()==1);
    assert(PlaneClipperSetter::getMaxClipPlanes()==6);
    std::printf("SIX_PLANE_CLIP_PASS random_triangles=5000 vertices=%u lines_points_boundaries=1\n",checked);
}
