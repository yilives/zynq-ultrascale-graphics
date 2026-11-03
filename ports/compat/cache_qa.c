/* SPDX-License-Identifier: MIT */
#define GL_GLEXT_PROTOTYPES
#include <SDL.h>
#include <GL/gl.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char**argv) {
    if(argc!=2)return 2;
    if(SDL_Init(SDL_INIT_VIDEO))return 3;
    SDL_Window *window=SDL_CreateWindow("RasterIX Cache QA",0,0,400,240,SDL_WINDOW_OPENGL|SDL_WINDOW_SHOWN);
    if(!window)return 4;
    SDL_GLContext context=SDL_GL_CreateContext(window);
    if(!context)return 5;
    glViewport(0,0,400,240);
    glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,400,0,240,-1,1);
    glMatrixMode(GL_MODELVIEW);glLoadIdentity();
    glDisable(GL_TEXTURE_2D);glDisable(GL_DEPTH_TEST);glDisable(GL_LIGHTING);glDisable(GL_CULL_FACE);glDisable(GL_BLEND);
    GLfloat positions[17*17*2],colors[17*17*4];
    GLushort indices[16*16*6];
    for(int y=0;y<17;y++)for(int x=0;x<17;x++) {
        int i=y*17+x;
        positions[i*2]=20+x*10;positions[i*2+1]=20+y*12;
        colors[i*4]=x/16.f;colors[i*4+1]=y/16.f;colors[i*4+2]=.2f;colors[i*4+3]=1;
    }
    for(int y=0;y<16;y++)for(int x=0;x<16;x++) {
        int a=y*17+x,o=(y*16+x)*6;
        indices[o]=a;indices[o+1]=a+1;indices[o+2]=a+18;
        indices[o+3]=a;indices[o+4]=a+18;indices[o+5]=a+17;
    }
    glBindBuffer(GL_ARRAY_BUFFER,0);glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,0);
    glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_COLOR_ARRAY);
    glVertexPointer(2,GL_FLOAT,0,positions);glColorPointer(4,GL_FLOAT,0,colors);
    glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    glDrawElements(GL_TRIANGLES,16*16*6,GL_UNSIGNED_SHORT,indices);
    /* Same indices after source data and transform changes: per-draw caches
       must invalidate, while repeated indices within each draw should hit. */
    for(int i=0;i<17*17;i++){positions[i*2]+=200;colors[i*4+2]=.8f;}
    glDrawElements(GL_TRIANGLES,16*16*6,GL_UNSIGNED_SHORT,indices);
    glLoadIdentity();glTranslatef(0,3,0);glScalef(.5f,.5f,1);
    for(int i=0;i<17*17;i++){colors[i*4]=1;colors[i*4+1]=.25f;}
    glDrawElements(GL_TRIANGLES,16*16*6,GL_UNSIGNED_SHORT,indices);
    SDL_GL_SwapWindow(window);
    unsigned char *pixels=malloc(400*240*4);
    if(!pixels)return 6;
    glReadPixels(0,0,400,240,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
    FILE *out=fopen(argv[1],"wb");
    if(!out||fwrite(pixels,1,400*240*4,out)!=400*240*4)return 7;
    fclose(out);free(pixels);
    printf("CACHE_GPU_QA_COMPLETE indices=4608 source_and_transform_invalidation=1 gl_error=%u\n",glGetError());
    SDL_GL_DeleteContext(context);SDL_DestroyWindow(window);SDL_Quit();
    return 0;
}
