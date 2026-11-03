// SPDX-License-Identifier: GPL-3.0-or-later
#include "RasterIXTextures.hpp"
#include "AtlasTiles.hpp"
#include "AtlasImage.hpp"
#include "graphics/GLFunc.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace {
using Matrix=std::array<float,16>;
constexpr Matrix identity{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1};
struct Page { GLuint id=0;bool dirty=true;unsigned frame=0;uint64_t used=0; };
struct Texture {
    u32 width=0,height=0,pageWidth=0,pageHeight=0,columns=0,rows=0;
    u32 sourceWidth=0,sourceHeight=0;
    std::vector<u8> pixels,source;
    std::vector<Page> pages;
    bool baseDirty=true;
};
struct Attribute {const u8* pointer=nullptr;std::size_t stride=0;};
bool powerOfTwo(u32 x){return x&&!(x&(x-1));}
GLuint createRaw(){GLuint id=0;g_glFuncTable.glGenTextures(1,&id);if(!id)throw std::runtime_error("TH06 GL texture name allocation failed");return id;}
void deleteRaw(GLuint id){if(id)g_glFuncTable.glDeleteTextures(1,&id);}
void nearest(){g_glFuncTable.glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);g_glFuncTable.glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);}
GLenum primitive(PrimitiveType type){return type==PRIM_TRIANGLES?GL_TRIANGLES:GL_TRIANGLE_STRIP;}
}
struct RasterIXTextures::Impl {
    std::unordered_map<u32,Texture> textures;
    std::array<Attribute,3> attributes{};
    Matrix textureMatrix=identity;
    bool texcoords=false,colors=false,paged=true,balanced=true;
    GLuint bound=0,white=0;
    unsigned currentFrame=0;
    uint64_t serial=0;
    Stats counters;
    std::vector<u8> upload;
    std::vector<th06atlas::Vertex> batch;

