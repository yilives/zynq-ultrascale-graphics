// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>
#include <stdexcept>
namespace rix_cnn_inplace {
struct Profile {
 uint32_t version,cycles,capabilities,atomic_abi;
};
inline Profile profile(uint32_t magic,uint32_t shape,uint32_t cycles,uint32_t capabilities,uint32_t abi) {
 if(shape!=((96u<<16)|160u))throw std::runtime_error("CNN shape mismatch");
 if(magic==0x4e4e5331)return {1,1843200,0,0};
 if(magic==0x4e4e5332){
  if(cycles!=414738||(capabilities&1)==0)throw std::runtime_error("NNS2 pipeline profile mismatch");
  return {2,cycles,capabilities,0x00020001};
 }
 if(magic==0x4e495031){
  if(cycles!=462816||(capabilities&13)!=13||(capabilities&~15u)!=0||abi!=0x00030001)
   throw std::runtime_error("NIP1 in-place profile mismatch");
  return {3,cycles,capabilities,0x00030001};
 }
 throw std::runtime_error("Unsupported CNN hardware identifier");
}
}
