// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "graphics/FixedFunctionGL.hpp"
#include <memory>
int RasterIXRenderFrame();
struct RasterIXBackend : FixedFunctionGL {
    static GfxInterface* Init();
    ~RasterIXBackend() override;
    void Exit() override;
    void SwapBuffers() override;
    void GetViewport(u32* viewport) override;
    void ToggleVertexAttribute(u8 attributes,bool enabled) override;
    void SetAttributePointer(VertexAttributeArrays kind,std::size_t stride,void* pointer) override;
    void SetTransformMatrix(TransformMatrix kind,const ZunMatrix& matrix) override;
    void SetTextureFilter() override;
    void Draw(PrimitiveType type,i32 start,i32 count) override;
    GfxTextureHandle CreateTexture() override;
    void BindTexture(GfxTextureHandle handle) override;
    void DeleteTexture(GfxTextureHandle handle) override;
    void SetTextureImage(u32 width,u32 height,PixelFormat fmt,PixelDataType type,const void* data) override;
    void SetTextureSubImage(i32 x,i32 y,i32 width,i32 height,const void* data) override;
private:
    struct State;
    std::unique_ptr<State> state;
};
