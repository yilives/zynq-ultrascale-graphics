// SPDX-License-Identifier: MIT
// The small fixed-function subset used by rRootage. No shader or GLU library.
#include <GL/glu.h>
#include <SDL.h>
#include <math.h>
#include <stdlib.h>
void gluPerspective(double fov,double aspect,double nearValue,double farValue){double h=tan(fov*3.141592653589793/360)*nearValue;glFrustum(-h*aspect,h*aspect,-h,h,nearValue,farValue);}
void gluLookAt(double ex,double ey,double ez,double cx,double cy,double cz,double ux,double uy,double uz){
    double fx=cx-ex,fy=cy-ey,fz=cz-ez,n=sqrt(fx*fx+fy*fy+fz*fz);fx/=n;fy/=n;fz/=n;
    double sx=fy*uz-fz*uy,sy=fz*ux-fx*uz,sz=fx*uy-fy*ux;n=sqrt(sx*sx+sy*sy+sz*sz);sx/=n;sy/=n;sz/=n;
    double vx=sy*fz-sz*fy,vy=sz*fx-sx*fz,vz=sx*fy-sy*fx;
    GLfloat matrix[]={sx,vx,-fx,0,sy,vy,-fy,0,sz,vz,-fz,0,0,0,0,1};glMultMatrixf(matrix);glTranslated(-ex,-ey,-ez);
}
int gluBuild2DMipmaps(GLenum target,GLint internal,GLsizei w,GLsizei h,GLenum format,GLenum type,const void* bytes){
    if(format!=GL_RGB||type!=GL_UNSIGNED_BYTE||w<1||h<1)return 1;
    int width=w>128?128:w,height=h>128?128:h;unsigned char* out=malloc((size_t)width*height*3);if(!out)return 1;
    const unsigned char* src=bytes;for(int y=0;y<height;++y)for(int x=0;x<width;++x)for(int c=0;c<3;++c)out[(y*width+x)*3+c]=src[((y*h/height)*w+x*w/width)*3+c];
    glTexImage2D(target,0,internal,width,height,0,format,type,out);free(out);glTexParameteri(target,GL_TEXTURE_MIN_FILTER,GL_LINEAR);return 0;
}
