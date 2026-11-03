// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <vector>
namespace rr {
// Only for the exclusively owned, GPU-read-only texture allocation range.
template<std::size_t PageSize,std::size_t Pages,uint32_t Base>
class TexturePageShadow {
    std::unique_ptr<uint8_t[]> bytes{new uint8_t[PageSize*Pages]};
    std::vector<uint8_t> valid=std::vector<uint8_t>(Pages,0);
public:
    uint64_t inputBytes=0,skippedBytes=0,writtenBytes=0,runs=0,failures=0;
    void invalidate(uint32_t address,std::size_t size) {
        const uint64_t begin=std::max<uint64_t>(address,Base),end=std::min<uint64_t>(uint64_t(address)+size,uint64_t(Base)+PageSize*Pages);
        if(begin>=end)return;
        for(std::size_t page=(begin-Base)/PageSize;page<(end-Base+PageSize-1)/PageSize;page++)valid[page]=0;
    }
    template<typename Send>
    void write(uint32_t address,const uint8_t* source,std::size_t size,Send send) {
        inputBytes+=size;
        const bool eligible=size&&address>=Base&&(address-Base)%PageSize==0&&size%PageSize==0&&uint64_t(address)+size<=uint64_t(Base)+PageSize*Pages;
        try {
            if(!eligible) {
                invalidate(address,size);
                if(!send(source,size,address))throw std::runtime_error("Texture shadow fallback write failed");
                writtenBytes+=size;++runs;return;
            }
            const std::size_t first=(address-Base)/PageSize,count=size/PageSize;
            auto same=[&](std::size_t page){return valid[first+page]&&std::memcmp(bytes.get()+(first+page)*PageSize,source+page*PageSize,PageSize)==0;};
            for(std::size_t page=0;page<count;) {
                if(same(page)){skippedBytes+=PageSize;++page;continue;}
                const std::size_t start=page++;
                while(page<count&&!same(page))++page;
                const std::size_t length=(page-start)*PageSize;
                if(!send(source+start*PageSize,length,address+start*PageSize))throw std::runtime_error("Texture shadow write failed");
                std::memcpy(bytes.get()+(first+start)*PageSize,source+start*PageSize,length);
                std::fill(valid.begin()+first+start,valid.begin()+first+page,1);
                writtenBytes+=length;++runs;
            }
        } catch(...) {std::fill(valid.begin(),valid.end(),0);++failures;throw;}
    }
};
}
