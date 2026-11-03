/* SPDX-License-Identifier: MIT */
#define GL_GLEXT_PROTOTYPES
#include <SDL.h>
#include <GL/gl.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>

static int test_clip_planes(SDL_Window *window) {
    puts("CLIP_TEST_BEGIN");
    GLint planes=0;
    glGetIntegerv(GL_MAX_CLIP_PLANES,&planes);
    if(planes!=6) return 0;
    const GLdouble equations[6][4]={{1,0,0,-80},{-1,0,0,320},{0,1,0,-40},{0,-1,0,200},{1,1,0,-170},{-1,-1,0,430}};
    glDisableClientState(GL_VERTEX_ARRAY);
    glDisable(GL_CULL_FACE);glDisable(GL_DEPTH_TEST);glDisable(GL_LIGHTING);glDisable(GL_TEXTURE_2D);
    for(int i=0;i<6;i++) {
        GLdouble actual[4]={0};
        glClipPlane(GL_CLIP_PLANE0+i,equations[i]);
        glGetClipPlane(GL_CLIP_PLANE0+i,actual);
        for(int j=0;j<4;j++)if(fabs(actual[j]-equations[i][j])>0.00001)return 0;
        glEnable(GL_CLIP_PLANE0+i);
        if(!glIsEnabled(GL_CLIP_PLANE0+i))return 0;
    }
    for(int frame=0;frame<3;frame++) {
        glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        glColor3f(1,0,0);
        glBegin(GL_QUADS);
        glVertex2f(0,0);glVertex2f(400,0);glVertex2f(400,240);glVertex2f(0,240);
        glEnd();SDL_GL_SwapWindow(window);printf("CLIP_TEST_SWAP %d\n",frame);
    }
    SDL_Delay(250);
    unsigned char *pixels=malloc(400*240*4);
    if(!pixels)return 0;
    puts("CLIP_TEST_READ_BEGIN");
    glReadPixels(0,0,400,240,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
    puts("CLIP_TEST_READ_END");
    unsigned checked=0,failed=0;
    for(int y=3;y<237;y+=3)for(int x=3;x<397;x+=3) {
        int inside=1,boundary=0;
        for(int p=0;p<6;p++) {
            double d=equations[p][0]*x+equations[p][1]*y+equations[p][3];
            if(fabs(d)<3)boundary=1;
            if(d<0)inside=0;
        }
        if(boundary)continue;
        unsigned char *pixel=pixels+((y*400+x)*4);
        if((inside?pixel[0]<248:pixel[0]>8)||pixel[1]>4||pixel[2]>8)failed++;
        checked++;
    }
    free(pixels);
    for(int i=0;i<6;i++) {
        glDisable(GL_CLIP_PLANE0+i);
        if(glIsEnabled(GL_CLIP_PLANE0+i))return 0;
    }
    printf("RIX_GLX_SIX_CLIP_PLANES pixels=%u failures=%u\n",checked,failed);
    return failed==0;
}

int main(void) {
    setvbuf(stdout,NULL,_IONBF,0);
    SDL_Window *window = NULL;
    SDL_GLContext context = NULL;
    int result = 1;
    if (SDL_Init(SDL_INIT_VIDEO) != 0) goto fail;
    SDL_GL_SetAttribute(SDL_GL_RED_SIZE, 5);
    SDL_GL_SetAttribute(SDL_GL_GREEN_SIZE, 6);
    SDL_GL_SetAttribute(SDL_GL_BLUE_SIZE, 5);
    SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 16);
    SDL_GL_SetAttribute(SDL_GL_STENCIL_SIZE, 0);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    window = SDL_CreateWindow("RasterIX GLX probe", 0, 0, 400, 240, SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN);
    if (!window) goto fail;
    context = SDL_GL_CreateContext(window);
    if (!context) goto fail;
    printf("GL_VENDOR=%s\nGL_RENDERER=%s\nGL_VERSION=%s\n", glGetString(GL_VENDOR), glGetString(GL_RENDERER), glGetString(GL_VERSION));
    if (strcmp((const char *)glGetString(GL_RENDERER), "RasterIX") != 0) goto fail;
    glViewport(0, 0, 400, 240);
    glMatrixMode(GL_PROJECTION); glLoadIdentity(); glOrtho(0, 400, 0, 240, -1, 1);
    glMatrixMode(GL_MODELVIEW); glLoadIdentity();
    /* Repeated unbinds must not leak all 1024 texture names. */
    GLuint texture = 0, buffers[2] = {0, 0};
    for (int i = 0; i < 4096; ++i) glBindTexture(GL_TEXTURE_2D, 0);
    glGenTextures(1, &texture);
    if (!texture) goto fail;
    glDeleteTextures(1, &texture);
    const GLfloat vertices[] = {20, 20, 380, 20, 200, 220};
    const GLushort indices[] = {0, 1, 2};
    glGenBuffers(2, buffers);
    glBindBuffer(GL_ARRAY_BUFFER, buffers[0]);
    glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STATIC_DRAW);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, buffers[1]);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, sizeof(indices), indices, GL_STATIC_DRAW);
    GLint vertex_bytes = 0, index_bytes = 0;
    glGetBufferParameteriv(GL_ARRAY_BUFFER, GL_BUFFER_SIZE, &vertex_bytes);
    glGetBufferParameteriv(GL_ELEMENT_ARRAY_BUFFER, GL_BUFFER_SIZE, &index_bytes);
    if (vertex_bytes != sizeof(vertices) || index_bytes != sizeof(indices)) goto fail;
    glEnableClientState(GL_VERTEX_ARRAY);
    glVertexPointer(2, GL_FLOAT, 0, 0);
    for (int i = 0; i < 15; ++i) {
        glClearColor(0, 0, 0.25f, 1);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        glDisable(GL_TEXTURE_2D);
        glColor3f(1, 0, 0);
        glDrawElements(GL_TRIANGLES, 3, GL_UNSIGNED_SHORT, 0);
        SDL_GL_SwapWindow(window);
        SDL_PumpEvents();
        SDL_Delay(50);
    }
    SDL_Delay(200);
    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);
    glDeleteBuffers(2, buffers);
    if (!test_clip_planes(window)) goto fail;
    puts("RIX_GLX_PROBE_VBO_EBO_AND_TEXTURE_REBIND_PASS");
    puts("RIX_GLX_PROBE_DRAW_PASS");
    result = 0;
fail:
    if (result) fprintf(stderr, "RIX_GLX_PROBE_FAIL: %s\n", SDL_GetError());
    if (context) SDL_GL_DeleteContext(context);
    if (window) SDL_DestroyWindow(window);
    SDL_Quit();
    return result;
}
