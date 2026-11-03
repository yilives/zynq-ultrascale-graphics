// SPDX-License-Identifier: MIT
// ARM game rules + fixed-function GL geometry; board pixels are drawn by RasterIX.
#include "rules.hpp"
#include "font.hpp"
#include <SDL.h>
#include <SDL_opengl.h>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <unistd.h>

namespace fs=std::filesystem;
using namespace arcade;
static volatile std::sig_atomic_t stopping=0;
static void onStop(int){stopping=1;}
struct Color{uint8_t r,g,b,a=255;};
constexpr Color ink{225,236,248},muted{135,161,186},panel{22,36,55},bg{10,18,31},green{116,234,166},gold{255,205,104};
const Color palette[]={{77,205,238},{95,126,244},{241,157,79},{245,209,101},{112,223,161},{181,132,236},{242,113,137}};
struct Vertex{float x,y,u,v;uint8_t r,g,b,a;};
class Canvas{
    std::vector<Vertex> vertices;GLuint texture=0;std::map<char,unsigned> slots;
    void vertex(float x,float y,float u,float v,Color c){vertices.push_back({x,y,u,v,c.r,c.g,c.b,c.a});}
public:
    Canvas(){
        // Two atlas texels per glyph pixel provide a full nearest-sampling margin
        // on both Mesa's pixel centres and RasterIX's fixed-point interpolation.
        std::array<uint8_t,128*128*4> pixels{};unsigned slot=0;
        for(auto entry:glyphs){unsigned c=slot++;slots[entry.first]=c;int x0=(c%8)*16,y0=(c/8)*16;for(int y=0;y<7;++y)for(int x=0;x<5;++x)if(entry.second[y]&(16>>x))for(int dy=0;dy<2;++dy)for(int dx=0;dx<2;++dx){int p=((y0+y*2+dy)*128+x0+x*2+dx)*4;pixels[p]=pixels[p+1]=pixels[p+2]=pixels[p+3]=255;}}
        int white=(127*128+127)*4;pixels[white]=pixels[white+1]=pixels[white+2]=pixels[white+3]=255;
        glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,128,128,0,GL_RGBA,GL_UNSIGNED_BYTE,pixels.data());
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);vertices.reserve(18000);
    }
    ~Canvas(){glDeleteTextures(1,&texture);}
    void quad(float x,float y,float w,float h,Color c,float u0,float v0,float u1,float v1){vertex(x,y,u0,v0,c);vertex(x+w,y,u1,v0,c);vertex(x+w,y+h,u1,v1,c);vertex(x,y,u0,v0,c);vertex(x+w,y+h,u1,v1,c);vertex(x,y+h,u0,v1,c);}
    void rect(float x,float y,float w,float h,Color c){quad(x,y,w,h,c,127.5f/128,127.5f/128,127.5f/128,127.5f/128);}
    void border(float x,float y,float w,float h,Color c){rect(x,y,w,1,c);rect(x,y+h-1,w,1,c);rect(x,y,1,h,c);rect(x+w-1,y,1,h,c);}
    void text(float x,float y,std::string s,Color c=ink,int scale=1){for(char ch:s){if(ch>='a'&&ch<='z')ch-=32;auto found=slots.find(ch);if(found!=slots.end()){unsigned n=found->second;float u=(n%8)*16+.5f,v=(n/8)*16-.5f;quad(x,y,5*scale,7*scale,c,u/128,v/128,(u+10)/128,(v+14)/128);}x+=6*scale;}}
    void disc(float x,float y,float radius,Color c){for(int i=0;i<16;++i){float a=i*6.2831853f/16,b=(i+1)*6.2831853f/16;vertex(x,y,127.5f/128,127.5f/128,c);vertex(x+radius*std::cos(a),y+radius*std::sin(a),127.5f/128,127.5f/128,c);vertex(x+radius*std::cos(b),y+radius*std::sin(b),127.5f/128,127.5f/128,c);}}
    void begin(const std::string& title){vertices.clear();rect(0,0,400,240,bg);rect(0,0,400,25,panel);text(12,8,title,green);text(270,8,"RASTERIX ARCADE",muted);}
    void finish(){
        glViewport(0,0,400,240);glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,400,240,0,-1,1);glMatrixMode(GL_MODELVIEW);glLoadIdentity();
        glDisable(GL_DEPTH_TEST);glDisable(GL_CULL_FACE);glDisable(GL_LIGHTING);glDisable(GL_ALPHA_TEST);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glEnable(GL_TEXTURE_2D);glBindTexture(GL_TEXTURE_2D,texture);
        glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_TEXTURE_COORD_ARRAY);glEnableClientState(GL_COLOR_ARRAY);
        glVertexPointer(2,GL_FLOAT,sizeof(Vertex),&vertices[0].x);glTexCoordPointer(2,GL_FLOAT,sizeof(Vertex),&vertices[0].u);glColorPointer(4,GL_UNSIGNED_BYTE,sizeof(Vertex),&vertices[0].r);
        glDrawArrays(GL_TRIANGLES,0,GLsizei(vertices.size()));glDisableClientState(GL_COLOR_ARRAY);glDisableClientState(GL_TEXTURE_COORD_ARRAY);glDisableClientState(GL_VERTEX_ARRAY);
    }
};

