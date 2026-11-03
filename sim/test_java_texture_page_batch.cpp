// SPDX-License-Identifier: GPL-3.0-or-later
#include "../ports/java_texture_page_batch.hpp"
#include <cassert>
#include <iostream>
#include <vector>
struct Page { uint32_t addr;uint8_t data[2048]; };
void check(const std::vector<uint32_t>& addresses,std::size_t expectedCalls) {
    std::vector<Page> pages;
    for(auto address:addresses){Page page;page.addr=address;for(std::size_t i=0;i<sizeof(page.data);i++)page.data[i]=(pages.size()*47+i)%251;pages.push_back(page);}
    std::size_t at=0,seen=0,calls=0;
    rr::uploadConsecutiveTexturePages<2048,65536>([&](){return at<pages.size()?&pages[at++]:nullptr;},
        [&](const uint8_t* bytes,std::size_t length,uint32_t address){
            ++calls;assert(length>0&&length<=65536&&length%2048==0);
            for(std::size_t offset=0;offset<length;offset+=2048){assert(seen<pages.size());const Page& page=pages[seen++];assert(uint64_t(address)+offset==page.addr);assert(std::equal(std::begin(page.data),std::end(page.data),bytes+offset));}
            return true;});
    assert(seen==pages.size()&&calls==expectedCalls);
}
int main() {
    check({},0);check({0},1);std::vector<uint32_t> consecutive;for(unsigned i=0;i<70;i++)consecutive.push_back(i*2048);check(consecutive,3);
    check({0,2048,8192,10240},2);check({8192,6144,4096},3);check({0,2048,2048,4096},2);check({0xfffff800U,0,2048},2);
    std::vector<Page> pages(70);for(unsigned i=0;i<70;i++)pages[i].addr=i*2048;std::size_t at=0,calls=0;bool failed=false;
    try{rr::uploadConsecutiveTexturePages<2048,65536>([&](){return at<pages.size()?&pages[at++]:nullptr;},[&](const uint8_t*,std::size_t,uint32_t){return ++calls!=2;});}catch(const std::runtime_error&){failed=true;}
    assert(failed&&calls==2);
    std::cout<<"JAVA_TEXTURE_BATCH_UNIT_PASS cases=8 byte_exact=1 order=1 failure_stops=1\n";
}
