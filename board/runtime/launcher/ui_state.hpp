// SPDX-License-Identifier: MIT
#pragma once
#include <algorithm>
#include <array>
#include <cctype>
#include <set>
#include <string>
#include <vector>

namespace launcher {
enum class Page { Library, Display, Help };
enum class Filter { All, Leisure, Action, Voxel, Favorites };
struct Game {
    const char *id, *title, *category, *genre, *description, *controls, *adapter;
};
struct Preferences {
    std::string output = "dp";
    std::string aspect = "fit";
    bool fsr = false;
    bool operator==(const Preferences& b) const { return output == b.output && aspect == b.aspect && fsr == b.fsr; }
};
struct State {
    Page page = Page::Library;
    Filter filter = Filter::All;
    int selected = 0;
    bool modal = false;
    Preferences preferences;
    std::string query;
    std::set<std::string> favorites;
    std::vector<std::string> recent;
    static std::string lower(std::string value){for(char& c:value)if(static_cast<unsigned char>(c)<128)c=char(std::tolower(static_cast<unsigned char>(c)));return value;}
    std::vector<int> visible(const std::vector<Game>& games) const {
        std::vector<int> result;
        const char* category = filter == Filter::Leisure ? "leisure" : filter == Filter::Action ? "action" : "voxel";
        const auto needle=lower(query);
        for (unsigned i = 0; i < games.size(); ++i){
            const auto& g=games[i];
            bool matches=filter==Filter::All||(filter==Filter::Favorites?favorites.count(g.id)!=0:g.category==std::string(category));
            std::string searchable=std::string(g.id)+" "+g.title+" "+g.genre+" "+g.description;
            if(matches&&(needle.empty()||lower(searchable).find(needle)!=std::string::npos))result.push_back(i);
        }
        if(!recent.empty())std::stable_sort(result.begin(),result.end(),[&](int a,int b){return std::find(recent.begin(),recent.end(),games[a].id)<std::find(recent.begin(),recent.end(),games[b].id);});
        return result;
    }
    void normalize(const std::vector<Game>& games){const auto ids=visible(games);if(!ids.empty()&&std::find(ids.begin(),ids.end(),selected)==ids.end())selected=ids.front();}
    int pageIndex(const std::vector<Game>& games)const{const auto ids=visible(games);auto p=std::find(ids.begin(),ids.end(),selected);return p==ids.end()?0:int(p-ids.begin())/8;}
    void turnPage(int delta,const std::vector<Game>& games){const auto ids=visible(games);if(ids.empty())return;int page=std::clamp(pageIndex(games)+delta,0,int((ids.size()-1)/8));selected=ids[page*8];}
    void setFilter(Filter value, const std::vector<Game>& games) {
        filter = value;
        const auto ids = visible(games);
        if (!ids.empty() && std::find(ids.begin(), ids.end(), selected) == ids.end()) selected = ids.front();
    }
    void move(int dx, int dy, const std::vector<Game>& games) {
        if (modal || page != Page::Library) return;
        const auto ids = visible(games);
        if (ids.empty()) return;
        auto it = std::find(ids.begin(), ids.end(), selected);
        int index = it == ids.end() ? 0 : int(it - ids.begin());
        const int row = index / 4;
        if (dx) {
            const int next = index + dx;
            if (next >= 0 && next < int(ids.size()) && next / 4 == row) index = next;
        }
        if (dy) {
            const int next = index + 4 * dy;
            if (next >= 0 && next < int(ids.size())) index = next;
        }
        selected = ids[index];
    }
};
inline bool allowedOutput(const std::string& value) { return value == "dp" || value == "lcd"; }
inline bool allowedAspect(const std::string& value) { return value == "fit" || value == "integer"; }
} // namespace launcher
