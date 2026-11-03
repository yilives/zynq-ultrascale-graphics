// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
namespace rr {
template<std::size_t PageSize,std::size_t Capacity,typename Next,typename Upload>
void uploadConsecutiveTexturePages(Next next,Upload upload) {
    static_assert(PageSize>0&&PageSize<=Capacity&&Capacity%PageSize==0,"Whole pages only");
    std::array<uint8_t,Capacity> data;uint32_t address=0;std::size_t used=0;
    auto flush=[&](){if(used&&!upload(data.data(),used,address))throw std::runtime_error("Texture upload failed; refuse to clear pending data");used=0;};
    while(const auto* page=next()) {
        if(used&&(uint64_t(address)+used!=page->addr||used+PageSize>Capacity))flush();
        if(!used)address=page->addr;
        std::copy_n(page->data,PageSize,data.data()+used);used+=PageSize;
    }
    flush();
}
}
