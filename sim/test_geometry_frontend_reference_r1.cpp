// SPDX-License-Identifier: GPL-3.0-or-later
// Golden fixtures from the frozen working ARM pipeline; no hardware access.
#include "SequentialVertexTransformer.hpp"
#include "geometry_vertex_f32_r1.hpp"
#include "renderer/Rasterizer.hpp"
#include "renderer/commands/Op.hpp"
#include "renderer/commands/TriangleStreamCmd.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <vector>
namespace fs=std::filesystem;
using V=rix_geometry_r1::VertexF32;
using Desc=rr::TriangleStreamTypes::TriangleDesc;
static_assert(sizeof(Desc)==192);
static void require(bool b,const char*s){if(!b)throw std::runtime_error(s);}
static void u32(std::ofstream&f,uint32_t v){for(unsigned i=0;i<4;i++)f.put(char(v>>(i*8)));}
static V vertex(float x,float y,float z=0,float w=1){
 V v{};v.position[0]=x;v.position[1]=y;v.position[2]=z;v.position[3]=w;
 v.color[0]=(x+1)*.25f;v.color[1]=(y+1)*.25f;v.color[2]=.75f;v.color[3]=1;
 for(unsigned t=0;t<2;t++){v.texture[t][0]=x*.25f+float(t)*.125f;v.texture[t][1]=y*.25f;v.texture[t][3]=1;}
 v.normal[2]=1;v.point_size=3;return v;
}
static void clear(Desc&d){
 auto&p=d.param;p.reserved=0;p.bbStartX=p.bbStartY=p.bbEndX=p.bbEndY=0;
 for(unsigned i=0;i<3;i++)p.wInit[i]=p.wXInc[i]=p.wYInc[i]=0;
 p.color.init();p.colorXInc.init();p.colorYInc.init();p.depthZw.init();p.depthZwXInc.init();p.depthZwYInc.init();
 for(auto&t:d.texture){t.texStq.init();t.texStqXInc.init();t.texStqYInc.init();}
}
struct Case{const char*name;std::vector<V>vertices;rr::DrawMode mode=rr::DrawMode::TRIANGLES;int option=0;int expected=-1;};
static rr::vertextransformer::VertexTransformerData state(const Case&c){
 rr::vertextransformer::VertexTransformerData d{};d.transformMatrices.modelView.identity();d.transformMatrices.projection.identity();d.transformMatrices.color.identity();
 for(auto&m:d.transformMatrices.texture)m.identity();d.tmuEnabled.set();
 d.viewPort.viewportWidth=400;d.viewPort.viewportHeight=240;d.viewPort.viewportWidthHalf=200;d.viewPort.viewportHeightHalf=120;d.viewPort.depthRangeScale=.5f;d.viewPort.depthRangeOffset=.5f;
 d.primitiveAssembler.mode=c.mode;d.primitiveAssembler.primitiveCount=c.vertices.size();
 if(c.option==1){
  const float a[16]={.937f,.071f,0,0,-.071f,.937f,.013f,0,.021f,0,.983f,0,.017f,-.03f,.021f,1};
  const float b[16]={.941f,0,0,0,0,1.057f,0,0,0,0,.877f,.113f,0,0,.017f,1};
  const float t[16]={.75f,0,0,0,0,.625f,0,0,0,0,1,0,.125f,.25f,0,1};
  d.transformMatrices.modelView=rr::Mat44(a);d.transformMatrices.projection=rr::Mat44(b);d.transformMatrices.texture[0]=rr::Mat44(t);d.transformMatrices.texture[1]=rr::Mat44(b);
 }
 if(c.option==2){d.planeClipper.enabledMask=1;d.planeClipper.equations[0]=rr::Vec4{1,0,0,0};}
 if(c.option==3)d.shadeModel.shadeModelFlat=true;
 if(c.option==4){d.polygonOffset.enable=true;d.polygonOffset.factor=.25f;d.polygonOffset.units=.5f;}
 if(c.option==5){d.lighting.lightingEnabled=true;d.lighting.lightEnable[0]=true;}
 if(c.option==6){d.culling.enableCulling=true;d.culling.cullMode=rr::Face::FRONT_AND_BACK;}
 if(c.option==7)d.tmuEnabled[1]=false;
 return d;
}
int main(int argc,char**argv){try{
 require(argc==2,"Output directory argument required");uint32_t endian=1;require(*reinterpret_cast<uint8_t*>(&endian)==1,"Only little-endian fixture encoding supported");
 fs::path out=argv[1];require(!fs::exists(out),"Preserve existing fixture outputs");require(fs::create_directory(out),"Fixture directory creation failed");
 const std::vector<V>tri={vertex(-.4f,-.4f),vertex(.4f,-.4f),vertex(0,.4f)};
 std::vector<Case>cases={{"inside",tri,rr::DrawMode::TRIANGLES,0,1}};
 const char*names[6]={"left","right","bottom","top","near","far"};
 for(unsigned plane=0;plane<6;plane++){
  auto v=tri;unsigned axis=plane/2;float edge=plane%2?2.0f:-2.0f;
  for(auto&p:v)p.position[axis]=edge;
  cases.push_back({nullptr,v,rr::DrawMode::TRIANGLES,0,0});
  // Names for generated cases are fixed below to avoid temporary storage.
  v=tri;v[axis==1?2:0].position[axis]=edge;
  cases.push_back({nullptr,v,rr::DrawMode::TRIANGLES,0,2});
 }
 std::vector<std::string>stableNames;stableNames.reserve(12);
 for(unsigned p=0;p<6;p++){stableNames.push_back(std::string("outside_")+names[p]);cases[1+2*p].name=stableNames.back().c_str();stableNames.push_back(std::string("cross_")+names[p]);cases[2+2*p].name=stableNames.back().c_str();}
 cases.push_back({"multi_plane",{vertex(-3,-3),vertex(3,-3),vertex(0,3)},rr::DrawMode::TRIANGLES,0,-1});
 cases.push_back({"degenerate",{vertex(0,0),vertex(0,0),vertex(0,0)},rr::DrawMode::TRIANGLES,0,0});
 cases.push_back({"two_position_and_texture_matrices",tri,rr::DrawMode::TRIANGLES,1,-1});
 cases.push_back({"varying_w",{vertex(-.2f,-.2f,0,.5f),vertex(.4f,-.4f,0,1),vertex(0,.2f,0,.5f)},rr::DrawMode::TRIANGLES,0,1});
 cases.push_back({"quad_three_bands",{vertex(-.8f,-.9f),vertex(.8f,-.9f),vertex(.8f,.9f),vertex(-.8f,.9f)},rr::DrawMode::QUADS,0,2});
 cases.push_back({"triangle_strip",{vertex(-.8f,-.8f),vertex(.8f,-.8f),vertex(-.8f,.8f),vertex(.8f,.8f)},rr::DrawMode::TRIANGLE_STRIP,0,2});
 cases.push_back({"line",{vertex(-.4f,-.4f),vertex(.4f,.4f)},rr::DrawMode::LINES,0,-1});
 cases.push_back({"point",{vertex(.1f,.2f)},rr::DrawMode::POINTS,0,-1});
 cases.push_back({"user_clip_plane",tri,rr::DrawMode::TRIANGLES,2,-1});
 cases.push_back({"flat_color",tri,rr::DrawMode::TRIANGLES,3,1});
 cases.push_back({"polygon_offset",tri,rr::DrawMode::TRIANGLES,4,1});
 cases.push_back({"fixed_function_light0",tri,rr::DrawMode::TRIANGLES,5,1});
 cases.push_back({"cull_all",tri,rr::DrawMode::TRIANGLES,6,0});
 cases.push_back({"single_tmu",tri,rr::DrawMode::TRIANGLES,7,1});
 std::ofstream report(out/"reference.json");report<<"{\"passed\":true,\"hardware_access\":false,\"vertex_stride\":80,\"descriptor_bytes\":192,\"cases\":[";
 unsigned total=0,totalBands=0,idx=0;
 for(const auto&c:cases){
  auto data=state(c);rr::Rasterizer rasterizer(true);rasterizer.enableTmu(0,true);rasterizer.enableTmu(1,c.option!=7);
  std::vector<Desc>descriptors;unsigned drawn=0;
  auto draw=[&](const rr::TransformedTriangle&t){++drawn;Desc d;clear(d);if(rasterizer.rasterize(d,t))descriptors.push_back(d);return true;};
  auto stencil=[](const rr::StencilReg&){return true;};
  rr::vertextransformer::SequentialVertexTransformerCalc<decltype(draw),decltype(stencil)>calc(data,draw,stencil);calc.init();
  for(size_t k=0;k<c.vertices.size();k++){
   const auto&v=c.vertices[k];rr::VertexParameter p;p.sourceIndex=k;p.vertex=rr::Vec4(v.position);p.color=rr::Vec4(v.color);p.normal=rr::Vec3(v.normal);p.pointSize=v.point_size;
   for(unsigned t=0;t<2;t++)p.tex[t]=rr::Vec4(v.texture[t]);require(calc.pushSequentialVertex(p),"Frozen transform rejected input");
  }
  if(c.expected>=0)require(descriptors.size()==size_t(c.expected),c.name);else require(!descriptors.empty(),c.name);
  require(descriptors.size()<=7||c.mode!=rr::DrawMode::TRIANGLES,"Unexpected clipping expansion");
  std::ofstream input(out/(std::string(c.name)+".vertices.bin"),std::ios::binary);input.write(reinterpret_cast<const char*>(c.vertices.data()),c.vertices.size()*sizeof(V));
  std::ofstream legacy(out/(std::string(c.name)+".triangles.bin"),std::ios::binary),bands(out/(std::string(c.name)+".bands.bin"),std::ios::binary);unsigned nband=0;
  for(const auto&d:descriptors)legacy.write(reinterpret_cast<const char*>(&d),sizeof(d));
  // Preserve draw order within each band, matching the real renderer schedule.
  for(unsigned band=0;band<3;band++)for(const auto&d:descriptors)
   if(rr::Rasterizer::checkIfTriangleIsInBounds(d.param,band*80,(band+1)*80)){
    Desc copy=d;require(rr::Rasterizer::increment(copy,band*80,(band+1)*80),"Band adjustment failed");u32(bands,band);u32(bands,rr::TriangleStreamCmd::command());bands.write(reinterpret_cast<const char*>(&copy),sizeof(copy));++nband;
  }
  require(input.good()&&legacy.good()&&bands.good(),"Fixture write failed");
  if(idx++)report<<',';report<<"{\"name\":\""<<c.name<<"\",\"option\":"<<c.option<<",\"draw_mode\":"<<unsigned(c.mode)<<",\"input_vertices\":"<<c.vertices.size()<<",\"assembled_triangles\":"<<drawn<<",\"visible_triangles\":"<<descriptors.size()<<",\"band_commands\":"<<nband<<"}";
  total+=descriptors.size();totalBands+=nband;
 }
 report<<"],\"triangles\":"<<total<<",\"band_commands\":"<<totalBands<<"}\n";require(report.good(),"JSON write failed");
 std::cout<<"GEOMETRY_REFERENCE_PASS cases="<<cases.size()<<" triangles="<<total<<" band_commands="<<totalBands<<" no_hardware_access=1\n";return 0;
}catch(const std::exception&e){std::cerr<<"GEOMETRY_REFERENCE_FAILED "<<e.what()<<'\n';return 1;}}
