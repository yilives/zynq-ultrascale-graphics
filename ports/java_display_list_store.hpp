// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <vector>
#include <new>
#include <algorithm>
#include <iterator>

namespace java_lists {
constexpr uint32_t INVALID_ENUM=0x500,INVALID_VALUE=0x501,INVALID_OPERATION=0x502,STACK_OVERFLOW=0x503,OUT_OF_MEMORY=0x505;
constexpr uint32_t COMPILE=0x1300,COMPILE_EXECUTE=0x1301;
using Command=std::function<void()>;
struct List {std::vector<Command> commands;size_t bytes=0;};
class Store {
 std::map<uint32_t,uint64_t> ranges;
 std::map<uint32_t,std::shared_ptr<List>> lists;
 std::shared_ptr<List> pending;
 std::function<void(uint32_t)> error;
 size_t used=0,limit;
 unsigned suppress=0,depth=0;
 bool poisoned=false;
 void reserve(uint32_t first,uint64_t end) {
  auto next=ranges.upper_bound(first);
  if(next!=ranges.begin()){auto prev=std::prev(next);if(prev->second>first)return;}
  auto pos=ranges.emplace(first,end).first;
  if(pos!=ranges.begin()){auto prev=std::prev(pos);if(prev->second==first){prev->second=end;ranges.erase(pos);pos=prev;}}
  next=std::next(pos);if(next!=ranges.end()&&pos->second==next->first){pos->second=next->second;ranges.erase(next);}
 }
public:
 uint32_t active=0,mode=0,base=0;
 bool primitive=false;
 explicit Store(std::function<void(uint32_t)> onError,size_t bytes=64*1024*1024):error(onError),limit(bytes){}
 void fail(uint32_t value){error(value);}
 void reset(){ranges.clear();lists.clear();pending.reset();used=0;suppress=depth=0;active=mode=base=0;primitive=poisoned=false;}
 bool capturing()const{return active&&!suppress;}
 bool isList(uint32_t name)const{return lists.count(name)!=0;}
 size_t memory()const{return used;}
 size_t available()const{return limit-used-(pending?pending->bytes:0);}
 uint32_t gen(int32_t count){
  if(count<0){fail(INVALID_VALUE);return 0;}if(!count)return 0;
  uint64_t first=1;
  for(const auto&r:ranges){if(first+uint64_t(count)<=r.first)break;if(first<r.second)first=r.second;}
  if(first+uint64_t(count)>0x100000000ULL){fail(OUT_OF_MEMORY);return 0;}
  try{reserve(uint32_t(first),first+count);}catch(const std::bad_alloc&){fail(OUT_OF_MEMORY);return 0;}
  return uint32_t(first);
 }
 void erase(uint32_t first,int32_t count){
  if(count<0){fail(INVALID_VALUE);return;}if(!count)return;
  const uint64_t end=std::min<uint64_t>(0x100000000ULL,uint64_t(first)+uint64_t(count));
  try{
   auto tail=ranges.upper_bound(first);
   if(tail!=ranges.begin())--tail;
   for(;tail!=ranges.end()&&tail->first<end;++tail)if(tail->second>end){ranges.emplace(uint32_t(end),tail->second);break;}
  }catch(const std::bad_alloc&){fail(OUT_OF_MEMORY);return;}
  for(auto it=ranges.begin();it!=ranges.end()&&it->first<end;){
   if(it->second<=first){++it;continue;}
   if(it->first<first){it->second=first;++it;}else it=ranges.erase(it);
  }
  for(auto it=lists.lower_bound(first);it!=lists.end()&&it->first<end;){used-=it->second->bytes;it=lists.erase(it);}
 }
 void begin(uint32_t name,uint32_t value){
  if(active){fail(INVALID_OPERATION);return;}if(!name){fail(INVALID_VALUE);return;}
  if(value!=COMPILE&&value!=COMPILE_EXECUTE){fail(INVALID_ENUM);return;}
  try{pending=std::make_shared<List>();}catch(const std::bad_alloc&){fail(OUT_OF_MEMORY);return;}
  active=name;mode=value;poisoned=false;primitive=false;
 }
 void end(){
  if(!active||primitive){fail(INVALID_OPERATION);return;}
  if(!poisoned)try{
   reserve(active,uint64_t(active)+1);
   auto old=lists.find(active);const size_t prior=old==lists.end()?0:old->second->bytes;
   lists[active]=pending;used=used-prior+pending->bytes;
  }catch(const std::bad_alloc&){fail(OUT_OF_MEMORY);}
  pending.reset();active=mode=0;poisoned=false;
 }
 bool append(Command command,size_t bytes=0){
  if(!capturing())return false;
  bytes+=sizeof(Command);
  if(poisoned||bytes>available()){poisoned=true;fail(OUT_OF_MEMORY);return false;}
  try{pending->commands.push_back(std::move(command));pending->bytes+=bytes;return true;}
  catch(const std::bad_alloc&){poisoned=true;fail(OUT_OF_MEMORY);return false;}
 }
 class Guard {
  Store* owner=nullptr;
 public:
  bool skip=false;
  Guard(Store&s,Command command,size_t bytes=0){
   if(!s.capturing())return;
   if(!s.append(std::move(command),bytes)||s.mode==COMPILE){skip=true;return;}
   owner=&s;++s.suppress;
  }
  ~Guard(){if(owner)--owner->suppress;}
  Guard(const Guard&)=delete;
 };
 void call(uint32_t name){
  auto found=lists.find(name);if(found==lists.end())return;
  if(depth>=64){fail(STACK_OVERFLOW);return;}
  auto list=found->second;
  struct Scope {Store&s;Scope(Store&v):s(v){++s.depth;++s.suppress;}~Scope(){--s.depth;--s.suppress;}} scope(*this);
  for(const auto&command:list->commands)command();
 }
};
}
