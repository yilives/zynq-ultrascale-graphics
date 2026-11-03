// SPDX-License-Identifier: GPL-3.0-or-later
#include "java_prepared_arrays.hpp"
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
static uint32_t seed=0x136a2497;
static float value(){const uint32_t specials[]={0,0x80000000,0x7fc12345,0x7f812345,0x7f800000,0xff800000,1,0x807fffff};seed=seed*1664525+1013904223;uint32_t bits=(seed&7)==0?specials[(seed>>4)&7]:seed;float f;std::memcpy(&f,&bits,4);return f;}
template<size_t N> rr::Vec<N> vector(){rr::Vec<N> v;for(size_t i=0;i<N;i++)v[i]=value();return v;}
static uint64_t digest=1469598103934665603ull;
static void equal(float a,float b){uint32_t x,y;std::memcpy(&x,&a,4);std::memcpy(&y,&b,4);if(x!=y)throw std::runtime_error("Float bits differ");digest=(digest^x)*1099511628211ull;}
template<size_t N> void equal(const rr::Vec<N>&a,const rr::Vec<N>&b){for(size_t i=0;i<N;i++)equal(a[i],b[i]);}
int main(){
 static_assert(rr::RenderConfig::TMU_COUNT==2,"Actual dual profile required");
 constexpr size_t n=257;size_t compared=0;
 for(unsigned mask=0;mask<32;mask++){
  std::vector<rr::Vec4> positions(n),colors;std::vector<rr::Vec3> normals;std::vector<float> points;
  std::array<std::vector<rr::Vec4>,2> coordinates;
  for(auto&v:positions)v=vector<4>();
  if(mask&1){colors.resize(n);for(auto&v:colors)v=vector<4>();}
  if(mask&2){normals.resize(n);for(auto&v:normals)v=vector<3>();}
  if(mask&4){points.resize(n);for(auto&v:points)v=value();}
  for(size_t t=0;t<2;t++)if(mask&(8<<t)){coordinates[t].resize(n);for(auto&v:coordinates[t])v=vector<4>();}
  for(unsigned call=0;call<3;call++){
   rr::RenderObj obj;obj.enableIndices(false);obj.setArrayOffset(0);obj.setCount(n);obj.enableVertexArray(true);
   obj.setVertexSize(4);obj.setVertexType(rr::Type::FLOAT);obj.setVertexStride(sizeof(rr::Vec4));obj.setVertexPointer(positions.data());
   obj.setVertexColor(vector<4>());obj.setNormal(vector<3>());obj.setPointSize(value());
   obj.enableColorArray(!colors.empty());obj.setColorSize(4);obj.setColorType(rr::Type::FLOAT);obj.setColorStride(sizeof(rr::Vec4));obj.setColorPointer(colors.data());
   obj.enableNormalArray(!normals.empty());obj.setNormalType(rr::Type::FLOAT);obj.setNormalStride(sizeof(rr::Vec3));obj.setNormalPointer(normals.data());
   obj.enablePointSizeArray(!points.empty());obj.setPointSizeType(rr::Type::FLOAT);obj.setPointSizeStride(sizeof(float));obj.setPointSizePointer(points.data());
   for(size_t t=0;t<2;t++){obj.setTexCoord(t,vector<4>());obj.enableTexCoordArray(t,!coordinates[t].empty());obj.setTexCoordSize(t,4);obj.setTexCoordType(t,rr::Type::FLOAT);obj.setTexCoordStride(t,sizeof(rr::Vec4));obj.setTexCoordPointer(t,coordinates[t].data());}
   java_prepared::View view(obj,positions,colors,normals,points,coordinates);
   for(size_t i=0;i<n;i++){
    auto p=view.at(i);if(p.sourceIndex!=obj.getIndex(i))return 2;
    equal(p.vertex,obj.getVertex(i));equal(p.color,obj.getColor(i));equal(p.normal,obj.getNormal(i));equal(p.pointSize,obj.getPointSize(i));
    for(size_t t=0;t<2;t++)equal(p.tex[t],obj.getTexCoord(t,i));++compared;
   }
  }
 }
 std::cout<<"JAVA_PREPARED_BITS_PASS masks=32 call_states=3 vertices="<<compared<<" digest="<<std::hex<<digest<<" nan_payload=1 signed_zero=1 tmu=2\n";
}
