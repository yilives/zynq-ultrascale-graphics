// SPDX-License-Identifier: MIT
#include "rules.hpp"
#include <cassert>
#include <iostream>
using namespace arcade;
int main(){
    Snake s;s.food={8,8};assert(!s.turn(3));assert(s.step()&&s.score==10&&s.body.size()==4);assert(std::find(s.body.begin(),s.body.end(),s.food)==s.body.end());s.body={{27,8},{26,8},{25,8}};s.direction=s.pending=1;s.step();assert(s.over);
    s=Snake();s.body={{1,1},{1,2},{2,2},{2,1}};s.direction=0;s.pending=1;s.food={10,10};assert(s.step()&&!s.over); // entering the tail that vacates is legal
    Blocks b;std::set<int> bag;bag.insert(b.kind);bag.insert(b.next);for(int i=0;i<5;++i)bag.insert(b.drawBag());assert(bag.size()==7);
    for(int i=190;i<200;++i)b.board[i]=1;
    b.board[180]=2;assert(b.clear()==1&&b.lines==1&&b.board[190]==2);
    b=Blocks();b.kind=3;b.x=3;b.y=17;b.drop();assert(std::count(b.board.begin(),b.board.end(),4)==4);
    for(int k=0;k<7;++k)for(int r=0;r<4;++r){int n=0;for(int y=0;y<4;++y)for(int x=0;x<4;++x)n+=Blocks::cell(k,r,x,y);assert(n==4);}
    std::array<int,4> row{{2,2,2,2}};assert(Merge::mergeLine(row)==8&&(row==std::array<int,4>{{4,4,0,0}}));row={{4,0,4,8}};assert(Merge::mergeLine(row)==8&&(row==std::array<int,4>{{8,8,0,0}}));
    Merge m;m.board={2,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0};m.score=0;assert(m.move(3,false)&&m.board[0]==4&&m.score==4);m.undo();assert(m.board[0]==2&&m.board[1]==2&&m.score==0);assert(m.move(3,false));m.board={2,4,2,4,4,2,4,2,2,4,2,4,4,2,4,2};assert(m.over());m.board[0]=4;assert(!m.over());
    Breakout a;assert(std::count(a.bricks.begin(),a.bricks.end(),1)==50);a.launched=true;a.bx=25;a.by=59;a.vx=0;a.vy=-100;a.update(.03f);assert(a.hits==1&&a.score==10);
    a=Breakout();a.launched=true;a.px=200;a.bx=200;a.by=212;a.vx=0;a.vy=100;a.update(.02f);assert(a.vy<0&&a.lives==3);a.bx=10;a.by=243;a.vy=200;a.update(.02f);assert(a.lives==2&&!a.launched);
    for(int level=0;level<int(Sokoban::levels().size());++level){Sokoban k;k.load(level);auto solution=k.solution();assert(!solution.empty());int at=k.player;for(char d:solution)assert(k.move(d-'0'));assert(k.won());for(unsigned i=0;i<solution.size();++i)k.undo();assert(k.player==at&&k.moves==0&&!k.won());}
    for(int first:{0,40,80}){Mines n;assert(n.reveal(first)&&!n.over&&n.around(first)==0);assert(std::count(n.mines.begin(),n.mines.end(),true)==10);for(int i=0;i<81;++i)if(!n.mines[i])n.reveal(i);assert(n.won&&n.revealed==71);}
    Mines n;n.reveal(40);for(int i=0;i<81;++i)if(n.mines[i]){n.toggle(i);assert(!n.reveal(i));n.toggle(i);n.reveal(i);break;}assert(n.over);
    std::cout<<"ARCADE_RULES_PASS snake_tail_and_growth seven_bag_rotation_and_line_clear merge_once_and_undo breakout_collision_and_lives six_sokoban_solutions_and_undo mines_safe_first_win_loss\n";
}
