// SPDX-License-Identifier: MIT
// Exact CPU pixel packing / ordered Device-memory writes for native LCD UI.
#include "../neural_style/pl_frames.hpp"
#include <cstddef>
#include <cstdint>
#include <vector>
extern "C" uint32_t rix_menu_read32(void* memory,unsigned offset) {
    rix_pl::barrier();return *reinterpret_cast<volatile uint32_t*>(static_cast<char*>(memory)+offset);
}
extern "C" void rix_menu_write32(void* memory,unsigned offset,uint32_t value) {
    *reinterpret_cast<volatile uint32_t*>(static_cast<char*>(memory)+offset)=value;rix_pl::barrier();
}
extern "C" int rix_menu_read_native(const void* source,uint32_t* destination,size_t words) {
    if(!source||!destination||words!=800*480||reinterpret_cast<uintptr_t>(source)%32)return -1;
    try {rix_pl::read_words(source,destination,words);rix_pl::barrier();return 0;}
    catch(...) {return -2;}
}
extern "C" int rix_menu_write565(void* destination,const uint8_t* source,size_t bytes) {
    if(!destination||!source||bytes!=800*480*2||reinterpret_cast<uintptr_t>(destination)%32)return -1;
    try {
        std::vector<uint32_t> pixels(800*480);
        for(size_t i=0;i<pixels.size();++i) {
            const unsigned v=source[i*2]|unsigned(source[i*2+1])<<8;
            const unsigned r=v>>11,g=(v>>5)&63,b=v&31;
            pixels[i]=0xff000000u|((r<<3)|(r>>2))<<16|((g<<2)|(g>>4))<<8|((b<<3)|(b>>2));
        }
        rix_pl::write_words(destination,pixels.data(),pixels.size());return 0;
    } catch(...) {return -2;}
}
