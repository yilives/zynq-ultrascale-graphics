// SPDX-License-Identifier: MIT
#include "cnn_profile.hpp"
#include <iostream>
int main(){
 using rix_cnn_inplace::profile;
 constexpr uint32_t shape=(96u<<16)|160u;
 unsigned checks=0;
 auto require=[&](bool ok){if(!ok)throw std::runtime_error("profile test failed");++checks;};
 auto legacy=profile(0x4e4e5331,shape,0,0,0);require(legacy.version==1&&legacy.cycles==1843200&&legacy.capabilities==0);
 auto pipelined=profile(0x4e4e5332,shape,414738,3,0);require(pipelined.version==2&&pipelined.atomic_abi==0x20001);
 auto atomic=profile(0x4e4e5332,shape,414738,7,0x20001);require(atomic.capabilities==7);
 for(uint32_t cap:{13u,15u}){auto p=profile(0x4e495031,shape,462816,cap,0x30001);require(p.version==3&&p.cycles==462816&&p.capabilities==cap);}
 auto reject=[&](uint32_t id,uint32_t dim,uint32_t cycles,uint32_t cap,uint32_t abi){
  bool failed=false;try{profile(id,dim,cycles,cap,abi);}catch(const std::runtime_error&){failed=true;}require(failed);
 };
 reject(0,shape,462816,15,0x30001);
 reject(0x4e495031,0,462816,15,0x30001);
 reject(0x4e495031,shape,414738,15,0x30001);
 reject(0x4e495031,shape,462815,15,0x30001);
 reject(0x4e495031,shape,462817,15,0x30001);
 for(uint32_t cap:{0u,1u,3u,5u,7u,9u,12u,31u})reject(0x4e495031,shape,462816,cap,0x30001);
 reject(0x4e495031,shape,462816,15,0x20001);
 reject(0x4e4e5332,shape,462816,7,0x20001);
 reject(0x4e4e5332,shape,414738,0,0x20001);
 std::cout<<"PASS CNN_INPLACE_PROFILE checks="<<checks<<"\n";
}
