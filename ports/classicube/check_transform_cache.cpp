// SPDX-License-Identifier: GPL-3.0-or-later
#include "transform/VertexTransformer.hpp"
#include "renderer/Triangle.hpp"
#include <fstream>
#include <iostream>
#include <random>

int main(int argc,char**argv){
    if(argc!=2)return 2;
    rr::vertextransformer::VertexTransformerData data;
    data.transformMatrices.modelView.identity();data.transformMatrices.projection.identity();
    data.transformMatrices.color.identity();for(auto&m:data.transformMatrices.texture)m.identity();
    data.tmuEnabled.set();data.viewPort.viewportWidth=400;data.viewPort.viewportHeight=240;
    data.viewPort.viewportWidthHalf=200;data.viewPort.viewportHeightHalf=120;
    std::ofstream output(argv[1],std::ios::binary);unsigned triangles=0;
    auto vec=[&](const rr::Vec4&v){for(unsigned i=0;i<4;i++){float f=v[i];output.write(reinterpret_cast<const char*>(&f),4);}};
    auto draw=[&](const rr::TransformedTriangle&t){
        vec(t.vertex0);vec(t.vertex1);vec(t.vertex2);vec(t.color0);vec(t.color1);vec(t.color2);
        for(unsigned i=0;i<rr::RenderConfig::TMU_COUNT;i++){vec(t.texture0[i]);vec(t.texture1[i]);vec(t.texture2[i]);}
        triangles++;return true;
    };
    auto stencil=[](auto){return true;};
    rr::vertextransformer::VertexTransformerCalc<decltype(draw),decltype(stencil)> calc(data,draw,stencil);
    std::mt19937 rng(32159);auto f=[&](){return float(int(rng()%3001)-1500)/1000.0f;};
    const rr::DrawMode modes[]={rr::DrawMode::QUADS,rr::DrawMode::TRIANGLES,rr::DrawMode::LINES,rr::DrawMode::POINTS};
    for(unsigned d=0;d<96;d++){
        data.primitiveAssembler.mode=modes[d%4];data.primitiveAssembler.primitiveCount=120;
        float matrix[16]={1,0,0,0,0,1,0,0,0,0,1,0,float(d%7)*.01f,0,0,1};
        data.transformMatrices.modelView=rr::Mat44(matrix);
        calc.init();
        rr::VertexParameter pool[256];
        for(unsigned i=0;i<256;i++){
            auto&p=pool[i];p.sourceIndex=i;p.vertex=rr::Vec4{f(),f(),f()*.5f,1};
            p.color=rr::Vec4{float(i%17)/16,float(i%13)/12,float(i%11)/10,1};
            p.normal=rr::Vec3{0,0,1};p.pointSize=1;
            for(auto&t:p.tex)t=rr::Vec4{f(),f(),0,1};
        }
        for(unsigned i=0;i<120;i++)if(!calc.pushVertex(pool[d%2?i%24:(i*13)%256]))return 3;
    }
    if(triangles<500||!output)return 4;
    std::cout<<"TRANSFORM_CACHE_FIXTURE triangles="<<triangles<<" draws=96 vertices=11520\n";
}
