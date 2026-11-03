// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "vertexpipeline/RenderObj.hpp"
#include "VertexParameter.hpp"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <vector>

namespace java_prepared {
inline bool enabled() {
    static const bool value=[] {const char* p=std::getenv("RIX_JAVA_PREPARED_ARRAYS");return p&&p[0]=='1'&&p[1]=='\0';}();
    return value;
}
struct Statistics {unsigned long long fastDraws=0,fastVertices=0,slowDraws=0,slowVertices=0;};
inline Statistics& statistics(){static Statistics value;return value;}
inline void flushStatistics(){
    const char* path=std::getenv("RIX_JAVA_PREPARED_STATS");if(!path)return;
    if(FILE* file=std::fopen(path,"w")){
        const auto& s=statistics();
        std::fprintf(file,"{\"enabled\":%s,\"fast_draws\":%llu,\"fast_vertices\":%llu,\"fallback_draws\":%llu,\"fallback_vertices\":%llu}\n",enabled()?"true":"false",s.fastDraws,s.fastVertices,s.slowDraws,s.slowVertices);
        std::fclose(file);
    }
}
inline void record(std::size_t count,bool fast){
    static const bool logging=[] {if(!std::getenv("RIX_JAVA_PREPARED_STATS"))return false;std::atexit(flushStatistics);return true;}();
    if(!logging)return;
    auto& s=statistics();if(fast){++s.fastDraws;s.fastVertices+=count;}else{++s.slowDraws;s.slowVertices+=count;}
}
// Inputs are OwnedBatch's fully decoded, owned arrays. Only this CPU loop reads
// them; pushVertex copies the complete parameter into the existing command list.
class View {
    template<class T> struct ArrayView {
        const T* p=nullptr;std::size_t n=0;
        bool empty() const { return n==0; }
        const T& operator[](std::size_t i) const { return p[i]; }
    };
public:
    View(const rr::RenderObj& state,const std::vector<rr::Vec4>& positions,
        const std::vector<rr::Vec4>& colors,const std::vector<rr::Vec3>& normals,
        const std::vector<float>& points,
        const std::array<std::vector<rr::Vec4>,rr::RenderConfig::TMU_COUNT>& coordinates)
      :vertex{positions.data(),positions.size()},color{colors.data(),colors.size()},
       normal{normals.data(),normals.size()},point{points.data(),points.size()} {
        for(std::size_t t=0;t<tex.size();++t)tex[t]={coordinates[t].data(),coordinates[t].size()};
        if(color.empty())constant.color=state.getColor(0);
        if(normal.empty())constant.normal=state.getNormal(0);
        if(point.empty())constant.pointSize=state.getPointSize(0);
        for(std::size_t t=0;t<tex.size();++t)if(tex[t].empty())constant.tex[t]=state.getTexCoord(t,0);
    }
    void at(std::size_t i,rr::VertexParameter& value) const {
        value.sourceIndex=i;value.vertex=vertex[i];
        value.color=color.empty()?constant.color:color[i];
        value.normal=normal.empty()?constant.normal:normal[i];
        value.pointSize=point.empty()?constant.pointSize:point[i];
        for(std::size_t t=0;t<tex.size();++t)value.tex[t]=tex[t].empty()?constant.tex[t]:tex[t][i];
    }
private:
    ArrayView<rr::Vec4> vertex,color;
    ArrayView<rr::Vec3> normal;
    ArrayView<float> point;
    std::array<ArrayView<rr::Vec4>,rr::RenderConfig::TMU_COUNT> tex{};
    rr::VertexParameter constant;
};
} // namespace java_prepared
