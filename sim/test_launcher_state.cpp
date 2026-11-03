// SPDX-License-Identifier: MIT
#include "ui_state.hpp"
#include "game_catalog.hpp"
#include <cassert>
#include <iostream>
using namespace launcher;
int main(){
    State s;assert(kGames.size()>=14&&s.visible(kGames).size()==kGames.size());
    s.move(0,1,kGames);assert(s.selected==4);
    s.move(1,0,kGames);assert(s.selected==5);
    s.move(0,-1,kGames);assert(s.selected==1);
    s.selected=3;s.move(1,0,kGames);assert(s.selected==3); // no row wrapping
    s.selected=0;s.move(-1,0,kGames);assert(s.selected==0);
    s.setFilter(Filter::Voxel,kGames);assert(s.selected==6&&s.visible(kGames)==std::vector<int>({6,7}));
    s.move(0,1,kGames);assert(s.selected==6);
    s.move(1,0,kGames);assert(s.selected==7);
    s.setFilter(Filter::All,kGames);assert(s.selected==7);
    s.setFilter(Filter::Action,kGames);assert(s.selected==3);auto action=s.visible(kGames);assert(action.size()>=3&&action[0]==3&&action[1]==4&&action[2]==5);
    s.modal=true;s.move(1,0,kGames);assert(s.selected==3);
    s.modal=false;s.page=Page::Display;s.move(1,0,kGames);assert(s.selected==3);
    assert(allowedOutput("dp")&&allowedOutput("lcd")&&!allowedOutput("shell"));
    assert(allowedAspect("fit")&&allowedAspect("integer")&&!allowedAspect("stretch"));
    s.page=Page::Library;s.setFilter(Filter::All,kGames);s.selected=0;s.turnPage(1,kGames);assert(s.selected==8&&s.pageIndex(kGames)==1);s.turnPage(-1,kGames);assert(s.selected==0);
    s.query="NeVeR";s.normalize(kGames);assert(s.visible(kGames)==std::vector<int>({1,2}));
    s.query="推箱";s.normalize(kGames);assert(s.visible(kGames).size()==1&&std::string(kGames[s.selected].id)=="arcade-sokoban");
    s.query="no-such-game";s.normalize(kGames);s.turnPage(1,kGames);s.move(1,1,kGames);assert(s.visible(kGames).empty());
    s.query.clear();s.favorites.insert("arcade-mines");s.setFilter(Filter::Favorites,kGames);assert(s.visible(kGames).size()==1&&std::string(kGames[s.selected].id)=="arcade-mines");
    s.favorites.clear();assert(s.visible(kGames).empty());s.setFilter(Filter::All,kGames);s.recent={"minecraft-java","neverputt"};auto recent=s.visible(kGames);assert(recent[0]==7&&recent[1]==2&&recent.size()==kGames.size());
    std::cout<<"LAUNCHER_STATE_PASS filtered_navigation modal_focus preference_whitelist\n";
}