struct Games {
    std::string id;Snake snake;Blocks blocks;Merge merge;Breakout breakout;Sokoban sokoban;Mines mines;
    int cursor=40,best=0;bool started=false,paused=false;unsigned actions=0,updates=0,rounds=0;float autoClock=0,playTime=0;std::string solution;
    explicit Games(std::string name):id(std::move(name)){}
    int score()const{return id=="snake"?snake.score:id=="blocks"?blocks.score:id=="merge2048"?merge.score:id=="breakout"?breakout.score:id=="sokoban"?sokoban.level+int(sokoban.won()):mines.revealed;}
    bool over()const{return id=="snake"?snake.over:id=="blocks"?blocks.over:id=="merge2048"?merge.over():id=="breakout"?breakout.over:id=="sokoban"?false:mines.over;}
    bool won()const{return id=="snake"?snake.won:id=="breakout"?breakout.won:id=="sokoban"?sokoban.won():id=="mines"?mines.won:false;}
    void reset(){int level=sokoban.level;snake=Snake();blocks=Blocks();merge=Merge();breakout=Breakout();mines=Mines();if(id=="sokoban")sokoban.load(level);started=true;paused=false;solution.clear();playTime=0;++rounds;}
    void direction(int d){bool changed=false;if(id=="snake")changed=snake.turn(d);else if(id=="blocks"){if(d==0)changed=blocks.rotate();if(d==1)changed=blocks.move(1);if(d==2)changed=blocks.down(true);if(d==3)changed=blocks.move(-1);}else if(id=="merge2048")changed=merge.move(d);else if(id=="sokoban")changed=sokoban.move(d);else if(id=="mines"){int x=cursor%9+directions[d].x,y=cursor/9+directions[d].y;if(x>=0&&x<9&&y>=0&&y<9){cursor=y*9+x;changed=true;}}actions+=changed;}
    void key(SDL_Keycode key){
        if(key==SDLK_RETURN&&!started){started=true;return;}if(key==SDLK_r){reset();return;}if(key==SDLK_p&&started){paused=!paused;return;}if(!started||paused)return;
        if(key==SDLK_UP||key==SDLK_w)direction(0);
        if(key==SDLK_RIGHT||key==SDLK_d)direction(1);
        if(key==SDLK_DOWN||key==SDLK_s)direction(2);
        if(key==SDLK_LEFT||key==SDLK_a)direction(3);
        if(key==SDLK_SPACE||key==SDLK_RETURN){if(id=="blocks"){blocks.drop();++actions;}if(id=="breakout"){breakout.launch();++actions;}if(id=="mines")actions+=mines.reveal(cursor);}
        if(key==SDLK_u){if(id=="merge2048")merge.undo();if(id=="sokoban")sokoban.undo();++actions;}
        if(key==SDLK_n&&id=="sokoban"&&sokoban.won()){sokoban.load(sokoban.level+1);solution.clear();++actions;}
        if(key==SDLK_f&&id=="mines")actions+=mines.toggle(cursor);
    }
    void click(int x,int y,bool right,bool doubleClick){if(!started){started=true;return;}if(paused)return;if(id=="breakout")breakout.launch();if(id=="mines"&&x>=16&&x<196&&y>=38&&y<218){cursor=((y-38)/20)*9+(x-16)/20;if(doubleClick)mines.chord(cursor);else if(right)actions+=mines.toggle(cursor);else actions+=mines.reveal(cursor);}}
    void update(float dt,bool autoplay,const uint8_t* keys){
        if(autoplay&&!started)started=true;
        if(!started||paused)return;
        playTime+=dt;++updates;
        if(id=="snake"){if(autoplay)snake.turn(snake.autoDirection());snake.update(dt);}
        if(id=="blocks")blocks.update(dt);
        if(id=="breakout"){float input=keys?float(keys[SDL_SCANCODE_RIGHT]||keys[SDL_SCANCODE_D])-float(keys[SDL_SCANCODE_LEFT]||keys[SDL_SCANCODE_A]):0;if(autoplay){breakout.px=std::clamp(breakout.bx,32.f,368.f);breakout.launch();}breakout.update(dt,input);}
        autoClock+=dt;if(autoplay&&autoClock>.24f){autoClock=0;
            if(over()||(won()&&id!="sokoban")){reset();++actions;}
            if(id=="snake")++actions;
            if(id=="blocks"){blocks.autoDrop();++actions;}
            if(id=="merge2048"){for(int i=0;i<4;++i)if(merge.move(int((actions+i)%4))){++actions;break;}}
            if(id=="sokoban"){if(sokoban.won()){sokoban.load(sokoban.level+1);solution.clear();}if(solution.empty())solution=sokoban.solution();if(!solution.empty()){direction(solution[0]-'0');solution.erase(0,1);}}
            if(id=="mines"){int next=(actions*17+40)%81;for(int i=0;i<81;++i){int p=(next+i)%81;if(!mines.open[p]&&!mines.flag[p]){cursor=p;actions+=mines.reveal(p);break;}}}
            if(id=="breakout")++actions;
        }best=std::max(best,score());
    }
    void draw(Canvas& c){
        const std::map<std::string,std::string> titles={{"snake","SNAKE GARDEN"},{"blocks","FALLING BLOCKS"},{"merge2048","MERGE 2048"},{"breakout","BRICK BREAKER"},{"sokoban","SOKOBAN"},{"mines","MINEFIELD"}};
        c.begin(titles.at(id));
        if(id=="snake"){
            c.rect(13,37,282,172,panel);for(int y=0;y<Snake::H;++y)for(int x=0;x<Snake::W;++x)if((x+y)%2==0)c.rect(14+x*10,38+y*10,10,10,{25,43,55});
            for(unsigned i=0;i<snake.body.size();++i)c.rect(15+snake.body[i].x*10,39+snake.body[i].y*10,8,8,i?green:gold);
            c.disc(19+snake.food.x*10,43+snake.food.y*10,4,{243,119,135});c.text(308,46,"SCORE",muted);c.text(308,60,std::to_string(snake.score),green,2);c.text(308,96,"BEST",muted);c.text(308,110,std::to_string(best),gold,2);c.text(308,152,"ARROWS");c.text(308,165,"TO TURN");
        }else if(id=="blocks"){
            c.rect(60,31,100,190,panel);for(int y=0;y<20;++y)for(int x=0;x<10;++x){int k=blocks.board[y*10+x];if(k)c.rect(65+x*9,36+y*9,8,8,palette[k-1]);}
            auto piece=[&](int x,int y,int rotation,Color color){for(int j=0;j<4;++j)for(int i=0;i<4;++i)if(Blocks::cell(blocks.kind,rotation,i,j)&&y+j>=0)c.rect(65+(x+i)*9,36+(y+j)*9,8,8,color);};
            if(!blocks.over){int ghost=blocks.y;while(blocks.fits(blocks.x,ghost+1,blocks.rotation))++ghost;piece(blocks.x,ghost,blocks.rotation,{63,76,96});piece(blocks.x,blocks.y,blocks.rotation,palette[blocks.kind]);}
            c.text(192,38,"SCORE",muted);c.text(192,52,std::to_string(blocks.score),green,2);c.text(192,79,"LINES "+std::to_string(blocks.lines),gold);c.text(192,102,"NEXT",muted);for(int j=0;j<4;++j)for(int i=0;i<4;++i)if(Blocks::cell(blocks.next,0,i,j))c.rect(192+i*10,116+j*10,9,9,palette[blocks.next]);c.text(192,172,"UP: ROTATE");c.text(192,186,"SPACE: DROP");
        }else if(id=="merge2048"){
            c.rect(30,35,184,184,panel);for(int y=0;y<4;++y)for(int x=0;x<4;++x){int n=merge.board[y*4+x],power=0;for(int v=n;v>1;v/=2)++power;Color color=n?palette[power%7]:Color{36,53,74};c.rect(34+x*45,39+y*45,41,41,color);if(n){auto s=std::to_string(n);int z=s.size()<4?2:1;c.text(34+x*45+(41-int(s.size())*6*z)/2,55+y*45,s,{14,26,40},z);}}
            c.text(244,46,"SCORE",muted);c.text(244,61,std::to_string(merge.score),green,2);c.text(244,100,"BEST "+std::to_string(best),gold);c.text(244,140,"ARROWS: SLIDE");c.text(244,157,"U: UNDO");if(merge.maximum()>=2048)c.text(244,190,"2048! KEEP GOING",green);
        }else if(id=="breakout"){
            for(int y=0;y<Breakout::H;++y)for(int x=0;x<Breakout::W;++x)if(breakout.bricks[y*10+x]){c.rect(12+x*38,40+y*17,32,12,palette[y%7]);if(breakout.bricks[y*10+x]>1)c.border(13+x*38,41+y*17,30,10,ink);}
            c.rect(breakout.px-29,216,58,6,green);c.disc(breakout.bx,breakout.by,3,gold);c.text(12,29,"SCORE "+std::to_string(breakout.score));c.text(164,29,"LEVEL "+std::to_string(breakout.level));c.text(307,29,"LIVES "+std::to_string(breakout.lives));if(!breakout.launched&&!breakout.over&&!breakout.won)c.text(104,180,"SPACE OR CLICK TO LAUNCH",gold);
        }else if(id=="sokoban"){
            int size=24,ox=22,oy=36;
            for(int y=0;y<sokoban.height;++y)for(int x=0;x<sokoban.width;++x){int p=y*sokoban.width+x;c.rect(ox+x*size,oy+y*size,size-1,size-1,sokoban.floor[p]=='#'?Color{56,80,104}:panel);if(sokoban.floor[p]=='.')c.disc(ox+x*size+11,oy+y*size+11,5,green);}
            for(int p:sokoban.boxes){float x=ox+(p%sokoban.width)*size,y=oy+(p/sokoban.width)*size;c.rect(x+3,y+3,size-7,size-7,sokoban.floor[p]=='.'?green:gold);c.border(x+5,y+5,size-11,size-11,panel);}
            c.disc(ox+(sokoban.player%sokoban.width)*size+11,oy+(sokoban.player/sokoban.width)*size+11,7,{118,169,255});
            c.text(244,45,"LEVEL "+std::to_string(sokoban.level+1)+" / 6",green);c.text(244,77,"MOVES "+std::to_string(sokoban.moves));c.text(244,94,"PUSHES "+std::to_string(sokoban.pushes));c.text(244,135,"ARROWS: MOVE");c.text(244,151,"U: UNDO");if(sokoban.won()){c.text(244,180,"SOLVED!",gold);c.text(244,196,"N: NEXT LEVEL");}
        }else if(id=="mines"){
            for(int y=0;y<9;++y)for(int x=0;x<9;++x){int p=y*9+x,xx=16+x*20,yy=38+y*20;c.rect(xx,yy,19,19,mines.open[p]?panel:Color{61,84,108});if(mines.open[p]&&mines.mines[p])c.disc(xx+9,yy+9,5,{248,112,121});else if(mines.open[p]&&mines.around(p))c.text(xx+7,yy+6,std::to_string(mines.around(p)),palette[mines.around(p)%7]);if(mines.flag[p]){c.rect(xx+5,yy+4,2,12,ink);c.rect(xx+7,yy+4,8,6,gold);}if(p==cursor)c.border(xx,yy,19,19,green);}
            int flags=int(std::count(mines.flag.begin(),mines.flag.end(),true));c.text(223,45,"MINES "+std::to_string(10-flags),gold,2);c.text(223,79,"SAFE "+std::to_string(mines.revealed)+" / 71");c.text(223,107,"FIRST CLICK IS SAFE",green);c.text(223,133,"LEFT: REVEAL");c.text(223,148,"RIGHT / F: FLAG");c.text(223,163,"ENTER: OPEN");c.text(223,178,"DOUBLE CLICK: CHORD");
        }
        c.text(12,229,"P: PAUSE    R: RESTART    ESC: LIBRARY",muted);
        if(!started||paused||over()||(won()&&id!="sokoban")){
            c.rect(49,88,302,65,{15,27,43,240});c.border(49,88,302,65,green);
            std::string label=!started?"READY TO PLAY":paused?"PAUSED":won()?"YOU WIN!":"GAME OVER";c.text(200-int(label.size())*6,100,label,gold,2);c.text(91,132,!started?"ENTER OR CLICK TO START":paused?"P TO CONTINUE":"R TO PLAY AGAIN",ink);
        }
        c.finish();
    }
};

