// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#if defined(__ARM_FEATURE_CRC32)
#include <arm_acle.h>
#endif
namespace rr::java_position {
inline bool enabled(){static bool value=[](){const char*p=std::getenv("RIX_JAVA_POSITION_CACHE");return p&&std::strcmp(p,"1")==0;}();return value;}
struct Statistics{uint64_t eligible=0,hits=0,misses=0,resets=0;};
inline Statistics&statistics(){static Statistics s;return s;}
// Only the exactly repeated position is cached. UV, color, normal, lighting,
// clipping, perspective division and viewport processing remain independent.
// reset() is mandatory at each DrawNewElement, before matrix/state reuse.
template<class Vector>class Cache{
    struct Entry{std::array<uint32_t,4>key{};Vector value{};uint32_t epoch=0;};
    std::array<Entry,128>m_entries{};uint32_t m_epoch=1;
    static std::array<uint32_t,4>key(const Vector&v){std::array<uint32_t,4>k;for(unsigned i=0;i<4;++i){float f=v[i];std::memcpy(&k[i],&f,4);}return k;}
    static std::size_t index(const std::array<uint32_t,4>&k){
#if defined(__ARM_FEATURE_CRC32)
        uint32_t h=__crc32cd(0,uint64_t(k[0])|(uint64_t(k[1])<<32));h=__crc32cd(h,uint64_t(k[2])|(uint64_t(k[3])<<32));
#else
        uint32_t h=0x9e3779b9;for(auto w:k){h^=w+0x9e3779b9+(h<<6)+(h>>2);}h^=h>>16;h*=0x7feb352d;h^=h>>15;
#endif
        return h&127;
    }
public:
    void reset(){if(++m_epoch==0){for(auto&e:m_entries)e.epoch=0;m_epoch=1;}if(enabled())++statistics().resets;}
    bool get(const Vector&v,Vector&out){const auto k=key(v);auto&e=m_entries[index(k)];++statistics().eligible;
        if(e.epoch==m_epoch&&e.key==k){out=e.value;++statistics().hits;return true;}++statistics().misses;return false;}
    void put(const Vector&v,const Vector&out){const auto k=key(v);auto&e=m_entries[index(k)];e.key=k;e.value=out;e.epoch=m_epoch;}
};
inline void finish(){const char*p=std::getenv("RIX_JAVA_POSITION_STATS");if(!p)return;FILE*f=std::fopen(p,"w");if(!f)throw std::runtime_error("Position statistics open");const auto&s=statistics();
    std::fprintf(f,"{\"phase\":\"after_renderer_destroy\",\"enabled\":%s,\"eligible\":%llu,\"hits\":%llu,\"misses\":%llu,\"resets\":%llu,\"slots\":128,\"exact_position_bits\":true}\n",enabled()?"true":"false",(unsigned long long)s.eligible,(unsigned long long)s.hits,(unsigned long long)s.misses,(unsigned long long)s.resets);if(std::fclose(f))throw std::runtime_error("Position statistics close");}
}
