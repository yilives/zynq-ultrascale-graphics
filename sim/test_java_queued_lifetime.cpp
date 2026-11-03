// SPDX-License-Identifier: GPL-3.0-or-later
#include "java_queued_arrays.hpp"
#include "renderer/commands/PushVertexBatchCmd.hpp"
#include "renderer/displaylist/RIXDisplayListAssembler.hpp"
#include "renderer/displaylist/DisplayListDisassembler.hpp"
#include <thread>
#include <stdexcept>
namespace {
struct Arrays {
    std::vector<rr::Vec4> positions=std::vector<rr::Vec4>(257),colors;
    std::vector<rr::Vec3> normals;std::vector<float> points;
    std::array<std::vector<rr::Vec4>,2> tex;
};
void require(bool ok){if(!ok)throw std::runtime_error("Queued lifetime/serialization test failed");}
}
void queuedLifetimeTest(){
    rr::RenderObj state;state.setVertexColor({.25f,.5f,.75f,1});state.setNormal({0,0,1});state.setPointSize(3);
    state.setTexCoord(0,{.125f,.25f,0,1});state.setTexCoord(1,{.75f,.5f,0,1});
    state.enableColorArray(false);state.enableNormalArray(false);state.enablePointSizeArray(false);
    state.enableTexCoordArray(0,false);state.enableTexCoordArray(1,false);
    auto arrays=std::make_shared<Arrays>();
    for(std::size_t i=0;i<arrays->positions.size();++i)arrays->positions[i]=rr::Vec4{float(i),float(i+1),float(i+2),1};
    const java_prepared::View view(state,arrays->positions,arrays->colors,arrays->normals,arrays->points,arrays->tex);
    auto packet=std::make_shared<java_queued::Batch>(arrays,view,arrays->positions.size(),8192);
    const std::weak_ptr<const void> weak=arrays;
    auto slice=std::make_shared<java_queued::Batch>(*packet);slice->first=113;slice->count=91;
    java_queued::Retained retained;retained.add(packet);retained.add(slice);
    alignas(8) std::array<uint8_t,64> bytes{};
    rr::displaylist::DisplayList stream;stream.setBuffer(bytes);
    rr::displaylist::RIXDisplayListAssembler<rr::displaylist::DisplayList> assembler(stream);
    const auto command=rr::vertexBatchCommand(packet.get());require(command.payload()[0][0]!=0);
    require(assembler.addCommand(command));require(assembler.addCommand(rr::vertexBatchCommand(slice.get())));require(stream.getSize()==24);
    require(reinterpret_cast<uintptr_t>(bytes.data()+4)%8==4);
    arrays.reset();packet.reset();slice.reset();require(!weak.expired());
    // Later call-time state changes must not change the queued constants.
    state.setVertexColor({0,0,0,0});state.setPointSize(99);state.setTexCoord(1,{0,0,0,0});
    std::size_t read=0;
    std::thread consumer([&]{
        rr::displaylist::DisplayListDisassembler decoder(stream);
        while(decoder.hasNextCommand())require(decoder.handleNextCommand([&](const auto& cmd){
            using T=std::decay_t<decltype(cmd)>;
            if constexpr(std::is_same_v<T,rr::PushVertexBatchCmd>){
                const auto* batch=rr::vertexBatchPointer<java_queued::Batch>(cmd);require((batch->count==257&&batch->first==0)||(batch->count==91&&batch->first==113));
                for(std::size_t i=0;i<batch->count;++i){
                    const auto index=batch->first+i;const auto value=batch->view.at(index);
                    require(value.sourceIndex==index&&value.vertex[0]==float(index)&&value.vertex[2]==float(index+2));
                    require(value.color[0]==.25f&&value.color[2]==.75f&&value.pointSize==3&&value.tex[1][0]==.75f);++read;
                }
                return true;
            }else return false;
        }));require(!decoder.hasNextCommand());
    });consumer.join();require(read==348&&!weak.expired());retained.clear();require(weak.expired());
    // A giant batch is admitted alone; another batch forces a drain. Count and
    // charged-source limits prevent unbounded retained command descriptors.
    auto other=std::make_shared<Arrays>();const java_prepared::View v(state,other->positions,other->colors,other->normals,other->points,other->tex);
    auto small=std::make_shared<java_queued::Batch>(other,v,257,1);
    for(std::size_t i=0;i<java_queued::Retained::countLimit;++i){require(!retained.needsDrain(*small));retained.add(small);}
    require(retained.needsDrain(*small));retained.clear();
    auto large=std::make_shared<java_queued::Batch>(other,v,257,java_queued::Retained::byteLimit+1);
    require(!retained.needsDrain(*large));retained.add(large);require(retained.needsDrain(*small));retained.clear();
}