    Impl(){
        const char* mode=std::getenv("TH06_TEXTURE_MODE");
        if(mode&&std::strcmp(mode,"native")&&std::strcmp(mode,"balanced")&&std::strcmp(mode,"scaled"))throw std::runtime_error("TH06_TEXTURE_MODE must be balanced, native or scaled");
        paged=!mode||std::strcmp(mode,"scaled");
        balanced=!mode||!std::strcmp(mode,"balanced");
        white=createRaw();g_glFuncTable.glBindTexture(GL_TEXTURE_2D,white);
        const u8 pixel[4]{255,255,255,255};rawImage(1,1,pixel);nearest();batch.reserve(8192);
    }
    ~Impl(){for(auto& pair:textures){for(auto& page:pair.second.pages)deleteRaw(page.id);deleteRaw(pair.first);}deleteRaw(white);}
    void rawImage(u32 width,u32 height,const u8* data){
        g_glFuncTable.glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,width,height,0,GL_RGBA,GL_UNSIGNED_BYTE,data);
        ++counters.uploads;counters.uploadBytes+=uint64_t(width)*height*2;
    }
    void bindBase(){g_glFuncTable.glBindTexture(GL_TEXTURE_2D,bound?bound:white);}
    void releasePages(Texture& tex){for(auto& page:tex.pages)if(page.id){deleteRaw(page.id);--counters.resident;}tex.pages.clear();}
    void ensureBase(Texture& tex){
        bindBase();if(!tex.baseDirty)return;
        u32 shift=0;while((tex.width>>shift)>128||(tex.height>>shift)>128)++shift;
        const u32 width=std::max(1u,tex.width>>shift),height=std::max(1u,tex.height>>shift);
        upload.resize(size_t(width)*height*4);
        for(u32 y=0;y<height;++y)for(u32 x=0;x<width;++x){
            const u32 sx=std::min(tex.width-1,(x<<shift)+(shift?(1u<<(shift-1)):0));
            const u32 sy=std::min(tex.height-1,(y<<shift)+(shift?(1u<<(shift-1)):0));
            std::copy_n(tex.pixels.data()+(size_t(sy)*tex.width+sx)*4,4,upload.data()+(size_t(y)*width+x)*4);
        }
        nearest();rawImage(width,height,upload.data());tex.baseDirty=false;
    }
    void evict(){
        // Do not recycle a page referenced by commands in the current frame.
        // The previous frame has already received its real presentation ACK.
        if(counters.resident<192)return;
        Page* victim=nullptr;
        for(auto& pair:textures)for(auto& page:pair.second.pages)
            if(page.id&&page.frame!=currentFrame&&(!victim||page.used<victim->used))victim=&page;
        if(victim){deleteRaw(victim->id);victim->id=0;victim->dirty=true;--counters.resident;++counters.evictions;}
        if(counters.resident>=384)throw std::runtime_error("TH06 per-frame atlas residency budget exceeded");
    }
    GLuint ensurePage(Texture& tex,int x,int y){
        const unsigned column=th06atlas::wrap(x,tex.columns),row=th06atlas::wrap(y,tex.rows);
        auto& page=tex.pages[row*tex.columns+column];
        if(!page.id){evict();page.id=createRaw();++counters.resident;page.dirty=true;}
        page.frame=currentFrame;page.used=++serial;
        g_glFuncTable.glBindTexture(GL_TEXTURE_2D,page.id);
        if(page.dirty){
            upload.resize(size_t(tex.pageWidth)*tex.pageHeight*4);
            for(u32 py=0;py<tex.pageHeight;++py)
                std::copy_n(tex.pixels.data()+((size_t(row*tex.pageHeight+py)*tex.width)+column*tex.pageWidth)*4,
                            size_t(tex.pageWidth)*4,upload.data()+size_t(py)*tex.pageWidth*4);
            nearest();g_glFuncTable.glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
            g_glFuncTable.glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
            rawImage(tex.pageWidth,tex.pageHeight,upload.data());page.dirty=false;
        }
        return page.id;
    }
    const u8* data(unsigned kind,unsigned vertex) const{
        const auto& a=attributes[kind];if(!a.pointer)throw std::runtime_error("TH06 vertex array is missing");
        const std::size_t element=kind==VERTEX_ARRAY_POSITION?12:kind==VERTEX_ARRAY_TEX_COORD?8:4;
        return a.pointer+vertex*(a.stride?a.stride:element);
    }
    std::array<float,2> uv(unsigned vertex,const Texture& tex) const{
        float v[2];std::memcpy(v,data(VERTEX_ARRAY_TEX_COORD,vertex),sizeof(v));
        const auto& m=textureMatrix;
        return {(v[0]*m[0]+v[1]*m[4]+m[12])*tex.width/m[15],(v[0]*m[1]+v[1]*m[5]+m[13])*tex.height/m[15]};
    }
    th06atlas::Vertex vertex(unsigned index,const Texture& tex) const{
        th06atlas::Vertex v;std::memcpy(v.position,data(VERTEX_ARRAY_POSITION,index),12);
        const auto t=uv(index,tex);std::copy(t.begin(),t.end(),v.uv);
        if(colors){const auto* c=data(VERTEX_ARRAY_DIFFUSE,index);for(unsigned j=0;j<4;++j)v.color[j]=c[j]/255.f;}
        return v;
    }
    void setMatrix(const Matrix& matrix){g_glFuncTable.glMatrixMode(GL_TEXTURE);g_glFuncTable.glLoadMatrixf(matrix.data());}
    void restoreArrays(){
        const auto& p=attributes[VERTEX_ARRAY_POSITION];g_glFuncTable.glVertexPointer(3,GL_FLOAT,p.stride,p.pointer);
        const auto& t=attributes[VERTEX_ARRAY_TEX_COORD];g_glFuncTable.glTexCoordPointer(2,GL_FLOAT,t.stride,t.pointer);
        const auto& c=attributes[VERTEX_ARRAY_DIFFUSE];if(c.pointer)g_glFuncTable.glColorPointer(4,GL_UNSIGNED_BYTE,c.stride,c.pointer);
    }
    void rawDraw(GLenum type,i32 start,i32 count){g_glFuncTable.glDrawArrays(type,start,count);++counters.draws;counters.triangles+=type==GL_TRIANGLES?count/3:std::max(0,count-2);}
    void draw(PrimitiveType type,i32 start,i32 count){
        if(start<0||count<0)throw std::runtime_error("TH06 invalid vertex range");
        if(!count)return;
        auto found=textures.find(bound);
        if(!texcoords||found==textures.end()||!found->second.width){bindBase();rawDraw(primitive(type),start,count);return;}
        auto& tex=found->second;
        if(!paged||!powerOfTwo(tex.width)||!powerOfTwo(tex.height)||textureMatrix[3]!=0||textureMatrix[7]!=0||textureMatrix[15]==0){
            if(paged)++counters.fallbacks;ensureBase(tex);rawDraw(primitive(type),start,count);return;
        }
        float loU=INFINITY,loV=INFINITY,hiU=-INFINITY,hiV=-INFINITY;
        for(int i=0;i<count;++i){const auto t=uv(start+i,tex);loU=std::min(loU,t[0]);hiU=std::max(hiU,t[0]);loV=std::min(loV,t[1]);hiV=std::max(hiV,t[1]);}
        const int x=th06atlas::page(loU,tex.pageWidth),y=th06atlas::page(loV,tex.pageHeight);
        if(x==th06atlas::lastPage(loU,hiU,tex.pageWidth)&&y==th06atlas::lastPage(loV,hiV,tex.pageHeight)){
            ensurePage(tex,x,y);
            auto m=textureMatrix;
            for(unsigned c=0;c<4;++c){m[c*4]=textureMatrix[c*4]*(float(tex.width)/tex.pageWidth)-x*textureMatrix[c*4+3];m[c*4+1]=textureMatrix[c*4+1]*(float(tex.height)/tex.pageHeight)-y*textureMatrix[c*4+3];}
            setMatrix(m);rawDraw(primitive(type),start,count);counters.fastVertices+=count;
        }else{
            setMatrix(identity);batch.clear();GLuint batchId=0;
            auto flush=[&]{if(batch.empty())return;g_glFuncTable.glBindTexture(GL_TEXTURE_2D,batchId);
                g_glFuncTable.glVertexPointer(3,GL_FLOAT,sizeof(th06atlas::Vertex),batch[0].position);
                g_glFuncTable.glTexCoordPointer(2,GL_FLOAT,sizeof(th06atlas::Vertex),batch[0].uv);
                if(colors)g_glFuncTable.glColorPointer(4,GL_FLOAT,sizeof(th06atlas::Vertex),batch[0].color);
                rawDraw(GL_TRIANGLES,0,batch.size());batch.clear();};
            const int triangles=type==PRIM_TRIANGLES?count/3:std::max(0,count-2);
            for(int i=0;i<triangles;++i){
                const unsigned a=start+(type==PRIM_TRIANGLES?i*3:i);
                std::array<th06atlas::Vertex,3> input{vertex(a,tex),vertex(a+1,tex),vertex(a+2,tex)};
                if(type==PRIM_TRIANGLE_STRIP&&(i&1))std::swap(input[0],input[1]);
                th06atlas::split(input,tex.pageWidth,tex.pageHeight,[&](int px,int py,const auto& part){
                    const GLuint id=ensurePage(tex,px,py);
                    if(id!=batchId||batch.size()>=8190){flush();batchId=id;}
                    batch.insert(batch.end(),part.begin(),part.end());++counters.clipped;
                });
            }
            flush();restoreArrays();
        }
        setMatrix(textureMatrix);bindBase();
    }
};

