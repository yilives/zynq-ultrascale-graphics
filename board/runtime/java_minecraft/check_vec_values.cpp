// SPDX-License-Identifier: GPL-3.0-or-later
#include "math/Vec.hpp"
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <type_traits>
#include <utility>
template<size_t N> __attribute__((noinline)) rr::Vec<N> returned(rr::Vec<N> input){return input;}
template<size_t N> bool check(std::ofstream& output){
    uint32_t state=0x19aac437;const uint32_t special[]={0,0x80000000,0x7f800000,0xff800000,0x7fc12345,0x7f812345,1,0x807fffff};
    for(unsigned row=0;row<2048;row++){
        uint32_t bits[N];float values[N];
        for(size_t i=0;i<N;i++){state=state*1664525+1013904223;bits[i]=row<8?special[(row+i)%8]:state;std::memcpy(values+i,bits+i,4);}
        rr::Vec<N> source;source.fromArray(values,N);rr::Vec<N> copy(source);rr::Vec<N> moved(std::move(copy));const rr::Vec<N> constant(source);
        rr::Vec<N> const_moved(std::move(constant));rr::Vec<N> assigned;assigned=source;assigned=std::move(assigned);
        rr::Vec<N> roundtrip=returned<N>(source);
        for(const auto* value:{&source,&moved,&const_moved,&assigned,&roundtrip})for(size_t i=0;i<N;i++){
            uint32_t actual;float component=(*value)[i];std::memcpy(&actual,&component,4);if(actual!=bits[i])return false;output.write(reinterpret_cast<const char*>(&actual),4);
        }
    }return true;
}
int main(int argc,char**argv){
    if(argc!=2)return 2;std::ofstream output(argv[1],std::ios::binary);
    if(sizeof(rr::Vec4)!=16||alignof(rr::Vec4)!=4||!check<2>(output)||!check<3>(output)||!check<4>(output)||!output)return 3;
    std::cout<<"VECTOR_VALUES_PASS sizes=2,3,4 patterns=6144 copies_per_pattern=5 nan_payload=1 negative_zero=1 self_move=1 trivial="<<std::is_trivially_copyable<rr::Vec4>::value<<"\n";
}
