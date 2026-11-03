/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "../src/ps/rasterix_texture_resize.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    const unsigned short dimensions[][2]={{256,255},{129,129},{128,128},{40,17},{1,512},{1024,32}};
    unsigned i;
    setenv("RIX_TEXTURE_PREFILTER","0",1);
    for(i=0;i<sizeof(dimensions)/sizeof(dimensions[0]);i++) {
        unsigned short w=dimensions[i][0],h=dimensions[i][1];unsigned ow=w,oh=h,x,y;
        unsigned char *data=malloc((size_t)w*h*4);
        for(y=0;y<h;y++) for(x=0;x<w;x++) {
            size_t n=((size_t)y*w+x)*4;data[n]=x;data[n+1]=y;data[n+2]=0x5a;data[n+3]=0x93;
        }
        assert(rix_resize_texture(&data,&w,&h,4,128)>=0);
        assert(w&&h&&w<=128&&h<=128&&!(w&(w-1))&&!(h&(h-1)));
        for(y=0;y<h;y++) for(x=0;x<w;x++) {
            size_t n=((size_t)y*w+x)*4;
            assert(data[n]==(unsigned char)(x*ow/w)&&data[n+1]==(unsigned char)(y*oh/h));
            assert(data[n+2]==0x5a&&data[n+3]==0x93);
        }
        free(data);
    }
    unsetenv("RIX_TEXTURE_PREFILTER");
    {
        unsigned short w=256,h=256;
        unsigned char *data=malloc((size_t)w*h*4);
        for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++) {
            unsigned char *p=data+((size_t)y*w+x)*4;
            p[0]=x%2?0:255;p[1]=p[2]=0;p[3]=x%2?0:255;
        }
        assert(rix_resize_texture(&data,&w,&h,4,128)==1&&w==128&&h==128);
        for(unsigned i=0;i<(unsigned)w*h;i++)assert(data[i*4]==255&&data[i*4+1]==0&&data[i*4+3]==128);
        free(data);
    }
    for(i=0;i<sizeof(dimensions)/sizeof(dimensions[0]);i++) {
        unsigned short w=dimensions[i][0],h=dimensions[i][1];
        unsigned char *data=malloc((size_t)w*h*3);
        memset(data,73,(size_t)w*h*3);
        assert(rix_resize_texture(&data,&w,&h,3,128)>=0);
        for(unsigned j=0;j<(unsigned)w*h*3;j++)assert(data[j]==73);
        free(data);
    }
    puts("TEXTURE_RESIZE_PASS: legacy bounds, area odd dimensions, uniform RGB, alpha edge color");
    return 0;
}
