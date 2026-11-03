// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace th06atlas {
struct Vertex {
    float position[3]{};
    float uv[2]{}; // Source texels, before conversion to a page's normalized UV.
    float color[4]{1,1,1,1};
};
struct Polygon { std::array<Vertex, 10> vertices{}; unsigned size=0; };
inline bool hasArea(const std::array<Vertex,3>& v) {
    double a[3],b[3];
    for(unsigned i=0;i<3;++i){a[i]=double(v[1].position[i])-v[0].position[i];b[i]=double(v[2].position[i])-v[0].position[i];}
    const double x=a[1]*b[2]-a[2]*b[1],y=a[2]*b[0]-a[0]*b[2],z=a[0]*b[1]-a[1]*b[0];
    const double scale=(a[0]*a[0]+a[1]*a[1]+a[2]*a[2])*(b[0]*b[0]+b[1]*b[1]+b[2]*b[2]);
    return x*x+y*y+z*z>scale*1.e-14;
}
inline Vertex interpolate(const Vertex& a,const Vertex& b,float t) {
    Vertex v;
    for(unsigned i=0;i<3;++i)v.position[i]=a.position[i]+(b.position[i]-a.position[i])*t;
    for(unsigned i=0;i<2;++i)v.uv[i]=a.uv[i]+(b.uv[i]-a.uv[i])*t;
    for(unsigned i=0;i<4;++i)v.color[i]=a.color[i]+(b.color[i]-a.color[i])*t;
    return v;
}
inline Polygon clip(const Polygon& input,unsigned axis,float edge,bool greater) {
    Polygon out;
    if(!input.size)return out;
    auto a=input.vertices[input.size-1];
    bool insideA=greater?a.uv[axis]>=edge:a.uv[axis]<=edge;
    for(unsigned i=0;i<input.size;++i) {
        const auto& b=input.vertices[i];
        const bool insideB=greater?b.uv[axis]>=edge:b.uv[axis]<=edge;
        if(insideA!=insideB) {
            auto v=interpolate(a,b,(edge-a.uv[axis])/(b.uv[axis]-a.uv[axis]));
            v.uv[axis]=edge;
            if(out.size==out.vertices.size())throw std::runtime_error("Atlas polygon overflow");
            out.vertices[out.size++]=v;
        }
        if(insideB) {
            if(out.size==out.vertices.size())throw std::runtime_error("Atlas polygon overflow");
            out.vertices[out.size++]=b;
        }
        a=b;insideA=insideB;
    }
    return out;
}
inline int page(float coordinate,int size) {
    if(!std::isfinite(coordinate)||std::fabs(coordinate)>1.e8f||size<=0)throw std::runtime_error("Invalid atlas UV");
    return static_cast<int>(std::floor(coordinate/size));
}
inline int lastPage(float lo,float hi,int size) {
    const int first=page(lo,size);
    // A right/bottom edge exactly on a page boundary has no area on the next page.
    return std::max(first,page(hi>lo?std::nextafter(hi,-INFINITY):hi,size));
}
inline int wrap(int value,int count) { const int r=value%count;return r<0?r+count:r; }
template<class Emit>
void split(const std::array<Vertex,3>& triangle,int width,int height,Emit&& emit) {
    const float minU=std::min({triangle[0].uv[0],triangle[1].uv[0],triangle[2].uv[0]});
    const float maxU=std::max({triangle[0].uv[0],triangle[1].uv[0],triangle[2].uv[0]});
    const float minV=std::min({triangle[0].uv[1],triangle[1].uv[1],triangle[2].uv[1]});
    const float maxV=std::max({triangle[0].uv[1],triangle[1].uv[1],triangle[2].uv[1]});
    const int x0=page(minU,width),x1=lastPage(minU,maxU,width);
    const int y0=page(minV,height),y1=lastPage(minV,maxV,height);
    if((int64_t(x1)-x0+1)*(int64_t(y1)-y0+1)>4096)throw std::runtime_error("Atlas UV span exceeds page budget");
    for(int y=y0;y<=y1;++y)for(int x=x0;x<=x1;++x) {
        Polygon polygon;polygon.size=3;std::copy(triangle.begin(),triangle.end(),polygon.vertices.begin());
        polygon=clip(polygon,0,float(x*width),true);
        polygon=clip(polygon,0,float((x+1)*width),false);
        polygon=clip(polygon,1,float(y*height),true);
        polygon=clip(polygon,1,float((y+1)*height),false);
        for(unsigned i=1;i+1<polygon.size;++i) {
            std::array<Vertex,3> part{polygon.vertices[0],polygon.vertices[i],polygon.vertices[i+1]};
            if(!hasArea(part))continue;
            for(auto& v:part) {
                v.uv[0]=std::clamp((v.uv[0]-x*width)/width,0.f,1.f);
                v.uv[1]=std::clamp((v.uv[1]-y*height)/height,0.f,1.f);
            }
            emit(x,y,part);
        }
    }
}
} // namespace th06atlas
