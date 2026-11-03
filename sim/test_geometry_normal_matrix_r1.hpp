#pragma once
#include "normal_matrix.hpp"
#include <stdexcept>
#include <iostream>
inline void geometryNormalMatrixCheck(){
 uint32_t seed=0x61462ba1u;
 unsigned checked=0;
 for(unsigned test=0;test<1030;test++){
  rr::Mat44 reference;
  for(unsigned i=0;i<16;i++){
   seed=seed*1664525u+1013904223u;
   float value=float(int((seed>>8)%2049)-1024)/2048.0f;
   if(i/4==i%4)value+=2.0f;
   if(test==0)value=0;
   if(test==1)value=i/4==i%4?1.0f:0.0f;
   if(test==2)value=float(i%4+1); // Rank one, invert() fails.
   if(test==3)value=i/4==i%4?-0.0f:0.0f;
   if(test==4)value=i/4==i%4?float(i+1)*.125f:0.0f;
   reference[i/4][i%4]=value;
   rixgeo::uniformWords[4+i]=rixgeo::bits(value);
   rixgeo::normalMatrixInput[i]=rixgeo::floating(0x7fc50001u+i);
   rixgeo::normalMatrixInverse[i]=rixgeo::floating(0x7fc50101u+i);
   rixgeo::normalMatrixStore[i/4][i%4]=rixgeo::floating(0x7fc50201u+i);
  }
  reference.invert();reference.transpose();
  rixgeo::prepareNormalMatrix();
  for(unsigned i=0;i<16;i++){
   const uint32_t expected=rixgeo::bits(reference[i/4][i%4]);
   const uint32_t actual=rixgeo::bits(rixgeo::normalMatrixStore[i/4][i%4]);
   if(expected!=actual)throw std::runtime_error("PL normal matrix differs from untouched Mat44 inverse");
   ++checked;
  }
 }
 std::cout<<"GEOMETRY_NORMAL_MATRIX_PASS matrices=1030 bit_exact_fields="<<checked<<" scratch_poisoned=1\n";
}
