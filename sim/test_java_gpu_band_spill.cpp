// SPDX-License-Identifier: GPL-3.0-or-later
#include "renderer/threadedvertextransformer/ThreadedVertexTransformer.hpp"
#include <cassert>
#include <iostream>
#include <vector>
#include <memory>
#include <type_traits>
using namespace rr;
struct SyncRunner:IThreadRunner{
 void wait()override{} void run(const std::function<void()>& f)override{f();} bool isBusy()const override{return false;}
};
struct CaptureDevice:IDevice{
 std::array<std::vector<uint8_t>,6> buffers;
 std::array<unsigned,3> triangles{},commits{},loads{};unsigned submissions=0;
 CaptureDevice(std::size_t capacity){for(auto& b:buffers)b.resize(capacity);}
 void streamDisplayList(uint8_t index,uint32_t size)override{
  assert(size<=buffers[index].size());submissions++;
  displaylist::DisplayList list;list.setBuffer({buffers[index]});list.setCurrentSize(size);list.resetGet();
  displaylist::DisplayListDisassembler reader(list);
  while(reader.hasNextCommand()){
   assert(reader.handleNextCommand([&](const auto& cmd){
    using C=std::decay_t<decltype(cmd)>;
    if constexpr(std::is_same_v<C,TriangleStreamCmd>)triangles[index/2]++;
    if constexpr(std::is_same_v<C,FramebufferCmd>){if(cmd.getCommitFramebuffer())commits[index/2]++;if(cmd.getLoadFramebuffer())loads[index/2]++;}
    return true;
   }));
  }
 }
 bool writeToDeviceMemory(tcb::span<const uint8_t>,uint32_t)override{return true;}
 bool readFromDeviceMemory(tcb::span<uint8_t>,uint32_t)override{return true;}
 void blockUntilDeviceIsIdle()override{}
 tcb::span<uint8_t> requestDisplayListBuffer(uint8_t index)override{return {buffers[index]};}
 uint8_t getDisplayListBufferCount()const override{return 6;}
};
CaptureDevice run(std::size_t capacity,unsigned count){
 CaptureDevice device(capacity);SyncRunner worker,uploader;
 auto transform=std::make_unique<threadedvertextransformer::ThreadedVertexTransformer>(device,worker,uploader);
 displaylist::DisplayListAssembler<RenderConfig::TMU_COUNT,displaylist::DisplayList,false> input;
 input.setBuffer(transform->requestDisplayListBuffer(0),0);
 auto add=[&](const auto& cmd){assert(input.addCommand(cmd));};
 add(WriteRegisterCmd{RenderResolutionReg{400,240}});
 transform::ElementGlobalData global;global.viewPort.viewportWidth=400;global.viewPort.viewportHeight=240;
 global.viewPort.viewportWidthHalf=200;global.viewPort.viewportHeightHalf=120;global.culling.enableCulling=false;
 add(SetElementGlobalCtxCmd{global});
 transform::ElementLocalData local;local.primitiveAssembler.mode=DrawMode::TRIANGLES;local.primitiveAssembler.primitiveCount=count*3;
 local.transformMatrices.modelView.identity();local.transformMatrices.projection.identity();local.transformMatrices.color.identity();
 for(auto& m:local.transformMatrices.texture)m.identity();
 add(SetElementLocalCtxCmd{local});add(DrawNewElementCmd{});
 for(unsigned i=0;i<count*3;i++){
  VertexParameter v{};v.vertex=Vec4{float(i%3==1?.5f:-.5f),float(i%3==2?.8f:-.8f),.5f,1};
  v.color=Vec4{1,1,0,1};v.normal=Vec3{0,0,1};v.pointSize=1;v.sourceIndex=i;
  for(auto& uv:v.tex)uv=Vec4{0,0,0,1};add(PushVertexCmd{v});
 }
 FramebufferCmd end{true,true,true,400*240};end.commitFramebuffer();add(end);
 transform->streamDisplayList(0,input.getDisplayListSize());transform->blockUntilDeviceIsIdle();
 return device;
}
int main(int argc,char**){
 const auto reference=run(1024*1024,1),large=run(64*1024,4000);
 bool complete=true;for(unsigned i=0;i<3;i++){
  complete=complete&&(large.triangles[i]==reference.triangles[i]*4000);
  std::cout<<"BAND "<<i<<" triangles="<<large.triangles[i]<<" expected="<<reference.triangles[i]*4000<<" commits="<<large.commits[i]<<" loads="<<large.loads[i]<<"\n";
 }
 if(argc>1){assert(!complete);std::cout<<"JAVA_GPU_OLD_TRUNCATION_REPRODUCED\n";return 0;}
 assert(complete);assert(large.submissions>3);
 for(unsigned i=0;i<3;i++){assert(large.commits[i]>1);assert(large.loads[i]+1==large.commits[i]);}
 std::cout<<"JAVA_GPU_BAND_SPILL_PASS triangles=4000 bands=3 all_committed=1 no_truncation=1\n";
 return 0;
}
