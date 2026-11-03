// SPDX-License-Identifier: GPL-3.0-or-later
// Bounded convex clipping in eye space; attributes use the same edge parameter.
#include "PlaneClipper.hpp"
#include <algorithm>

namespace rr::planeclipper {
tcb::span<TransformingVertexParameter> PlaneClipperCalc::clipPolygon(ClipList& list, ClipList& scratch, std::size_t count) {
    ClipList* input=&list;
    ClipList* output=&scratch;
    for (std::size_t p=0;p<6 && count;p++) {
        if (!(m_data.enabledMask & (1u<<p))) continue;
        const auto& equation=m_data.equations[p];
        std::size_t written=0;
        std::size_t previous=count-1;
        float d0=(*input)[previous].vertex.dot(equation);
        for (std::size_t i=0;i<count;i++) {
            float d1=(*input)[i].vertex.dot(equation);
            if ((d0>=0)!=(d1>=0)) {
                // A triangle gains at most one vertex per convex half-space.
                if (written>=output->size()) return {};
                (*output)[written++]=clippinghelper::ClippingHelper::lerp(d0/(d0-d1),(*input)[previous],(*input)[i]);
            }
            if (d1>=0) {
                if (written>=output->size()) return {};
                (*output)[written++]=(*input)[i];
            }
            previous=i;
            d0=d1;
        }
        count=written;
        std::swap(input,output);
    }
    return {input->data(),count};
}
tcb::span<TransformingVertexParameter> PlaneClipperCalc::clipTriangle(ClipList& list, ClipList& scratch) {
    return clipPolygon(list,scratch,3);
}
tcb::span<TransformingVertexParameter> PlaneClipperCalc::clipLine(ClipList& list, ClipList&) {
    for (std::size_t p=0;p<6;p++) {
        if (!(m_data.enabledMask & (1u<<p))) continue;
        float a=list[0].vertex.dot(m_data.equations[p]);
        float b=list[1].vertex.dot(m_data.equations[p]);
        if (a<0 && b<0) return {};
        if (a<0) list[0]=clippinghelper::ClippingHelper::lerp(a/(a-b),list[0],list[1]);
        else if (b<0) list[1]=clippinghelper::ClippingHelper::lerp(b/(b-a),list[1],list[0]);
    }
    return {list.data(),2};
}
tcb::span<TransformingVertexParameter> PlaneClipperCalc::clipPoint(ClipList& list, ClipList&) {
    for (std::size_t p=0;p<6;p++)
        if ((m_data.enabledMask & (1u<<p)) && list[0].vertex.dot(m_data.equations[p])<0) return {};
    return {list.data(),1};
}
}