static void screenshot(const fs::path& path){std::vector<uint8_t> pixels(400*240*3);glPixelStorei(GL_PACK_ALIGNMENT,1);glReadPixels(0,0,400,240,GL_RGB,GL_UNSIGNED_BYTE,pixels.data());std::ofstream f(path,std::ios::binary);f<<"P6\n400 240\n255\n";for(int y=239;y>=0;--y)f.write(reinterpret_cast<char*>(pixels.data()+y*1200),1200);if(!f)throw std::runtime_error("Capture failed");}
int main(int argc,char** argv){
    try{
        std::string game="snake";double seconds=0;bool autoplay=false;fs::path capture,state;
        for(int i=1;i<argc;++i){std::string a=argv[i];auto value=[&](){if(++i>=argc)throw std::runtime_error("Missing value");return std::string(argv[i]);};if(a=="--game")game=value();else if(a=="--seconds")seconds=std::stod(value());else if(a=="--qa-autoplay")autoplay=true;else if(a=="--capture")capture=value();else if(a=="--state-dir")state=value();else throw std::runtime_error("Unknown option");}
        if(game!="snake"&&game!="blocks"&&game!="merge2048"&&game!="breakout"&&game!="sokoban"&&game!="mines")throw std::runtime_error("Unknown game");
        if(seconds<0||seconds>600)throw std::runtime_error("Invalid duration");
        std::signal(SIGTERM,onStop);std::signal(SIGINT,onStop);if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_EVENTS)!=0)throw std::runtime_error(SDL_GetError());
        SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION,1);SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION,3);SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER,1);
        SDL_Window* window=SDL_CreateWindow("RasterIX Arcade",SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,400,240,SDL_WINDOW_OPENGL|(capture.empty()?SDL_WINDOW_SHOWN:SDL_WINDOW_HIDDEN));if(!window)throw std::runtime_error(SDL_GetError());
        SDL_GLContext context=SDL_GL_CreateContext(window);if(!context)throw std::runtime_error(SDL_GetError());SDL_GL_SetSwapInterval(0);
        std::cout<<"ARCADE_RENDERER "<<glGetString(GL_VENDOR)<<" / "<<glGetString(GL_RENDERER)<<std::endl;
        Games games(game);fs::path bestFile;
        if(!state.empty()){fs::create_directories(state);if(fs::is_symlink(state))throw std::runtime_error("Refuse state symlink");bestFile=state/(game+".best");if(fs::is_symlink(bestFile))throw std::runtime_error("Refuse score symlink");std::ifstream f(bestFile);int value=0;if(f>>value&&value>=0&&value<100000000)games.best=value;}
        unsigned frames=0;using Clock=std::chrono::steady_clock;auto began=Clock::now(),previous=began,next=began;
        {Canvas canvas;while(!stopping){auto now=Clock::now();double elapsed=std::chrono::duration<double>(now-began).count();if(seconds&&elapsed>=seconds)break;float dt=std::min(.05,std::chrono::duration<double>(now-previous).count());previous=now;
            SDL_Event e;while(SDL_PollEvent(&e)){if(e.type==SDL_QUIT)stopping=1;if(e.type==SDL_KEYDOWN){if(e.key.keysym.sym==SDLK_ESCAPE)stopping=1;else games.key(e.key.keysym.sym);}if(e.type==SDL_MOUSEMOTION&&game=="breakout"){int w=400,h=240;SDL_GetWindowSize(window,&w,&h);games.breakout.px=std::clamp(e.motion.x*400.f/std::max(1,w),32.f,368.f);}if(e.type==SDL_MOUSEBUTTONDOWN){int w=400,h=240;SDL_GetWindowSize(window,&w,&h);games.click(e.button.x*400/std::max(1,w),e.button.y*240/std::max(1,h),e.button.button==SDL_BUTTON_RIGHT,e.button.clicks>1);}}
            games.update(dt,autoplay,SDL_GetKeyboardState(nullptr));games.draw(canvas);if(!capture.empty()&&seconds&&elapsed>=seconds-.10){screenshot(capture);capture.clear();}SDL_GL_SwapWindow(window);++frames;
            next+=std::chrono::microseconds(16667);auto end=Clock::now();if(next<end-std::chrono::milliseconds(50))next=end;if(next>end)std::this_thread::sleep_until(next);
        }}
        glFinish();SDL_GL_DeleteContext(context);SDL_DestroyWindow(window);SDL_Quit();
        if(!bestFile.empty()){auto tmp=bestFile;tmp+=".new-"+std::to_string(getpid());if(fs::exists(tmp)||fs::is_symlink(tmp))throw std::runtime_error("Score temporary exists");{std::ofstream f(tmp);f<<games.best<<'\n';if(!f)throw std::runtime_error("Score save failed");}fs::rename(tmp,bestFile);}
        double elapsed=std::chrono::duration<double>(Clock::now()-began).count();std::cout<<"ARCADE_RESULT {\"passed\":true,\"game\":\""<<game<<"\",\"frames\":"<<frames<<",\"seconds\":"<<elapsed<<",\"fps\":"<<frames/elapsed<<",\"updates\":"<<games.updates<<",\"actions\":"<<games.actions<<",\"score\":"<<games.score()<<",\"best\":"<<games.best<<",\"rounds\":"<<games.rounds<<",\"qa_autoplay\":"<<(autoplay?"true":"false")<<"}"<<std::endl;
        return 0;
    }catch(const std::exception& e){std::cerr<<"ARCADE_ERROR "<<e.what()<<std::endl;return 1;}
}
