#pragma once
#include "renderer/commands/Op.hpp"
#include "renderer/registers/StencilReg.hpp"
#include <array>
#include <vector>
#include <cmath>
#include <cstring>
#include <cstdint>
#include <stdexcept>
#include <string>
// Criteria fixed before RTL/board runs. Command headers, integer bounding boxes
// and all edge equations are exact. No whole-descriptor relative-error shortcut.
namespace geometry_numeric {
inline double maxAbs=0;inline uint64_t floats=0,integerWords=0;
inline void compare(const std::array<std::vector<uint32_t>,3>&actual,
                    const std::array<std::vector<uint32_t>,3>&expected,const char*name){
 auto fail=[&](const std::string&reason){throw std::runtime_error(std::string(name)+": "+reason);};
 for(unsigned band=0;band<3;band++){
  if(actual[band].size()!=expected[band].size())fail("band word count differs");
  for(size_t at=0;at<expected[band].size();){
   const auto*a=actual[band].data()+at;const auto*e=expected[band].data()+at;
   if(a[0]!=e[0])fail("GPU opcode differs");++integerWords;
   if(e[0]==(rr::op::RENDER_CONFIG|rr::StencilReg::getAddr())){
    if(at+2>expected[band].size()||a[1]!=e[1])fail("stencil differs");++integerWords;at+=2;continue;
   }
   if(e[0]!=0x300000c0||at+49>expected[band].size())fail("unexpected GPU command");
   for(unsigned word=0;word<48;word++){
    if(word<12){if(a[word+1]!=e[word+1])fail("integer geometry differs field "+std::to_string(word));++integerWords;continue;}
    float af,ef;std::memcpy(&af,a+word+1,4);std::memcpy(&ef,e+word+1,4);
    if(!std::isfinite(af)||!std::isfinite(ef))fail("non-finite attribute");
    bool initial=(word<16)||(word>=24&&word<26)||(word>=30&&(word-30)%9<3);
    double tolerance=(initial?4e-6:1e-7)+2e-5*std::abs(double(ef));
    double error=std::abs(double(af)-double(ef));if(error>maxAbs)maxAbs=error;++floats;
    if(error>tolerance)fail("float geometry differs field "+std::to_string(word)+" error="+std::to_string(error));
   }
   at+=49;
  }
 }
}
}