RasterIXTextures::RasterIXTextures():impl(std::make_unique<Impl>()){}
RasterIXTextures::~RasterIXTextures()=default;
GfxTextureHandle RasterIXTextures::create(){const auto id=createRaw();impl->textures.emplace(id,Texture{});return id;}
void RasterIXTextures::bind(GfxTextureHandle id){impl->bound=id;impl->bindBase();}
void RasterIXTextures::erase(GfxTextureHandle id){if(!id)return;auto found=impl->textures.find(id);if(found==impl->textures.end())return;impl->releasePages(found->second);deleteRaw(id);impl->textures.erase(found);}
void RasterIXTextures::image(u32 width,u32 height,PixelFormat format,PixelDataType type,const void* raw){
    if(!width||!height||width>4096||height>4096)throw std::runtime_error("TH06 texture dimensions out of range");
    auto& tex=impl->textures.at(impl->bound);
    tex.sourceWidth=width;tex.sourceHeight=height;
    const u32 sourceWidth=width,sourceHeight=height;
    if(impl->balanced){width=std::max(1u,width/2);height=std::max(1u,height/2);}
    if(tex.width!=width||tex.height!=height){impl->releasePages(tex);tex.width=width;tex.height=height;tex.pageWidth=std::min(128u,width);tex.pageHeight=std::min(128u,height);tex.columns=(width+tex.pageWidth-1)/tex.pageWidth;tex.rows=(height+tex.pageHeight-1)/tex.pageHeight;tex.pages.resize(size_t(tex.columns)*tex.rows);}
    auto& storage=impl->balanced?tex.source:tex.pixels;
    storage.assign(size_t(sourceWidth)*sourceHeight*4,0);
    const auto* bytes=static_cast<const u8*>(raw);const auto* words=static_cast<const u16*>(raw);
    for(size_t i=0;i<size_t(sourceWidth)*sourceHeight;++i){auto* p=storage.data()+i*4;
        if(!raw){if(sourceWidth==1&&sourceHeight==1)std::fill(p,p+4,255);continue;}
        if(type==PIXEL_UNSIGNED_BYTE){const unsigned channels=format==PIXEL_RGBA?4:3;std::copy_n(bytes+i*channels,channels,p);if(channels==3)p[3]=255;}
        else{const auto v=words[i];
            if(type==PIXEL_UNSIGNED_SHORT_4_4_4_4){p[0]=((v>>12)&15)*17;p[1]=((v>>8)&15)*17;p[2]=((v>>4)&15)*17;p[3]=(v&15)*17;}
            else if(type==PIXEL_UNSIGNED_SHORT_5_5_5_1){p[0]=((v>>11)&31)*255/31;p[1]=((v>>6)&31)*255/31;p[2]=((v>>1)&31)*255/31;p[3]=(v&1)?255:0;}
            else{p[0]=((v>>11)&31)*255/31;p[1]=((v>>5)&63)*255/63;p[2]=(v&31)*255/31;p[3]=255;}
        }
    }
    if(impl->balanced){tex.pixels.resize(size_t(width)*height*4);th06atlas::reduce2x(tex.source.data(),sourceWidth,sourceHeight,tex.pixels.data(),width,0,0,width,height);}
    tex.baseDirty=true;for(auto& page:tex.pages)page.dirty=true;
    if(!impl->paged)impl->ensureBase(tex);
}
void RasterIXTextures::subImage(i32 x,i32 y,i32 width,i32 height,const void* raw){
    auto& tex=impl->textures.at(impl->bound);
    if(x<0||y<0||width<0||height<0||u32(x+width)>tex.sourceWidth||u32(y+height)>tex.sourceHeight||(!raw&&width&&height))throw std::runtime_error("TH06 subimage out of range");
    const auto* data=static_cast<const u8*>(raw);
    auto& storage=impl->balanced?tex.source:tex.pixels;
    for(i32 row=0;row<height;++row)for(i32 column=0;column<width;++column){auto* p=storage.data()+(size_t(y+row)*tex.sourceWidth+x+column)*4;std::copy_n(data+(size_t(row)*width+column)*3,3,p);p[3]=255;}
    const u32 x0=impl->balanced?x/2:x,y0=impl->balanced?y/2:y;
    const u32 x1=std::min(tex.width,impl->balanced?u32(x+width+1)/2:u32(x+width));
    const u32 y1=std::min(tex.height,impl->balanced?u32(y+height+1)/2:u32(y+height));
    if(impl->balanced&&width&&height)th06atlas::reduce2x(tex.source.data(),tex.sourceWidth,tex.sourceHeight,tex.pixels.data(),tex.width,x0,y0,x1,y1);
    if(width&&height)for(u32 py=y0/tex.pageHeight;py<=(y1-1)/tex.pageHeight;++py)for(u32 px=x0/tex.pageWidth;px<=(x1-1)/tex.pageWidth;++px)tex.pages[py*tex.columns+px].dirty=true;
    tex.baseDirty=true;if(!impl->paged)impl->ensureBase(tex);
}
void RasterIXTextures::attribute(VertexAttributeArrays kind,std::size_t stride,void* pointer){impl->attributes.at(kind)={static_cast<const u8*>(pointer),stride};}
void RasterIXTextures::toggle(u8 attributes,bool enabled){if(attributes&VERTEX_ATTR_TEX_COORD)impl->texcoords=enabled;if(attributes&VERTEX_ATTR_DIFFUSE)impl->colors=enabled;}
void RasterIXTextures::matrix(TransformMatrix kind,const ZunMatrix& matrix){if(kind==MATRIX_TEXTURE){static_assert(sizeof(matrix)==sizeof(Matrix),"Matrix layout");std::memcpy(impl->textureMatrix.data(),&matrix,sizeof(matrix));}}
void RasterIXTextures::filter(){impl->bindBase();nearest();}
void RasterIXTextures::draw(PrimitiveType type,i32 start,i32 count){impl->draw(type,start,count);}
void RasterIXTextures::frame(unsigned frame){impl->currentFrame=frame;}
const RasterIXTextures::Stats& RasterIXTextures::stats() const{return impl->counters;}
const char* RasterIXTextures::mode() const{return impl->balanced?"balanced":impl->paged?"native":"scaled";}
