// SPDX-License-Identifier: GPL-3.0-or-later
#include "PackedVertexReader.hpp"
#include <iostream>
#include <vector>
#include <stdexcept>
using namespace rr;
static void require(bool value) { if(!value) throw std::runtime_error("Packed reader check failed"); }
static VertexParameter generic(const RenderObj& obj,std::size_t index) {
    VertexParameter p;auto i=obj.getIndex(index);p.sourceIndex=i;
    p.vertex=obj.getVertex(i);p.color=obj.getColor(i);p.normal=obj.getNormal(i);p.pointSize=obj.getPointSize(i);
    for(std::size_t t=0;t<RenderConfig::TMU_COUNT;t++)p.tex[t]=obj.getTexCoord(t,i);
    return p;
}
int main() {
    std::size_t checked=0,fallbacks=0;
    for(bool interleaved:{false,true}) for(bool textured:{false,true}) for(std::size_t offset:{0,3,73}) {
        constexpr std::size_t n=1024;
        std::vector<float> positions((n+offset)*8),uv((n+offset)*2);
        std::vector<unsigned char> colors((n+offset)*4);
        for(std::size_t i=0;i<n+offset;i++) {
            float xyz[3]={float(int(i)%53-27)/7.0f,i%2 ? -0.0f : 0.0f,float(i%97)/13.0f};
            unsigned char c[4]={static_cast<unsigned char>(i),static_cast<unsigned char>(i>>2),static_cast<unsigned char>(255-i),static_cast<unsigned char>(i%3 ? 255:0)};
            float tex[2]={float(i%31)/31.0f,float(i%13)/13.0f};
            if(interleaved) {
                auto* p=reinterpret_cast<unsigned char*>(positions.data()+i*8);
                std::memcpy(p,xyz,12);std::memcpy(p+12,c,4);std::memcpy(p+16,tex,8);
            } else {
                std::memcpy(positions.data()+i*3,xyz,12);std::memcpy(colors.data()+i*4,c,4);std::memcpy(uv.data()+i*2,tex,8);
            }
        }
        RenderObj obj;obj.enableVertexArray(true);obj.enableIndices(false);obj.setArrayOffset(offset);obj.setCount(n);
        obj.setVertexType(Type::FLOAT);obj.setVertexSize(3);obj.setVertexPointer(positions.data());obj.setVertexStride(interleaved?32:0);
        obj.enableColorArray(true);obj.setColorType(Type::UNSIGNED_BYTE);obj.setColorSize(4);
        obj.setColorPointer(interleaved?reinterpret_cast<unsigned char*>(positions.data())+12:colors.data());obj.setColorStride(interleaved?32:0);
        obj.enableNormalArray(false);obj.setNormal(Vec3{0,-0.0f,1});obj.enablePointSizeArray(false);obj.setPointSize(2.5f);
        for(std::size_t t=0;t<RenderConfig::TMU_COUNT;t++) {
            obj.enableTexCoordArray(t,textured);
            if(textured) {
                obj.setTexCoordType(t,Type::FLOAT);obj.setTexCoordSize(t,2);
                obj.setTexCoordPointer(t,interleaved?static_cast<const void*>(reinterpret_cast<unsigned char*>(positions.data())+16):static_cast<const void*>(uv.data()));obj.setTexCoordStride(t,interleaved?32:0);
            }
            obj.setTexCoord(t,Vec4{0.25f,0.75f,0,1});
        }
        boardopt::PackedVertexReader packed(obj);require(packed.enabled());
        for(std::size_t i=0;i<n;i++){require(boardopt::PackedVertexReader::equal(packed.fetch(i),generic(obj,i)));++checked;}
        obj.enableIndices(true);require(!boardopt::PackedVertexReader(obj).enabled());++fallbacks;obj.enableIndices(false);
        obj.enableNormalArray(true);require(!boardopt::PackedVertexReader(obj).enabled());++fallbacks;obj.enableNormalArray(false);
        obj.enablePointSizeArray(true);require(!boardopt::PackedVertexReader(obj).enabled());++fallbacks;obj.enablePointSizeArray(false);
        obj.setVertexSize(2);require(!boardopt::PackedVertexReader(obj).enabled());++fallbacks;obj.setVertexSize(3);
        obj.setVertexPointer(nullptr);require(!boardopt::PackedVertexReader(obj).enabled());++fallbacks;obj.setVertexPointer(positions.data());
        obj.setColorType(Type::FLOAT);require(!boardopt::PackedVertexReader(obj).enabled());++fallbacks;obj.setColorType(Type::UNSIGNED_BYTE);
        obj.setCount(0);require(!boardopt::PackedVertexReader(obj).enabled());++fallbacks;
    }
    std::cout<<"PACKED_READER_PASS exact_vertices="<<checked<<" fallback_cases="<<fallbacks<<"\n";
}
