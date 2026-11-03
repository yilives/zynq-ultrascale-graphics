#include "java_display_list_store.hpp"
#include <cassert>
#include <cstdio>
int main(){
 unsigned error=0;java_lists::Store s([&](uint32_t value){if(!error)error=value;});int value=0;
 auto checkError=[&](unsigned expected){assert(error==expected);error=0;};
 auto first=s.gen(3000000);assert(first==1&&!s.isList(first));
 s.erase(16,16);assert(s.gen(16)==16);assert(s.gen(1)==3000001);
 s.begin(1,java_lists::COMPILE);{java_lists::Store::Guard g(s,[&]{++value;});if(!g.skip)++value;}s.end();assert(!value&&s.isList(1));s.call(1);assert(value==1);
 s.begin(2,java_lists::COMPILE_EXECUTE);{java_lists::Store::Guard g(s,[&]{value+=2;});if(!g.skip)value+=2;}s.end();assert(value==3);s.call(2);assert(value==5);
 s.begin(3,java_lists::COMPILE);s.append([&]{s.call(1);});s.end();
 s.begin(1,java_lists::COMPILE);s.append([&]{value+=4;});s.end();s.call(3);assert(value==9);
 s.erase(1,1);assert(!s.isList(1));s.call(3);assert(value==9);assert(s.gen(1)==1);
 s.begin(4,0);checkError(java_lists::INVALID_ENUM);assert(!s.active);
 s.begin(0,java_lists::COMPILE);checkError(java_lists::INVALID_VALUE);
 s.end();checkError(java_lists::INVALID_OPERATION);
 s.gen(-1);checkError(java_lists::INVALID_VALUE);
 s.begin(4,java_lists::COMPILE);s.begin(5,java_lists::COMPILE);checkError(java_lists::INVALID_OPERATION);s.end();
 s.begin(5,java_lists::COMPILE);s.append([&]{s.call(5);});s.end();s.call(5);checkError(java_lists::STACK_OVERFLOW);
 java_lists::Store small([&](uint32_t v){error=v;},128);
 small.begin(1,java_lists::COMPILE);small.append([&]{++value;});small.end();int before=value;
 small.begin(1,java_lists::COMPILE);assert(!small.append([]{},1024));checkError(java_lists::OUT_OF_MEMORY);small.end();small.call(1);assert(value==before+1);
 assert(s.gen(0)==0);checkError(0);
 std::printf("DISPLAY_LIST_STORE_PASS namespace=3000000 lifecycle=1 compile_execute=1 late_binding=1 recursion_limit=1 oom_preserves_old=1\n");
}
