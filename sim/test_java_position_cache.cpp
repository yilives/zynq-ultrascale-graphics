// SPDX-License-Identifier: GPL-3.0-or-later
#include "java_position_cache.hpp"
#include <cassert>
#include <iostream>
int main(){
 using V=std::array<float,4>;rr::java_position::Cache<V>c;V a{1,2,3,1},b{4,5,6,1},out{},projected{8,9,10,11};
 assert(!c.get(a,out));c.put(a,projected);assert(c.get(a,out)&&out==projected);assert(!c.get(b,out));
 V positive{0,2,3,1},negative{-0.0f,2,3,1};c.put(positive,projected);assert(!c.get(negative,out));
 c.put(a,projected);c.reset();assert(!c.get(a,out));
 for(unsigned i=0;i<10000;++i){V x{float(i),float(i%17),float(i%11),1},y{float(i+1),float(i%17),float(i%11),1};c.put(x,projected);assert(c.get(x,out)&&out==projected);assert(!c.get(y,out));}
 std::cout<<"JAVA_POSITION_CACHE_HOST_PASS exact_bits=1 signed_zero=1 reset=1 collision_keys=1\n";
}
