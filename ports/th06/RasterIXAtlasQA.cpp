// SPDX-License-Identifier: GPL-3.0-or-later
#include "RasterIXTextures.hpp"
#include "graphics/GLFunc.hpp"
#include <array>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

namespace {
std::array<unsigned char,4> pattern(int x,int y,bool patch) {
    x=(x%512+512)%512;y=(y%256+256)%256;
    if(patch&&x>=240&&x<288&&y>=112&&y<160)return {0,255,136,255};
    return {static_cast<unsigned char>((x/2)&1?255:17),static_cast<unsigned char>((y/2)&1?221:34),static_cast<unsigned char>((x/128+(y/128)*4)*17),255};
}
}
int RasterIXAtlasQA(GfxInterface& gfx,RasterIXTextures& textures,const char* prefix) {
    g_glFuncTable.glDisable(GL_DEPTH_TEST);g_glFuncTable.glDisable(GL_BLEND);g_glFuncTable.glDisable(GL_FOG);
    g_glFuncTable.glDisable(GL_ALPHA_TEST);g_glFuncTable.glEnable(GL_TEXTURE_2D);
    const float white[4]{1,1,1,1};g_glFuncTable.glTexEnvfv(GL_TEXTURE_ENV,GL_TEXTURE_ENV_COLOR,white);
    gfx.ToggleVertexAttribute(VERTEX_ATTR_TEX_COORD,true);gfx.ToggleVertexAttribute(VERTEX_ATTR_DIFFUSE,false);
    ZunMatrix identity;identity.Identity();
    gfx.SetTransformMatrix(MATRIX_VIEW,identity);gfx.SetTransformMatrix(MATRIX_PROJECTION,identity);gfx.SetTransformMatrix(MATRIX_TEXTURE,identity);
    gfx.SetViewport(0,0,400,240);gfx.SetClearColor(0,0,0,1);
    const auto texture=gfx.CreateTexture();gfx.BindTexture(texture);
    std::vector<unsigned char> image(512*256*4);
    for(int y=0;y<256;++y)for(int x=0;x<512;++x){const auto p=pattern(x,y,false);std::copy(p.begin(),p.end(),image.begin()+(y*512+x)*4);}
    gfx.SetTextureImage(512,256,PIXEL_RGBA,PIXEL_UNSIGNED_BYTE,image.data());
    const std::string mode=textures.mode();const int ew=mode=="native"?512:mode=="balanced"?256:128,eh=ew/2;
    unsigned total=0,bad=0;
    std::ofstream report(std::string(prefix)+".json");report<<"{\"mode\":\""<<mode<<"\",\"cases\":[";
    for(unsigned test=0;test<4;++test){
        const float u0=test==1?-.25f:test==2?.25f:0.f,u1=test==1?1.25f:test==2?.5f:1.f;
        const float v0=test==1?-.5f:0.f,v1=test==1?1.5f:test==2?.5f:1.f;
        if(test==3){std::vector<unsigned char> patch(48*48*3);for(unsigned i=0;i<48*48;++i){patch[i*3]=0;patch[i*3+1]=255;patch[i*3+2]=136;}gfx.SetTextureSubImage(240,112,48,48,patch.data());}
        struct Vertex {float position[3],uv[2];};
        const Vertex vertices[6]{{{-1,-1,0},{u0,v0}},{{1,-1,0},{u1,v0}},{{-1,1,0},{u0,v1}},{{1,-1,0},{u1,v0}},{{-1,1,0},{u0,v1}},{{1,1,0},{u1,v1}}};
        gfx.SetAttributePointer(VERTEX_ARRAY_POSITION,sizeof(Vertex),const_cast<float*>(vertices[0].position));
        gfx.SetAttributePointer(VERTEX_ARRAY_TEX_COORD,sizeof(Vertex),const_cast<float*>(vertices[0].uv));
        const auto uploads=textures.stats().uploads;
        gfx.Clear(CLEAR_COLOR_BUFFER|CLEAR_DEPTH_BUFFER);gfx.Draw(PRIM_TRIANGLES,0,6);gfx.SwapBuffers();
        std::vector<unsigned char> pixels(400*240*4);gfx.ReadPixels(0,0,400,240,pixels.data());
        unsigned compared=0,mismatches=0;
        for(int y=1;y<239;++y)for(int x=1;x<399;++x){
            // This RasterIX revision seeds interpolation at integer bounding-box
            // coordinates (Rasterizer.cpp: p=bbStart<<SUB_PIXEL), without +0.5.
            const double tx=(u0+(u1-u0)*x/400)*ew,ty=(v0+(v1-v0)*y/240)*eh;
            const double fx=tx-std::floor(tx),fy=ty-std::floor(ty);
            // Fixed-point rasterization can choose either side of an exact
            // texel boundary; check interior samples and page colors strictly.
            if(fx<.08||fx>.92||fy<.08||fy>.92)continue;
            const int factor=mode=="native"?1:mode=="balanced"?2:4;
            const int offset=mode=="scaled"?2:0;
            const auto wanted=pattern(int(std::floor(tx))*factor+offset,int(std::floor(ty))*factor+offset,test==3);
            const auto* got=pixels.data()+(y*400+x)*4;
            bool wrong=false;for(unsigned c=0;c<3;++c)wrong|=std::abs(int(got[c])-int(wanted[c]))>9;
            if(wrong&&mismatches<3)std::fprintf(stderr,"TH06_ATLAS_PIXEL_MISMATCH test=%u x=%d y=%d got=%u,%u,%u expected=%u,%u,%u\n",test,x,y,got[0],got[1],got[2],wanted[0],wanted[1],wanted[2]);
            mismatches+=wrong;++compared;
        }
        std::ofstream frame(std::string(prefix)+"-"+std::to_string(test)+".ppm",std::ios::binary);frame<<"P6\n400 240\n255\n";
        for(int y=239;y>=0;--y)for(int x=0;x<400;++x)frame.write(reinterpret_cast<const char*>(pixels.data()+(y*400+x)*4),3);
        if(test)report<<',';
        report<<"{\"test\":"<<test<<",\"compared\":"<<compared<<",\"mismatches\":"<<mismatches<<",\"uploads\":"<<textures.stats().uploads-uploads<<'}';
        total+=compared;bad+=mismatches+(compared<30000?1:0);
    }
    report<<"],\"compared\":"<<total<<",\"mismatches\":"<<bad<<",\"passed\":"<<(bad?"false":"true")<<"}\n";
    gfx.DeleteTexture(texture);
    std::printf("TH06_ATLAS_GPU_QA mode=%s compared=%u mismatches=%u\n",mode.c_str(),total,bad);std::fflush(stdout);
    return bad?1:0;
}
