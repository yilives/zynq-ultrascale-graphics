// SPDX-License-Identifier: MIT
#pragma once
#include "pl_frames.hpp"
#ifdef __aarch64__
#include <arm_neon.h>
#endif

namespace rix_pl {
namespace mc_snapshot_detail {
// Keep exactly the existing aligned 32-byte Device transaction footprint.
// The loaded vectors stay in registers through RGB565 conversion; no stack
// XRGB buffer, cacheable mapping, speculative prefetch or unaligned load.
inline void copy8(const void*source,uint16_t*dest) {
#ifdef __aarch64__
 uint32x4_t low,high;
 asm volatile("ldp %q0, %q1, [%2]":"=w"(low),"=w"(high):"r"(source):"memory");
 auto pack=[](uint32x4_t p) {
  auto r=vand_u16(vshrn_n_u32(p,8),vdup_n_u16(0xf800));
  auto g=vand_u16(vshrn_n_u32(p,5),vdup_n_u16(0x07e0));
  auto b=vand_u16(vshrn_n_u32(p,3),vdup_n_u16(0x001f));
  return vorr_u16(vorr_u16(r,g),b);
 };
 vst1q_u16(dest,vcombine_u16(pack(low),pack(high)));
#else
 const auto*words=static_cast<const volatile uint32_t*>(source);
 for(unsigned j=0;j<8;j++) {
  auto p=words[j];dest[j]=uint16_t(((p>>8)&0xf800)|((p>>5)&0x7e0)|((p>>3)&31));
 }
#endif
}
}

// Caller must hold an SNP1 lease for the ENTIRE call and verify ownership
// again after it returns. This routine only reads the passed immutable PL
// snapshot. It neither requests/releases a lease nor accesses a live PS slot.
// API matches copy_snapshot so selection can stay inside Snapshot::read.
inline void copy_snapshot_neon(const void*source,std::vector<uint16_t>&in,
                               const bool*rows=nullptr,unsigned workers=4) {
 if(!source||in.size()!=96000||reinterpret_cast<uintptr_t>(source)%32||
    (workers!=1&&workers!=2&&workers!=4))throw std::runtime_error("invalid MC snapshot copy layout");
 auto copy=[&](unsigned lo,unsigned hi) {
  for(unsigned y=lo;y<hi;y++) {
   if(rows&&!rows[y])continue;
   for(unsigned i=y*400;i<(y+1)*400;i+=8)
    mc_snapshot_detail::copy8(static_cast<const char*>(source)+i*4,in.data()+i);
  }
  // Drain this CPU's Device reads before join allows lease release.
  barrier();
 };
 std::array<std::thread,3> threads;
 try {
  for(unsigned i=0;i+1<workers;i++)threads[i]=std::thread(copy,240*i/workers,240*(i+1)/workers);
  copy(240*(workers-1)/workers,240);
 }catch(...) {
  for(auto&t:threads)if(t.joinable())t.join();throw;
 }
 for(auto&t:threads)if(t.joinable())t.join();
}
}
