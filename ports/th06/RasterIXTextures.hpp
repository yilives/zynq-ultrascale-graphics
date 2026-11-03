// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "graphics/GfxInterface.hpp"
#include <cstdint>
#include <memory>

class RasterIXTextures {
public:
    struct Stats {
        uint64_t uploads=0,uploadBytes=0,draws=0,triangles=0,clipped=0,fastVertices=0,evictions=0,fallbacks=0;
        unsigned resident=0;
    };
    RasterIXTextures();
    ~RasterIXTextures();
    GfxTextureHandle create();
    void bind(GfxTextureHandle id);
    void erase(GfxTextureHandle id);
    void image(u32 width,u32 height,PixelFormat format,PixelDataType type,const void* pixels);
    void subImage(i32 x,i32 y,i32 width,i32 height,const void* pixels);
    void attribute(VertexAttributeArrays kind,std::size_t stride,void* pointer);
    void toggle(u8 attributes,bool enabled);
    void matrix(TransformMatrix kind,const ZunMatrix& matrix);
    void filter();
    void draw(PrimitiveType type,i32 start,i32 count);
    void frame(unsigned frame);
    const Stats& stats() const;
    const char* mode() const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl;
};
