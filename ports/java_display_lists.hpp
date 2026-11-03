// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "java_display_list_store.hpp"
#include "opengl/GLImpl.h"
#include "RIXGL.hpp"
#include "vertexpipeline/VertexArray.hpp"
#include "vertexpipeline/VertexPipeline.hpp"
#include <array>
#include <cstring>
#include <limits>
#include <cmath>

namespace java_lists {
inline Store& store(){static Store value([](uint32_t e){rr::RIXGL::getInstance().setError(e);});return value;}
template<class T>bool query(GLenum pname,T* output){
 uint32_t value;
 switch(pname){case GL_LIST_INDEX:value=store().active;break;case GL_LIST_MODE:value=store().mode;break;
  case GL_LIST_BASE:value=store().base;break;case GL_MAX_LIST_NESTING:value=64;break;default:return false;}
 if(output){if constexpr(sizeof(T)==1)*output=value!=0;else *output=static_cast<T>(value);}return true;
}
inline bool unsupported(){if(!store().capturing())return false;store().fail(INVALID_OPERATION);return true;}
inline bool beginCommand(GLenum mode){
 if(!store().capturing())return true;
 if(mode>GL_POLYGON){store().fail(INVALID_ENUM);return false;}
 if(store().primitive){store().fail(INVALID_OPERATION);return false;}
 store().primitive=true;return true;
}
inline bool endCommand(){
 if(!store().capturing())return true;
 if(!store().primitive){store().fail(INVALID_OPERATION);return false;}
 store().primitive=false;return true;
}
inline bool serverAllowed(bool insideBegin){
 if(store().capturing()&&store().primitive&&!insideBegin){store().fail(INVALID_OPERATION);return false;}return true;
}
struct OwnedBatch {
 std::vector<rr::Vec4> vertex,color;
 std::vector<rr::Vec3> normal;
 std::vector<float> point;
 std::array<std::vector<rr::Vec4>,rr::RenderConfig::TMU_COUNT> tex;
 rr::DrawMode mode;
 explicit OwnedBatch(const rr::RenderObj&source):mode(source.getDrawMode()){
  const size_t n=source.getCount();vertex.reserve(n);
  if(source.colorArrayEnabled())color.reserve(n);
  if(source.normalArrayEnabled())normal.reserve(n);
  if(source.pointSizeArrayEnabled())point.reserve(n);
  for(size_t t=0;t<tex.size();++t)if(source.texCoordArrayEnabled()[t])tex[t].reserve(n);
  for(size_t i=0;i<n;++i){const auto index=source.getIndex(i);vertex.push_back(source.getVertex(index));
   if(source.colorArrayEnabled())color.push_back(source.getColor(index));
   if(source.normalArrayEnabled())normal.push_back(source.getNormal(index));
   if(source.pointSizeArrayEnabled())point.push_back(source.getPointSize(index));
   for(size_t t=0;t<tex.size();++t)if(source.texCoordArrayEnabled()[t])tex[t].push_back(source.getTexCoord(t,index));
  }
 }
 size_t bytes()const{
  size_t n=sizeof(*this)+vertex.size()*sizeof(rr::Vec4)+color.size()*sizeof(rr::Vec4)+normal.size()*sizeof(rr::Vec3)+point.size()*sizeof(float);
  for(const auto&v:tex)n+=v.size()*sizeof(rr::Vec4);return n;
 }
 void replay()const{
  // Only constants come from call-time state; compiled arrays own all their data.
  auto&gl=rr::RIXGL::getInstance();rr::RenderObj obj=gl.vertexArray().renderObj();
  obj.enableIndices(false);obj.setArrayOffset(0);obj.setCount(vertex.size());obj.setDrawMode(mode);
  obj.enableVertexArray(true);obj.setVertexSize(4);obj.setVertexType(rr::Type::FLOAT);obj.setVertexStride(sizeof(rr::Vec4));obj.setVertexPointer(vertex.data());
  obj.enableColorArray(!color.empty());if(!color.empty()){obj.setColorSize(4);obj.setColorType(rr::Type::FLOAT);obj.setColorStride(sizeof(rr::Vec4));obj.setColorPointer(color.data());}
  obj.enableNormalArray(!normal.empty());if(!normal.empty()){obj.setNormalType(rr::Type::FLOAT);obj.setNormalStride(sizeof(rr::Vec3));obj.setNormalPointer(normal.data());}
  obj.enablePointSizeArray(!point.empty());if(!point.empty()){obj.setPointSizeType(rr::Type::FLOAT);obj.setPointSizeStride(sizeof(float));obj.setPointSizePointer(point.data());}
  for(size_t t=0;t<tex.size();++t){obj.enableTexCoordArray(t,!tex[t].empty());if(!tex[t].empty()){obj.setTexCoordSize(t,4);obj.setTexCoordType(t,rr::Type::FLOAT);obj.setTexCoordStride(t,sizeof(rr::Vec4));obj.setTexCoordPointer(t,tex[t].data());}}
  gl.pipeline().drawObj(obj);
 }
};
inline bool captureArray(const rr::RenderObj&obj){
 if(!store().capturing())return false;
 if(store().primitive){store().fail(INVALID_OPERATION);return true;}
 if(!obj.vertexArrayEnabled()||!obj.getCount())return store().mode==COMPILE;
 const size_t maximum=sizeof(rr::Vec4)*(2+rr::RenderConfig::TMU_COUNT)+sizeof(rr::Vec3)+sizeof(float);
 if(obj.getCount()>store().available()/maximum){store().fail(OUT_OF_MEMORY);return true;}
 try{
  auto data=std::make_shared<OwnedBatch>(obj);
  const bool added=store().append([data]{data->replay();},data->bytes());
  return !added||store().mode==COMPILE;
 }catch(const std::bad_alloc&){store().fail(OUT_OF_MEMORY);return true;}
}
inline void callList(GLuint id){Store::Guard guard(store(),[id]{store().call(id);});if(!guard.skip)store().call(id);}
inline void callLists(GLsizei count,GLenum type,const void*pointer){
 if(count<0){store().fail(INVALID_VALUE);return;}if(!count)return;
 if(!pointer){store().fail(INVALID_VALUE);return;}
 if(size_t(count)>store().available()/sizeof(uint32_t)){store().fail(OUT_OF_MEMORY);return;}
 std::vector<uint32_t> ids;ids.reserve(count);const auto*p=static_cast<const uint8_t*>(pointer);
 for(int i=0;i<count;++i){uint32_t value=0;
  switch(type){
   case GL_BYTE:{int8_t v;std::memcpy(&v,p+i,1);value=v;break;}
   case GL_UNSIGNED_BYTE:value=p[i];break;
   case GL_SHORT:{int16_t v;std::memcpy(&v,p+i*2,2);value=v;break;}
   case GL_UNSIGNED_SHORT:{uint16_t v;std::memcpy(&v,p+i*2,2);value=v;break;}
   case GL_INT:case GL_UNSIGNED_INT:std::memcpy(&value,p+i*4,4);break;
   case GL_FLOAT:{float v;std::memcpy(&v,p+i*4,4);if(!std::isfinite(v)||v<-2147483648.0||v>4294967295.0){store().fail(INVALID_VALUE);return;}value=uint32_t(int64_t(v));break;}
   case GL_2_BYTES:case GL_3_BYTES:case GL_4_BYTES:{const unsigned bytes=type-GL_2_BYTES+2;for(unsigned b=0;b<bytes;++b)value=(value<<8)|p[i*bytes+b];break;}
   default:store().fail(INVALID_ENUM);return;
  }ids.push_back(value);
 }
 auto execute=[ids]{for(uint32_t id:ids)store().call(store().base+id);};
 Store::Guard guard(store(),execute,ids.size()*sizeof(uint32_t));if(!guard.skip)execute();
}
}
