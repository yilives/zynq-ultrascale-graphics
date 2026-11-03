// SPDX-License-Identifier: MIT
// EASU / RCAS derived from AMD FidelityFX FSR1 (Copyright (c) 2021 AMD).
// Integer Q6.18 arithmetic, with the original GPU reciprocal seed constants.
// This is a numerical hardware approximation; compare against the FP32 golden.
#pragma once
#include <cstdint>
#ifdef __SYNTHESIS__
#include <ap_int.h>
using FQ = ap_int<24>;
using FW = ap_int<56>;
using FU = ap_uint<56>;
using FL = ap_int<33>;
using FP = ap_int<48>;
#else
using FQ = int32_t;
using FW = int64_t;
using FU = uint64_t;
using FL = int64_t;
using FP = int64_t;
#endif
static const int FS = 1 << 18;
struct FColor { FQ r, g, b; bool fault; FL luma; };
struct FDirection { FQ x, y, length; };
static FQ fminq(FQ a,FQ b) { return a<b?a:b; }
static FQ fmaxq(FQ a,FQ b) { return a>b?a:b; }
static FQ fabsq(FQ a) { return a<0?FQ(-a):a; }
static FQ fmulq(FQ a,FQ b) {
#pragma HLS INLINE
    FW product=FW(a)*FW(b);
    return FQ(product >> 18);
}
static FQ fdivq(FQ a,FQ b);
static uint32_t float_bits_q(FU raw,unsigned fractional) {
#pragma HLS INLINE
    if(raw==0)return 0;
    unsigned msb=0;
    for(unsigned i=0;i<48;++i) {
#pragma HLS UNROLL
        if((raw>>i)&1)msb=i;
    }
    FU mantissa;
    if(msb<=23)mantissa=raw<<(23-msb);
    else {
        unsigned shift=msb-23;
        mantissa=raw>>shift;
        bool guard=(raw>>(shift-1))&1;
        bool sticky=(raw&((FU(1)<<(shift-1))-1))!=0;
        if(guard&&(sticky||bool(mantissa&1)))++mantissa;
        if(mantissa==(FU(1)<<24)) {mantissa>>=1;++msb;}
    }
    return ((msb+127-fractional)<<23)|(uint32_t(mantissa)&0x7fffffu);
}
static FQ seed_product(FQ numerator,uint32_t seed) {
#pragma HLS INLINE
    uint32_t mantissa=(seed&0x7fffffu)|0x800000u;
    int exponent=int((seed>>23)&255)-127;
    FP product=FP(numerator)*FP(mantissa);
    // Q18 inputs have reciprocal exponents <=18. The normalized EASU
    // direction has inverse-sqrt exponent <=7. No left shift is possible.
    return FQ(product>>(23-exponent));
}
static uint32_t reciprocal_seed18(FQ denominator,uint32_t magic) {
#pragma HLS INLINE
    uint32_t raw=uint32_t(denominator);
    unsigned msb=0;
    for(unsigned i=0;i<24;++i) {
#pragma HLS UNROLL
        if((raw>>i)&1)msb=i;
    }
    // Positive Q6.18 fits 23 value bits, so no FP32 mantissa rounding.
    uint32_t bits=((msb+109)<<23)|((raw<<(23-msb))&0x7fffffu);
    return magic-bits;
}
static FQ reciprocal_product(FQ numerator,FQ denominator,uint32_t magic=0x7ef07ebbu) {
#pragma HLS INLINE
    if(denominator<=0)return 0;
    return seed_product(numerator,reciprocal_seed18(denominator,magic));
}
static FQ fdivq(FQ a,FQ b) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
    if(b==0)return 0;
    bool negative=(a<0)!=(b<0);
    FQ aa=fabsq(a),bb=fabsq(b);
    uint32_t seed=reciprocal_seed18(bb,0x7ef19fffu);
    FQ q=seed_product(aa,seed);
    // Two quotient refinements avoid both a large divider and an inverse
    // overflowing at tiny RCAS denominators. Ratios stay bounded by design.
    q+=seed_product(aa-fmulq(q,bb),seed);
    q+=seed_product(aa-fmulq(q,bb),seed);
    return negative?FQ(-q):q;
}
static FQ ratio_length(FL numerator,FL denominator) {
#pragma HLS INLINE
    if(denominator==0)return 0;
    // Ratio is bounded before narrowing to Q6.18, including very small gradients.
    uint32_t seed=0x7ef07ebbu-float_bits_q(FU(denominator),30);
    uint32_t mantissa=(seed&0x7fffffu)|0x800000u;
    int exponent=int((seed>>23)&255)-127;
    FU product=FU(numerator)*mantissa;
    FU value=product>>(35-exponent);
    return value>=FS?FQ(FS):FQ(value);
}
static void set_direction(FDirection& state,unsigned weight,FL a,FL b,FL c,FL d,FL e) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
    FL dx=d-b,dy=e-a;
    FL dc=d-c,cb=c-b,ec=e-c,ca=c-a;
    dc=dc<0?FL(-dc):dc;cb=cb<0?FL(-cb):cb;
    ec=ec<0?FL(-ec):ec;ca=ca<0?FL(-ca):ca;
    FQ rx=ratio_length(dx<0?FL(-dx):dx,dc>cb?dc:cb);
    FQ ry=ratio_length(dy<0?FL(-dy):dy,ec>ca?ec:ca);
    state.x+=FQ((FW(dx)*weight)>>16);
    state.y+=FQ((FW(dy)*weight)>>16);
    state.length+=FQ((FW(fmulq(rx,rx)+fmulq(ry,ry))*weight)>>4);
}
// Preserve FP32 luma rounding before gradient ratios: exact color cancellations
// can leave a one-ULP gradient in the official kernel. Q18 luma loses it, and
// EASU's normalized edge length then changes even though the direction is tiny.
#include "fsr1_luma_tables.hpp"
static uint32_t round_luma_float(uint32_t raw) {
#pragma HLS INLINE
    unsigned msb=0;
    for(unsigned i=23;i<32;++i) {
#pragma HLS UNROLL
        if((raw>>i)&1)msb=i;
    }
    if(msb<=23)return uint32_t(raw);
    unsigned shift=msb-23;
    uint32_t q=raw>>shift;
    bool guard=(raw>>(shift-1))&1;
    bool sticky=(raw&((uint32_t(1)<<(shift-1))-1))!=0;
    if(guard&&(sticky||bool(q&1)))++q;
    return uint32_t(q<<shift);
}
static FL luma_of_raw(uint16_t p) {
#pragma HLS INLINE
    unsigned r=p>>11,g=(p>>5)&63,b=p&31;
    uint32_t rg=round_luma_float((FSR_LUMA_R[r]>>1)+FSR_LUMA_G[g]);
    return FL(round_luma_float((FSR_LUMA_R[b]>>1)+rg));
}
static FL lumaq(FColor c) {return c.luma;}
static FColor load_fixed(int x,int y);
static FColor decode_fixed(uint16_t p);
static void fixed_tap(FColor& sum,FQ& weight,int px,int py,FQ dx,FQ dy,FQ lx,FQ ly,FQ lob,FQ clip,FColor c) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
    FQ vx=FQ((FW(dx)*px+FW(dy)*py)>>2);
    FQ vy=FQ((-FW(dy)*px+FW(dx)*py)>>2);
    vx=fmulq(vx,lx);vy=fmulq(vy,ly);
    FQ d2=fminq(fmulq(vx,vx)+fmulq(vy,vy),clip);
    FQ wb=fmulq(FQ(104858),d2)-FS; // round(0.4 * 2^18)
    FQ wa=fmulq(lob,d2)-FS;
    wb=fmulq(wb,wb);wa=fmulq(wa,wa);
    wb=FQ((FW(wb)*25)>>4)-FQ(9*FS/16);
    FQ w=fmulq(wb,wa);
    sum.r+=fmulq(c.r,w);sum.g+=fmulq(c.g,w);sum.b+=fmulq(c.b,w);weight+=w;
}
static FColor fixed_easu(int ox,int oy) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=16
#pragma HLS ALLOCATION function instances=fixed_tap limit=1
#pragma HLS ALLOCATION function instances=set_direction limit=1
#pragma HLS ALLOCATION function instances=fdivq limit=1
#pragma HLS ALLOCATION function instances=decode_fixed limit=1
    int bx=ox==0?-1:(ox-1)/2,by=oy==0?-1:(oy-1)/2;
    int px=(ox&1)?1:3,py=(oy&1)?1:3;
    FColor b=load_fixed(bx,by-1),c=load_fixed(bx+1,by-1);
    FColor e=load_fixed(bx-1,by),f=load_fixed(bx,by),g=load_fixed(bx+1,by),h=load_fixed(bx+2,by);
    FColor i=load_fixed(bx-1,by+1),j=load_fixed(bx,by+1),k=load_fixed(bx+1,by+1),l=load_fixed(bx+2,by+1);
    FColor n=load_fixed(bx,by+2),o=load_fixed(bx+1,by+2);
    FDirection state={0,0,0};
    set_direction(state,(4-px)*(4-py),lumaq(b),lumaq(e),lumaq(f),lumaq(g),lumaq(j));
    set_direction(state,px*(4-py),lumaq(c),lumaq(f),lumaq(g),lumaq(h),lumaq(k));
    set_direction(state,(4-px)*py,lumaq(f),lumaq(i),lumaq(j),lumaq(k),lumaq(n));
    set_direction(state,px*py,lumaq(g),lumaq(j),lumaq(k),lumaq(l),lumaq(o));
    FU radius=FU(FW(state.x)*state.x+FW(state.y)*state.y);
    FQ dx,dy;
    // Official FSR replaces only dir.x in the near-zero branch; dir.y survives.
    if(radius<FU(FW(FS)*FS/32768)) {dx=FS;dy=state.y;}
    else {
        uint32_t seed=0x5f347d74u-(float_bits_q(radius,36)>>1);
        dx=seed_product(state.x,seed);dy=seed_product(state.y,seed);
    }
    FQ len=fmulq(state.length/2,state.length/2);
    FQ stretch=reciprocal_product(fmulq(dx,dx)+fmulq(dy,dy),fmaxq(fabsq(dx),fabsq(dy)));
    FQ lx=FS+fmulq(stretch-FS,len),ly=FS-len/2;
    FQ lob=FS/2-fmulq(FQ(76022),len); // round(0.29 * 2^18)
    FQ clip=reciprocal_product(FS,lob);
    FColor sum={0,0,0};FQ weights=0;
    fixed_tap(sum,weights, 0-px,-4-py,dx,dy,lx,ly,lob,clip,b);
    fixed_tap(sum,weights, 4-px,-4-py,dx,dy,lx,ly,lob,clip,c);
    fixed_tap(sum,weights,-4-px, 4-py,dx,dy,lx,ly,lob,clip,i);
    fixed_tap(sum,weights, 0-px, 4-py,dx,dy,lx,ly,lob,clip,j);
    fixed_tap(sum,weights, 0-px, 0-py,dx,dy,lx,ly,lob,clip,f);
    fixed_tap(sum,weights,-4-px, 0-py,dx,dy,lx,ly,lob,clip,e);
    fixed_tap(sum,weights, 4-px, 4-py,dx,dy,lx,ly,lob,clip,k);
    fixed_tap(sum,weights, 8-px, 4-py,dx,dy,lx,ly,lob,clip,l);
    fixed_tap(sum,weights, 8-px, 0-py,dx,dy,lx,ly,lob,clip,h);
    fixed_tap(sum,weights, 4-px, 0-py,dx,dy,lx,ly,lob,clip,g);
    fixed_tap(sum,weights, 4-px, 8-py,dx,dy,lx,ly,lob,clip,o);
    fixed_tap(sum,weights, 0-px, 8-py,dx,dy,lx,ly,lob,clip,n);
    FColor lo={fminq(fminq(f.r,g.r),fminq(j.r,k.r)),fminq(fminq(f.g,g.g),fminq(j.g,k.g)),fminq(fminq(f.b,g.b),fminq(j.b,k.b))};
    FColor hi={fmaxq(fmaxq(f.r,g.r),fmaxq(j.r,k.r)),fmaxq(fmaxq(f.g,g.g),fmaxq(j.g,k.g)),fmaxq(fmaxq(f.b,g.b),fmaxq(j.b,k.b))};
    return {fminq(hi.r,fmaxq(lo.r,fdivq(sum.r,weights))),fminq(hi.g,fmaxq(lo.g,fdivq(sum.g,weights))),fminq(hi.b,fmaxq(lo.b,fdivq(sum.b,weights))),weights<=0||lob<=0};
}
static FQ channel_lobe(FQ b,FQ d,FQ e,FQ f,FQ h) {
#pragma HLS INLINE
    FQ lo=fminq(fminq(b,d),fminq(f,h)),hi=fmaxq(fmaxq(b,d),fmaxq(f,h));
    // Match FP32 fmax's treatment of NaN from the 0/0 endpoint limiters.
    if(hi==0)return fdivq(FS-fmaxq(hi,e),4*lo-4*FS);
    if(lo==FS)return -fdivq(fminq(lo,e),4*hi);
    return fmaxq(-fdivq(fminq(lo,e),4*hi),fdivq(FS-fmaxq(hi,e),4*lo-4*FS));
}
static FColor load_easu_fixed(int x,int y);
static FColor fixed_rcas(int x,int y) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=8
#pragma HLS ALLOCATION function instances=fdivq limit=1
    FColor b=load_easu_fixed(x,y-1),d=load_easu_fixed(x-1,y),e=load_easu_fixed(x,y),f=load_easu_fixed(x+1,y),h=load_easu_fixed(x,y+1);
    FQ lr=channel_lobe(b.r,d.r,e.r,f.r,h.r),lg=channel_lobe(b.g,d.g,e.g,f.g,h.g),lb=channel_lobe(b.b,d.b,e.b,f.b,h.b);
    FQ lobe=fmulq(fmaxq(FQ(-3*FS/16),fminq(FQ(0),fmaxq(fmaxq(lr,lg),lb))),FQ(228210));
    FQ denominator=FS+4*lobe;
    FQ inverse=reciprocal_product(FS,denominator,0x7ef19fffu);
    inverse=fmulq(inverse,2*FS-fmulq(inverse,denominator));
    return {fmulq(fmulq(lobe,b.r)+fmulq(lobe,d.r)+fmulq(lobe,h.r)+fmulq(lobe,f.r)+e.r,inverse),
            fmulq(fmulq(lobe,b.g)+fmulq(lobe,d.g)+fmulq(lobe,h.g)+fmulq(lobe,f.g)+e.g,inverse),
            fmulq(fmulq(lobe,b.b)+fmulq(lobe,d.b)+fmulq(lobe,h.b)+fmulq(lobe,f.b)+e.b,inverse),
            b.fault||d.fault||e.fault||f.fault||h.fault||denominator<=0};
}
