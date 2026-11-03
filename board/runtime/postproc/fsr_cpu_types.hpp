// SPDX-License-Identifier: MIT
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
using AF1=float;using AP1=bool;
template<int N> struct V {
 union {struct {float x,y,z,w;};struct {float r,g,b,a;};};
 explicit V(float v=0):x(v),y(v),z(v),w(v){}
 V(float p,float q,float s=0,float t=0):x(p),y(q),z(s),w(t){}
 V<3> rgb() const{return V<3>(x,y,z);}
 V& operator+=(V b){x+=b.x;y+=b.y;z+=b.z;w+=b.w;return *this;}
 V& operator-=(V b){x-=b.x;y-=b.y;z-=b.z;w-=b.w;return *this;}
 V& operator*=(V b){x*=b.x;y*=b.y;z*=b.z;w*=b.w;return *this;}
};
using AF2=V<2>;using AF3=V<3>;using AF4=V<4>;
template<int N> V<N> operator+(V<N>a,V<N>b){return a+=b;}
template<int N> V<N> operator-(V<N>a,V<N>b){return a-=b;}
template<int N> V<N> operator*(V<N>a,V<N>b){return a*=b;}
template<int N> V<N> operator*(V<N>a,float b){return a*=V<N>(b);}
template<int N> V<N> operator*(float a,V<N>b){return b*a;}
template<int N> V<N> min(V<N>a,V<N>b){return V<N>(fminf(a.x,b.x),fminf(a.y,b.y),fminf(a.z,b.z),fminf(a.w,b.w));}
template<int N> V<N> max(V<N>a,V<N>b){return V<N>(fmaxf(a.x,b.x),fmaxf(a.y,b.y),fmaxf(a.z,b.z),fmaxf(a.w,b.w));}
inline float min(float a,float b){return fminf(a,b);}inline float max(float a,float b){return fmaxf(a,b);}
inline float abs(float a){return fabsf(a);}
struct I2 {int x,y;I2(int a=0,int b=0):x(a),y(b){}};
using AU2=I2;using ASU2=I2;
inline I2 operator+(I2 a,I2 b){return I2(a.x+b.x,a.y+b.y);}
struct AU4 {uint32_t x=0,y=0,z=0,w=0;};
inline uint32_t AU1_AF1(float x){uint32_t v;memcpy(&v,&x,4);return v;}
inline float AF1_AU1(uint32_t x){float v;memcpy(&v,&x,4);return v;}
inline float ARcpF1(float x){return 1.0f/x;}
inline float APrxLoRcpF1(float a){return AF1_AU1(0x7ef07ebb-AU1_AF1(a));}
inline float APrxMedRcpF1(float a){float b=AF1_AU1(0x7ef19fff-AU1_AF1(a));return b*(-b*a+2.0f);}
inline float APrxLoRsqF1(float a){return AF1_AU1(0x5f347d74-(AU1_AF1(a)>>1));}
inline float ASatF1(float a){return max(0,min(1,a));}
inline float AMin3F1(float a,float b,float c){return min(a,min(b,c));}
inline float AMax3F1(float a,float b,float c){return max(a,max(b,c));}
inline AF3 AMin3F3(AF3 a,AF3 b,AF3 c){return min(a,min(b,c));}
inline AF3 AMax3F3(AF3 a,AF3 b,AF3 c){return max(a,max(b,c));}
#define AF1_(x) float(x)
#define AF2_(x) AF2(x)
#define AF3_(x) AF3(x)
#define AF4_(x) AF4(x)
#define FSR_RCAS_LIMIT (0.25f-1.0f/16.0f)
