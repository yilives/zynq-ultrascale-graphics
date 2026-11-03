// SPDX-License-Identifier: MIT
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <deque>
#include <queue>
#include <set>
#include <string>
#include <unordered_set>
#include <vector>

namespace arcade {
struct Rng {
    uint32_t state=0x5eeda123;
    uint32_t next(){state^=state<<13;state^=state>>17;state^=state<<5;return state;}
    int pick(int n){return int(next()%unsigned(n));}
};
struct Point {int x,y;bool operator==(const Point& b)const{return x==b.x&&y==b.y;}};
inline constexpr Point directions[]={{0,-1},{1,0},{0,1},{-1,0}};

struct Snake {
    static constexpr int W=28,H=17;
    std::deque<Point> body{{7,8},{6,8},{5,8}};Point food{12,8};int direction=1,pending=1,score=0;
    bool over=false,won=false;float clock=0;Rng rng;
    bool turn(int d){if(d<0||d>3||d==(direction+2)%4)return false;pending=d;return true;}
    void spawn(){std::vector<Point> free;for(int y=0;y<H;++y)for(int x=0;x<W;++x)if(std::find(body.begin(),body.end(),Point{x,y})==body.end())free.push_back({x,y});if(free.empty()){won=true;return;}food=free[rng.pick(int(free.size()))];}
    bool step(){
        if(over||won)return false;
        direction=pending;Point head{body.front().x+directions[direction].x,body.front().y+directions[direction].y};
        bool eats=head==food;auto end=body.end();if(!eats)--end;
        if(head.x<0||head.x>=W||head.y<0||head.y>=H||std::find(body.begin(),end,head)!=end){over=true;return false;}
        body.push_front(head);if(eats){score+=10;spawn();}else body.pop_back();return true;
    }
    void update(float dt){clock+=dt;float period=std::max(.075f,.16f-score*.00018f);while(clock>=period&&!over&&!won){clock-=period;step();}}
    int autoDirection()const{
        std::queue<Point> q;std::array<int,W*H> first;first.fill(-1);q.push(body.front());first[body.front().y*W+body.front().x]=4;
        while(!q.empty()){Point p=q.front();q.pop();for(int d=0;d<4;++d){Point n{p.x+directions[d].x,p.y+directions[d].y};if(n.x<0||n.x>=W||n.y<0||n.y>=H||first[n.y*W+n.x]>=0)continue;if(std::find(body.begin(),body.end()-1,n)!=body.end()-1)continue;int f=first[p.y*W+p.x]==4?d:first[p.y*W+p.x];if(n==food)return f;first[n.y*W+n.x]=f;q.push(n);}}
        for(int d=0;d<4;++d){Point p{body.front().x+directions[d].x,body.front().y+directions[d].y};if(d!=(direction+2)%4&&p.x>=0&&p.x<W&&p.y>=0&&p.y<H&&std::find(body.begin(),body.end()-1,p)==body.end()-1)return d;}return direction;
    }
};

struct Blocks {
    static constexpr int W=10,H=20;
    std::array<int,W*H> board{};std::array<int,7> bag{{0,1,2,3,4,5,6}};int bagAt=7;
    int kind=0,next=0,rotation=0,x=3,y=-1,score=0,lines=0;bool over=false;float clock=0;Rng rng;
    static constexpr uint16_t shapes[]={0x0f00,0x8e00,0x2e00,0x6600,0x6c00,0x4e00,0xc600};
    static bool cell(int k,int r,int xx,int yy){for(int i=0;i<(r&3);++i){int old=xx;xx=yy;yy=3-old;}return (shapes[k]&(0x8000u>>(yy*4+xx)))!=0;}
    int drawBag(){if(bagAt==7){for(int i=6;i>0;--i)std::swap(bag[i],bag[rng.pick(i+1)]);bagAt=0;}return bag[bagAt++];}
    Blocks(){kind=drawBag();next=drawBag();}
    bool fits(int nx,int ny,int nr)const{for(int j=0;j<4;++j)for(int i=0;i<4;++i)if(cell(kind,nr,i,j)){int a=nx+i,b=ny+j;if(a<0||a>=W||b>=H||(b>=0&&board[b*W+a]))return false;}return true;}
    bool move(int dx){if(over||!fits(x+dx,y,rotation))return false;x+=dx;return true;}
    bool rotate(){if(over)return false;for(int kick:{0,-1,1,-2,2})if(fits(x+kick,y,(rotation+1)&3)){x+=kick;rotation=(rotation+1)&3;return true;}return false;}
    int clear(){int n=0;for(int row=H-1;row>=0;--row){bool full=true;for(int col=0;col<W;++col)full&=board[row*W+col]!=0;if(full){++n;for(int b=row;b>0;--b)for(int a=0;a<W;++a)board[b*W+a]=board[(b-1)*W+a];std::fill(board.begin(),board.begin()+W,0);++row;}}lines+=n;static constexpr int points[]={0,100,300,500,800};score+=points[n]*(1+lines/10);return n;}
    void lock(){for(int j=0;j<4;++j)for(int i=0;i<4;++i)if(cell(kind,rotation,i,j)){if(y+j<0){over=true;return;}board[(y+j)*W+x+i]=kind+1;}clear();kind=next;next=drawBag();x=3;y=-1;rotation=0;clock=0;if(!fits(x,y,rotation))over=true;}
    bool down(bool soft=false){if(over)return false;if(fits(x,y+1,rotation)){++y;if(soft)++score;return true;}lock();return false;}
    void drop(){if(over)return;while(fits(x,y+1,rotation)){++y;score+=2;}lock();}
    void update(float dt){clock+=dt;float speed=std::max(.08f,.65f-.045f*(lines/10));while(clock>=speed&&!over){clock-=speed;down();}}
    void autoDrop(){
        if(over)return;
        int best=1000000,bx=x,br=rotation;
        for(int r=0;r<4;++r)for(int a=-3;a<W;++a){int b=-3;if(!fits(a,b,r))continue;while(fits(a,b+1,r))++b;bool above=false;auto test=board;for(int j=0;j<4;++j)for(int i=0;i<4;++i)if(cell(kind,r,i,j)){if(b+j<0)above=true;else test[(b+j)*W+a+i]=kind+1;}if(above)continue;int holes=0,height=0,rough=0,prev=0,full=0;for(int row=0;row<H;++row){bool all=true;for(int col=0;col<W;++col)all&=test[row*W+col]!=0;full+=all;}for(int col=0;col<W;++col){int h=0;for(int row=0;row<H;++row){if(test[row*W+col]&&!h)h=H-row;if(h&&!test[row*W+col])++holes;}height+=h;if(col)rough+=std::abs(h-prev);prev=h;}int cost=holes*90+height*4+rough*3-full*75;if(cost<best){best=cost;bx=a;br=r;}}
        x=bx;rotation=br;drop();
    }
};

struct Merge {
    std::array<int,16> board{},previous{};int score=0,oldScore=0;bool canUndo=false;Rng rng;
    Merge(){spawn();spawn();}
    void spawn(){std::vector<int> empty;for(int i=0;i<16;++i)if(!board[i])empty.push_back(i);if(!empty.empty())board[empty[rng.pick(int(empty.size()))]]=rng.pick(10)?2:4;}
    static int mergeLine(std::array<int,4>& line){std::array<int,4> packed{},result{};int n=0,k=0,points=0;for(int v:line)if(v)packed[n++]=v;for(int i=0;i<n;++i){int v=packed[i];if(i+1<n&&v==packed[i+1]){v*=2;++i;points+=v;}result[k++]=v;}line=result;return points;}
    bool move(int d,bool add=true){auto before=board;int points=0;for(int lane=0;lane<4;++lane){std::array<int,4> line;auto index=[&](int i){return d==0?i*4+lane:d==1?lane*4+3-i:d==2?(3-i)*4+lane:lane*4+i;};for(int i=0;i<4;++i)line[i]=board[index(i)];points+=mergeLine(line);for(int i=0;i<4;++i)board[index(i)]=line[i];}if(board==before)return false;previous=before;oldScore=score;canUndo=true;score+=points;if(add)spawn();return true;}
    void undo(){if(canUndo){board=previous;score=oldScore;canUndo=false;}}
    bool over()const{for(int i=0;i<16;++i){if(!board[i])return false;if(i%4<3&&board[i]==board[i+1])return false;if(i<12&&board[i]==board[i+4])return false;}return true;}
    int maximum()const{return *std::max_element(board.begin(),board.end());}
};

struct Breakout {
    static constexpr int W=10,H=5;
    std::array<int,W*H> bricks{};float px=200,bx=200,by=207,vx=82,vy=-114;int lives=3,score=0,level=1,hits=0;
    bool launched=false,over=false,won=false;
    Breakout(){fill();}
    void fill(){for(int y=0;y<H;++y)for(int x=0;x<W;++x)bricks[y*W+x]=(level>1&&y<2)?2:1;}
    void launch(){if(!over&&!won)launched=true;}
    void update(float dt,float input=0){
        if(over||won)return;
        px=std::clamp(px+input*240*dt,32.f,368.f);if(!launched){bx=px;by=208;return;}
        int steps=std::max(1,int(std::ceil(dt/.003f)));float step=dt/steps;
        for(int s=0;s<steps;++s){float ox=bx,oy=by;bx+=vx*step;by+=vy*step;
            if(bx<6){bx=6;vx=std::abs(vx);}if(bx>394){bx=394;vx=-std::abs(vx);}if(by<28){by=28;vy=std::abs(vy);}
            if(vy>0&&by>=213&&oy<213&&std::abs(bx-px)<34){by=212;vx=(bx-px)*4.2f;vy=-std::sqrt(std::max(6000.f,18000.f-vx*vx));}
            bool collided=false;for(int y=0;y<H&&!collided;++y)for(int x=0;x<W;++x){int i=y*W+x;if(!bricks[i])continue;float left=12+x*38,top=40+y*17;
                if(bx>=left-3&&bx<left+35&&by>=top-3&&by<top+16){--bricks[i];++hits;score+=10;if(oy<top-3||oy>=top+16){vy=-vy;by=oy;}else{vx=-vx;bx=ox;}collided=true;break;}}
            if(by>244){if(--lives==0)over=true;launched=false;bx=px;by=208;vx=82;vy=-114;break;}
            if(std::all_of(bricks.begin(),bricks.end(),[](int v){return v==0;})){score+=100;if(++level>3){won=true;break;}fill();launched=false;bx=px;by=208;break;}
        }
    }
};

struct Sokoban {
    struct Frame {int player;std::vector<int> boxes;int moves,pushes;};
    static std::vector<std::vector<std::string>> levels(){return {
        {"#######","#     #","# @$. #","#     #","#######"},
        {"#######","#  .  #","#  $  #","#  @  #","#     #","#######"},
        {"########","#      #","# .$$.@#","#      #","#      #","########"},
        {"########","# . .  #","# $ $  #","#      #","#  @   #","########"},
        {"########","#      #","# . .  #","# $ $  #","#   @  #","#      #","########"},
        {"########","#   .  #","#  $   #","# . $  #","#  @   #","#      #","########"}};}
    int level=0,width=0,height=0,player=0,moves=0,pushes=0;std::string floor;std::vector<int> boxes;std::vector<Frame> history;
    Sokoban(){load(0);}
    void load(int n){level=n%int(levels().size());auto rows=levels()[level];height=int(rows.size());width=int(rows[0].size());floor.clear();boxes.clear();history.clear();moves=pushes=0;for(int y=0;y<height;++y)for(int x=0;x<width;++x){char c=rows[y][x];int p=y*width+x;floor+=c=='#'?'#':(c=='.'||c=='*'||c=='+')?'.':' ';if(c=='$'||c=='*')boxes.push_back(p);if(c=='@'||c=='+')player=p;}}
    bool wall(int p)const{return p<0||p>=int(floor.size())||floor[p]=='#';}
    bool won()const{return std::all_of(boxes.begin(),boxes.end(),[&](int p){return floor[p]=='.';});}
    bool move(int d){int delta=d==0?-width:d==1?1:d==2?width:-1,n=player+delta;if(wall(n))return false;auto box=std::find(boxes.begin(),boxes.end(),n);if(box!=boxes.end()&&(wall(n+delta)||std::find(boxes.begin(),boxes.end(),n+delta)!=boxes.end()))return false;history.push_back({player,boxes,moves,pushes});if(box!=boxes.end()){*box=n+delta;++pushes;}player=n;++moves;return true;}
    void undo(){if(history.empty())return;auto f=history.back();history.pop_back();player=f.player;boxes=f.boxes;moves=f.moves;pushes=f.pushes;}
    std::string solution()const{
        struct Node {int player;std::vector<int> boxes;std::string path;};
        auto encode=[](int p,std::vector<int> b){std::sort(b.begin(),b.end());std::string k(1,char(p));for(int x:b)k+=char(x);return k;};
        std::queue<Node> q;q.push({player,boxes,{}});std::unordered_set<std::string> visited;visited.insert(encode(player,boxes));
        while(!q.empty()&&visited.size()<100000){auto s=q.front();q.pop();if(std::all_of(s.boxes.begin(),s.boxes.end(),[&](int p){return floor[p]=='.';}))return s.path;
            for(int d=0;d<4;++d){int delta=d==0?-width:d==1?1:d==2?width:-1,n=s.player+delta;if(wall(n))continue;auto b=s.boxes;auto it=std::find(b.begin(),b.end(),n);if(it!=b.end()){if(wall(n+delta)||std::find(b.begin(),b.end(),n+delta)!=b.end())continue;*it=n+delta;}auto key=encode(n,b);if(visited.insert(key).second)q.push({n,b,s.path+char('0'+d)});}}
        return {};
    }
};

struct Mines {
    static constexpr int W=9,H=9,N=W*H,COUNT=10;
    std::array<bool,N> mines{},open{},flag{};bool placed=false,over=false,won=false;int revealed=0;Rng rng;
    void place(int first){std::vector<int> slots;for(int i=0;i<N;++i)if(std::abs(i%W-first%W)>1||std::abs(i/W-first/W)>1)slots.push_back(i);for(int i=int(slots.size())-1;i>0;--i)std::swap(slots[i],slots[rng.pick(i+1)]);for(int i=0;i<COUNT;++i)mines[slots[i]]=true;placed=true;}
    int around(int at)const{int n=0;for(int i=0;i<N;++i)if(i!=at&&std::abs(i%W-at%W)<=1&&std::abs(i/W-at/W)<=1)n+=mines[i];return n;}
    bool reveal(int at){if(at<0||at>=N||over||won||flag[at]||open[at])return false;if(!placed)place(at);if(mines[at]){over=true;open[at]=true;return true;}std::queue<int> q;q.push(at);while(!q.empty()){int p=q.front();q.pop();if(open[p]||flag[p]||mines[p])continue;open[p]=true;++revealed;if(around(p)==0)for(int i=0;i<N;++i)if(!open[i]&&!flag[i]&&std::abs(i%W-p%W)<=1&&std::abs(i/W-p/W)<=1)q.push(i);}won=revealed==N-COUNT;return true;}
    bool toggle(int at){if(at<0||at>=N||over||won||open[at])return false;flag[at]=!flag[at];return true;}
    void chord(int at){if(at<0||at>=N||!open[at]||over||won)return;int flags=0;for(int i=0;i<N;++i)if(i!=at&&std::abs(i%W-at%W)<=1&&std::abs(i/W-at/W)<=1)flags+=flag[i];if(flags==around(at))for(int i=0;i<N&&!over;++i)if(i!=at&&std::abs(i%W-at%W)<=1&&std::abs(i/W-at/W)<=1)reveal(i);}
};
} // namespace arcade
