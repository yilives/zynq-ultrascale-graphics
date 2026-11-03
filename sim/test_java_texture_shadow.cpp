// SPDX-License-Identifier: GPL-3.0-or-later
#include "../ports/java_texture_shadow.hpp"
#include <array>
#include <cassert>
#include <iostream>
#include <random>
int main(){
    constexpr unsigned base=128,page=16,pages=64;rr::TexturePageShadow<page,pages,base> cache;
    std::array<uint8_t,1400> actual{},expected{};unsigned calls=0;std::array<uint8_t,64> input{};input.fill(23);
    auto send=[&](const uint8_t* data,std::size_t size,uint32_t address){assert(address+size<=actual.size());std::copy_n(data,size,actual.data()+address);++calls;return true;};
    auto apply=[&](uint32_t address,const uint8_t* data,std::size_t size){std::copy_n(data,size,expected.data()+address);cache.write(address,data,size,send);assert(actual==expected);};
    apply(base,input.data(),64);assert(calls==1);apply(base,input.data(),64);assert(calls==1&&cache.skippedBytes==64);
    input[17]=99;apply(base,input.data(),64);assert(calls==2&&cache.skippedBytes==112);
    input[1]=31;input[63]=75;apply(base,input.data(),64);assert(calls==4);
    const uint8_t partial[]={1,2,3};apply(base+17,partial,3);unsigned before=calls;apply(base,input.data(),64);assert(calls==before+1);
    std::array<uint8_t,16> overlap{};apply(base-8,overlap.data(),16);before=calls;apply(base,input.data(),64);assert(calls==before+1);
    apply(base+pages*page-8,overlap.data(),16);
    std::mt19937 random(71291);
    for(unsigned i=0;i<1000;i++){unsigned slot=random()%(pages-4);if(i%3)input[random()%64]=random()%256;apply(base+slot*page,input.data(),64);}
    rr::TexturePageShadow<page,pages,base> failure;failure.write(base,input.data(),64,send);auto changed=input;changed[0]^=255;changed[63]^=255;
    unsigned attempts=0;bool threw=false;
    try{failure.write(base,changed.data(),64,[&](const uint8_t* data,std::size_t size,uint32_t address){if(++attempts==2)return false;return send(data,size,address);});}catch(const std::runtime_error&){threw=true;}
    assert(threw&&attempts==2&&failure.failures==1);before=calls;failure.write(base,changed.data(),64,send);assert(calls==before+1);
    assert(cache.inputBytes==cache.skippedBytes+cache.writtenBytes);
    std::cout<<"JAVA_TEXTURE_SHADOW_UNIT_PASS random_writes=1000 exact_bytes=1 duplicate=1 partial=1 boundaries=1 failed_write_invalidates=1\n";
}
