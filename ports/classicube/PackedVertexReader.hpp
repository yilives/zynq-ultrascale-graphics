// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "vertexpipeline/RenderObj.hpp"
#include "VertexParameter.hpp"
#include <cstring>

namespace rr::boardopt {
// A checked specialization of RenderObj's generic array conversions. Strides,
// array offsets and disabled attributes retain the generic path's semantics.
// Custom indices and all other formats continue through the generic reader.
class PackedVertexReader {
public:
    explicit PackedVertexReader(const RenderObj& obj) {
        if (!obj.getCount() || obj.indicesEnabled() || obj.getVertexType()!=Type::FLOAT ||
            obj.getVertexSize()!=3 || !obj.getVertexPointer() || !obj.colorArrayEnabled() ||
            obj.getColorType()!=Type::UNSIGNED_BYTE || obj.getColorSize()!=4 ||
            !obj.getColorPointer() || obj.normalArrayEnabled() || obj.pointSizeArrayEnabled()) return;
        for (std::size_t t=0;t<RenderConfig::TMU_COUNT;t++) {
            if (obj.texCoordArrayEnabled()[t] &&
                (obj.getTexCoordType(t)!=Type::FLOAT || obj.getTexCoordSize(t)!=2 || !obj.getTexCoordPointer(t))) return;
        }
        position=static_cast<const unsigned char*>(obj.getVertexPointer());
        color=static_cast<const unsigned char*>(obj.getColorPointer());
        positionStride=obj.getVertexStride() ? obj.getVertexStride() : 3*sizeof(float);
        colorStride=obj.getColorStride() ? obj.getColorStride() : 4;
        offset=obj.getArrayOffset();
        constant.vertex=Vec4::createHomogeneous();
        constant.color=Vec4{1,1,1,1};
        constant.normal=obj.getNormal(0);
        constant.pointSize=obj.getPointSize(0);
        constant.sourceIndex=0;
        for (std::size_t t=0;t<RenderConfig::TMU_COUNT;t++) {
            texture[t]=obj.texCoordArrayEnabled()[t] ? static_cast<const unsigned char*>(obj.getTexCoordPointer(t)) : nullptr;
            textureStride[t]=texture[t] ? (obj.getTexCoordStride(t) ? obj.getTexCoordStride(t) : 2*sizeof(float)) : 0;
            constant.tex[t]=texture[t] ? Vec4::createHomogeneous() : obj.getTexCoord(t,0);
        }
        valid=true;
    }
    bool enabled() const { return valid; }
    VertexParameter fetch(std::size_t index) const {
        const std::size_t i=index+offset;
        // memcpy also permits unaligned application array pointers. These are
        // ordinary VBO process memory, never Device-mapped framebuffer memory.
        float xyz[3]; std::memcpy(xyz,position+i*positionStride,sizeof(xyz));
        const auto* c=color+i*colorStride;
        VertexParameter p=constant;
        p.sourceIndex=i;
        p.vertex=Vec4{xyz[0],xyz[1],xyz[2],1};
        p.color=Vec4{float(c[0]),float(c[1]),float(c[2]),float(c[3])};
        p.color*=1.0f/255.0f;
        for (std::size_t t=0;t<RenderConfig::TMU_COUNT;t++) if (texture[t]) {
            float uv[2]; std::memcpy(uv,texture[t]+i*textureStride[t],sizeof(uv));
            p.tex[t]=Vec4{uv[0],uv[1],0,1};
        }
        return p;
    }
    static bool equal(const VertexParameter& a,const VertexParameter& b) {
        if(a.sourceIndex!=b.sourceIndex || !same(a.pointSize,b.pointSize)) return false;
        for(int i=0;i<4;i++) if(!same(a.vertex[i],b.vertex[i]) || !same(a.color[i],b.color[i])) return false;
        for(int i=0;i<3;i++) if(!same(a.normal[i],b.normal[i])) return false;
        for(std::size_t t=0;t<RenderConfig::TMU_COUNT;t++)
            for(int i=0;i<4;i++) if(!same(a.tex[t][i],b.tex[t][i])) return false;
        return true;
    }
private:
    static bool same(float a,float b) { return std::memcmp(&a,&b,sizeof(float))==0; }
    bool valid=false;
    const unsigned char *position=nullptr,*color=nullptr;
    std::array<const unsigned char*,RenderConfig::TMU_COUNT> texture{};
    std::array<std::size_t,RenderConfig::TMU_COUNT> textureStride{};
    std::size_t positionStride=0,colorStride=0,offset=0;
    VertexParameter constant{};
};
}
