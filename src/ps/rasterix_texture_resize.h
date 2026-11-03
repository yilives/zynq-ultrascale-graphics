/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef RASTERIX_TEXTURE_RESIZE_H
#define RASTERIX_TEXTURE_RESIZE_H
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
static unsigned rix_texture_dimension(unsigned original,unsigned largest,unsigned limit)
{
    double desired=(double)original*(largest>limit?(double)limit/largest:1.0);
    unsigned lower=1;
    while(lower*2<=limit && lower*2<=desired) lower*=2;
    return lower*2<=limit && desired-lower>lower*2-desired?lower*2:lower;
}
/* Area prefiltering suppresses aliasing before the 128-pixel hardware limit.
 * Alpha-weighted RGB avoids dark fringes around transparent sprites. Integer
 * footprint weights also cover odd source dimensions exactly. The legacy
 * sampler remains selectable for controlled comparisons.
 */
static int rix_resize_texture(unsigned char **data,unsigned short *width,
    unsigned short *height,unsigned channels,unsigned limit)
{
    unsigned x,y,k,w=*width,h=*height,largest=w>h?w:h;
    unsigned nw,nh;unsigned char *resized;
    const char *filter=getenv("RIX_TEXTURE_PREFILTER");
    if(!*data||!w||!h||(channels!=3&&channels!=4)||!limit||(limit&(limit-1))) return -1;
    nw=rix_texture_dimension(w,largest,limit);nh=rix_texture_dimension(h,largest,limit);
    if(nw==w&&nh==h) return 0;
    resized=(unsigned char*)malloc((size_t)nw*nh*channels);
    if(!resized) return -1;
    for(y=0;y<nh;y++) for(x=0;x<nw;x++) {
        size_t dest=((size_t)y*nw+x)*channels;
        if(filter&&filter[0]=='0') {
            for(k=0;k<channels;k++) resized[dest+k]=(*data)[((size_t)(y*h/nh)*w+x*w/nw)*channels+k];
        } else {
            unsigned sx,sy;
            uint64_t sums[3]={0,0,0},alpha=0,weight=0;
            for(sy=y*h/nh;sy<((y+1)*h+nh-1)/nh;sy++) {
                unsigned top=y*h>sy*nh?y*h:sy*nh;
                unsigned bottom=(y+1)*h<(sy+1)*nh?(y+1)*h:(sy+1)*nh;
                for(sx=x*w/nw;sx<((x+1)*w+nw-1)/nw;sx++) {
                    unsigned left=x*w>sx*nw?x*w:sx*nw;
                    unsigned right=(x+1)*w<(sx+1)*nw?(x+1)*w:(sx+1)*nw;
                    uint64_t area=(uint64_t)(right-left)*(bottom-top);
                    const unsigned char *p=*data+((size_t)sy*w+sx)*channels;
                    uint64_t a=channels==4?p[3]:1;
                    weight+=area;alpha+=area*a;
                    for(k=0;k<3;k++) sums[k]+=area*a*p[k];
                }
            }
            for(k=0;k<3;k++) resized[dest+k]=alpha?(unsigned char)((sums[k]+alpha/2)/alpha):0;
            if(channels==4) resized[dest+3]=(unsigned char)((alpha+weight/2)/weight);
        }
    }
    free(*data);*data=resized;*width=(unsigned short)nw;*height=(unsigned short)nh;
    return 1;
}
#endif
