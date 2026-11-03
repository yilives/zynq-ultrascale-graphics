// Test the private hardware uniform accessor against the independent codec.
#pragma once
#include "uniforms.hpp"
#include <array>
#include <stdexcept>
#include <iostream>
inline void geometryUniformSchemaCheck(const rr::vertextransformer::VertexTransformerData&input){
 static bool complete=false;if(complete)return;complete=true;
 std::array<uint32_t,rixgeo::STATE_WORDS> original{},words{},roundtrip{};
 auto data=input;bool scissor=false;int32_t box[4]={};uint32_t mask=3;
 if(!rixgeo::state<false>(original.data(),data,scissor,box,mask)||original[2]!=434)throw std::runtime_error("uniform schema source");
 unsigned comparisons=0;
 for(unsigned i=0;i<434;i++)for(uint32_t pattern:{0x7fc10001u,2u,0xffffffffu}){
  words=original;words[i]=pattern;auto decoded=input;bool a=false,b=false;int32_t ab[4]={},bb[4]={};uint32_t am=0,bm=0;
  bool expected=rixgeo::state<true>(words.data(),decoded,a,ab,am);
  bool actual=rixgeo::loadUniforms(words.data(),b,bb,bm);
  if(expected!=actual)throw std::runtime_error("uniform validation mismatch word "+std::to_string(i));
  ++comparisons;
 }
 words=original;
 for(unsigned i=4;i<434;i++){
  if(rixgeo::uniformKinds[i]==1)words[i]=rixgeo::bits(.125f+float(i)*.001f);
  else if(rixgeo::uniformKinds[i]==2)words[i]=i&1;
 }
 if(!rixgeo::loadUniforms(words.data(),scissor,box,mask))throw std::runtime_error("uniform varied input rejected");
 auto materialized=rixgeo::materializeUniformsForTest();
 if(!rixgeo::state<false>(roundtrip.data(),materialized,scissor,box,mask))throw std::runtime_error("uniform materialization invalid");
 for(unsigned i=0;i<434;i++)if(words[i]!=roundtrip[i])throw std::runtime_error("uniform accessor mismatch word "+std::to_string(i));
 std::cout<<"GEOMETRY_UNIFORM_SCHEMA_PASS words=434 validator_comparisons="<<comparisons<<" varied_roundtrip=1\n";
}
