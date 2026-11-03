// SPDX-License-Identifier: MIT
// Software-only SDL2 launcher. It does not open DRM, DMA or PL registers.
#include <SDL.h>
#include "ui_state.hpp"
#include "game_catalog.hpp"
#include "font_atlas.hpp"
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

namespace fs = std::filesystem;
using namespace launcher;
struct Color { Uint8 r,g,b,a=255; };
constexpr Color bg{243,245,239}, paper{255,255,251}, ink{29,46,40}, muted{82,98,87},
    dark{26,44,36}, green{197,239,139}, line{222,228,216}, pale{233,239,226}, amber{160,113,39};
struct Hit { SDL_Rect rect; std::function<void()> action; };
struct Options {
    fs::path assets, snapshot, stateDir, frameOutput, testOutput;
    std::string socket = "/run/rasterix-launcher/control.sock", selected, page;
    int width=1600,height=900;
    bool lcdInput=false;
    bool headless=false;
};
struct Backend {
    bool connected=false;
    std::string mode="offline",phase="menu",game,reason="offline",ready;
    bool canStart(const std::string& id) const {
        const auto list=","+ready+",";
        return connected && phase=="menu" && list.find(","+id+",")!=std::string::npos;
    }
};
static std::map<std::string,std::string> request(const std::string& socket,const std::string& operation) {
    if(socket.size()>=sizeof(sockaddr_un::sun_path))return {};
    int fd=::socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0);
    if(fd<0)return {};
    timeval timeout{0,500000};
    setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));
    setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
    sockaddr_un address{};address.sun_family=AF_UNIX;std::strcpy(address.sun_path,socket.c_str());
    std::map<std::string,std::string> fields;
    if(connect(fd,reinterpret_cast<sockaddr*>(&address),sizeof(address))==0){
        const std::string command=operation+"\n";
        size_t sent=0;
        while(sent<command.size()){
            ssize_t n=send(fd,command.data()+sent,command.size()-sent,MSG_NOSIGNAL);
            if(n<0&&errno==EINTR)continue;
            if(n<=0)break;
            sent+=size_t(n);
        }
        std::string reply;char bytes[1024];
        while(reply.size()<16384&&reply.find("\n.\n")==std::string::npos){
            ssize_t n=recv(fd,bytes,sizeof(bytes),0);
            if(n<0&&errno==EINTR)continue;
            if(n<=0)break;
            reply.append(bytes,size_t(n));
        }
        if(reply.find("\n.\n")!=std::string::npos){
            size_t start=0;
            while(start<reply.size()){
                auto end=reply.find('\n',start);if(end==std::string::npos)break;
                auto row=reply.substr(start,end-start);auto split=row.find('=');
                if(split!=std::string::npos)fields.emplace(row.substr(0,split),row.substr(split+1));
                start=end+1;
            }
        }
    }
    close(fd);return fields;
}
static std::string reasonText(const std::string& code) {
    if(code=="preview")return "当前为交互预览，不会启动真实游戏。";
    if(code=="pending-adapter")return "这款游戏的专用启动适配器尚未接入。";
    if(code=="requires-v23")return "请先通过现有流程加载已验收的运行配置。";
    if(code=="gpu-busy")return "另一个游戏仍在运行，请先返回游戏库。";
    if(code=="quarantined")return "检测到硬件恢复标记，请按恢复流程检查开发板。";
    if(code=="game-error")return "游戏未正常结束，请查看运行日志。";
    if(code=="missing-runtime")return "开发板运行包尚未准备好。";
    if(code=="stopping")return "正在保存并退出游戏，请稍候。";
    if(code=="starting")return "正在准备游戏，请稍候。";
    if(code=="preparing")return "正在释放菜单渲染资源，请稍候。";
    if(code=="returning")return "游戏已退出，正在恢复游戏库。";
    return "启动服务尚未连接，当前可以浏览界面与设置偏好。";
}
static void fail(bool condition,const std::string& message){if(!condition)throw std::runtime_error(message+": "+SDL_GetError());}

class UI {
    Options opt;
    State state;
    Backend backend;
    SDL_Surface* surface=nullptr;
    SDL_Surface* outputSurface=nullptr;
    SDL_Renderer* renderer=nullptr;
    SDL_Texture* font=nullptr;
    SDL_Window* window=nullptr;
    std::vector<SDL_Texture*> pictures;
    std::vector<Hit> hits;
    std::string modalTitle,modalBody,toast;
    Uint64 toastUntil=0;
    int tabFocus=-1;
    bool compact=false,dirty=true,hidden=false,quit=false,searching=false;
    int w=1600,h=900;
    int pixelW=1600,pixelH=900;
    int cursorX=0,cursorY=0;
    bool cursorVisible=false;
    float scale=1;
    uint64_t frameId=0;

    void color(Color c){SDL_SetRenderDrawColor(renderer,c.r,c.g,c.b,c.a);}
    void rect(int x,int y,int width,int height,Color c){color(c);SDL_Rect r{x,y,width,height};SDL_RenderFillRect(renderer,&r);}
    void outline(int x,int y,int width,int height,Color c){color(c);SDL_Rect r{x,y,width,height};SDL_RenderDrawRect(renderer,&r);}
    void circle(int x,int y,int radius,Color c){
        color(c);
        for(int yy=-radius;yy<=radius;++yy){int xx=int(std::sqrt(double(radius*radius-yy*yy)));SDL_Rect row{x-xx,y+yy,2*xx+1,1};SDL_RenderFillRect(renderer,&row);}
    }
    void round(int x,int y,int width,int height,int radius,Color c){
        rect(x+radius,y,width-2*radius,height,c);rect(x,y+radius,width,height-2*radius,c);
        circle(x+radius,y+radius,radius,c);circle(x+width-radius-1,y+radius,radius,c);
        circle(x+radius,y+height-radius-1,radius,c);circle(x+width-radius-1,y+height-radius-1,radius,c);
    }
    void rule(int x1,int y1,int x2,int y2,Color c){color(c);SDL_RenderDrawLine(renderer,x1,y1,x2,y2);}
    std::vector<unsigned> decode(const std::string& s) const {
        std::vector<unsigned> result;
        for(size_t i=0;i<s.size();){unsigned c=(unsigned char)s[i++];int count=0;
            if(c>=0xf0){c&=7;count=3;}else if(c>=0xe0){c&=15;count=2;}else if(c>=0xc0){c&=31;count=1;}
            while(count--&&i<s.size())c=(c<<6)|((unsigned char)s[i++]&63);
            result.push_back(c);
        }return result;
    }
    const Glyph* glyph(unsigned code,int size,bool bold) const {
        if(opt.lcdInput&&compact)size=std::max(16,size);
        const auto key=std::make_tuple(size,int(bold),code);
        auto it=std::lower_bound(kGlyphs.begin(),kGlyphs.end(),key,[](const Glyph& g,const auto& value){return std::make_tuple(g.size,g.weight,g.code)<value;});
        if(it==kGlyphs.end()||it->code!=code||it->size!=size||it->weight!=int(bold))return nullptr;
        return &*it;
    }
    int textWidth(const std::string& value,int size,bool bold=false) const {
        int width=0;for(auto c:decode(value)){auto g=glyph(c,size,bold);width+=g?g->advance:size;}return width;
    }
    void text(int x,int y,const std::string& value,int size=18,Color c=ink,bool bold=false,int maxWidth=10000){
        SDL_SetTextureColorMod(font,c.r,c.g,c.b);SDL_SetTextureAlphaMod(font,c.a);
        int start=x;
        for(auto code:decode(value)){
            auto g=glyph(code,size,bold);
            if(!g)g=glyph('?',size,bold);
            if(!g)continue;
            if(x-start+g->advance>maxWidth)break;
            SDL_Rect source{g->x,g->y,g->w,g->h},dest{x-2,y-2,g->w,g->h};
            SDL_RenderCopy(renderer,font,&source,&dest);x+=g->advance;
        }
    }
    void image(int id,SDL_Rect box,bool cover=false){
        const float ratio=400.f/240.f;
        SDL_Rect src{0,0,400,240};
        if(cover){
            float target=float(box.w)/box.h;
            if(target>ratio){src.h=int(400/target);src.y=(240-src.h)/2;}
            else {src.w=int(240*target);src.x=(400-src.w)/2;}
        }else{
            float ratio2=std::min(float(box.w)/400,float(box.h)/240);
            int width=int(400*ratio2),height=int(240*ratio2);
            box.x+=(box.w-width)/2;box.y+=(box.h-height)/2;box.w=width;box.h=height;
        }
        SDL_RenderCopy(renderer,pictures.at(id),&src,&box);
    }
    void button(SDL_Rect r,const std::string& label,std::function<void()> action,bool primary=false,bool active=false,int size=18){
        round(r.x,r.y,r.w,r.h,compact?8:10,primary?dark:active?green:pale);
        int tw=textWidth(label,size,true);
        text(r.x+(r.w-tw)/2,r.y+(r.h-size)/2-3,label,size,primary?paper:ink,true);
        hits.push_back({r,std::move(action)});
    }
    void notify(const std::string& value){toast=value;toastUntil=SDL_GetTicks64()+3000;dirty=true;}
    void modal(const std::string& title,const std::string& body){state.modal=true;modalTitle=title;modalBody=body;tabFocus=-1;dirty=true;}
    void readPreferences(){
        fs::path path=opt.stateDir/"preferences.conf";
        if(fs::is_symlink(path))throw std::runtime_error("Refuse preference symlink");
        std::ifstream file(path);std::string row;
        while(std::getline(file,row)){
            if(row.rfind("output=",0)==0&&allowedOutput(row.substr(7)))state.preferences.output=row.substr(7);
            if(row.rfind("aspect=",0)==0&&allowedAspect(row.substr(7)))state.preferences.aspect=row.substr(7);
            if(row=="fsr=0"||row=="fsr=1")state.preferences.fsr=row=="fsr=1";
            for(const auto& game:kGames){
                if(row=="favorite="+std::string(game.id))state.favorites.insert(game.id);
                if(row=="recent="+std::string(game.id)&&state.recent.size()<8&&std::find(state.recent.begin(),state.recent.end(),game.id)==state.recent.end())state.recent.push_back(game.id);
            }
        }
    }
    void savePreferences(bool announce=true){
        fs::create_directories(opt.stateDir);
        if(fs::is_symlink(opt.stateDir))throw std::runtime_error("Refuse preference directory symlink");
        fs::path path=opt.stateDir/"preferences.conf",pending=opt.stateDir/("preferences."+std::to_string(getpid())+".new");
        int fd=open(pending.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
        if(fd<0)throw std::runtime_error("Cannot create preference file");
        std::string value="output="+state.preferences.output+"\naspect="+state.preferences.aspect+"\nfsr="+(state.preferences.fsr?"1":"0")+"\n";
        for(const auto& id:state.favorites)value+="favorite="+id+"\n";
        for(const auto& id:state.recent)value+="recent="+id+"\n";
        size_t offset=0;
        while(offset<value.size()){ssize_t n=write(fd,value.data()+offset,value.size()-offset);if(n<0&&errno==EINTR)continue;if(n<=0){close(fd);throw std::runtime_error("Preference write failed");}offset+=n;}
        if(fsync(fd)){close(fd);throw std::runtime_error("Preference sync failed");}close(fd);
        if(rename(pending.c_str(),path.c_str()))throw std::runtime_error("Preference commit failed");
        if(announce)notify("偏好已保存，实际输出由显示服务应用。");
    }
    void poll(){
        auto fields=request(opt.socket,"STATUS");
        Backend next;
        if(fields["ok"]=="1"){
            next.connected=true;next.mode=fields["mode"];next.phase=fields["phase"];
            next.game=fields["game"];next.reason=fields["reason"];next.ready=fields["ready"];
        }
        if(next.mode!=backend.mode||next.phase!=backend.phase||next.ready!=backend.ready||next.reason!=backend.reason)dirty=true;
        backend=std::move(next);
        bool shouldHide=backend.mode=="board"&&(backend.phase=="running"||backend.phase=="starting"||backend.phase=="preparing"||backend.phase=="stopping");
        if(window&&shouldHide!=hidden){hidden=shouldHide;if(hidden)SDL_HideWindow(window);else{SDL_ShowWindow(window);SDL_RaiseWindow(window);SDL_SetWindowInputFocus(window);}dirty=true;}
    }
    void start(){
        // Return can complete between periodic polls; use current service
        // state for a user action rather than blocking on a stale cache.
        poll();
        if(state.visible(kGames).empty()){notify("没有匹配的游戏，请调整搜索或分类。");return;}
        const auto& game=kGames.at(state.selected);
        if(std::string(game.adapter)=="pending"){modal("专用入口正在接入",reasonText("pending-adapter"));return;}
        if(!backend.connected){modal("界面预览",reasonText("offline"));return;}
        if(!backend.canStart(game.id)){
            if(backend.phase=="returning"||backend.phase=="preparing"||backend.phase=="starting"||backend.phase=="stopping")notify(reasonText(backend.reason));
            else modal("暂时无法启动",reasonText(backend.reason));return;
        }
        auto reply=request(opt.socket,"START "+std::string(game.id)+(state.preferences.fsr?" fsr":""));
        if(reply["ok"]!="1"){modal("暂时无法启动",reasonText(reply["reason"]));return;}
        if(backend.mode=="board"){
            state.recent.erase(std::remove(state.recent.begin(),state.recent.end(),game.id),state.recent.end());state.recent.insert(state.recent.begin(),game.id);if(state.recent.size()>8)state.recent.resize(8);savePreferences(false);
        }
        poll();
        if(backend.mode=="preview")modal("启动流程预览",reasonText("preview"));
        dirty=true;
    }
    void stop(){request(opt.socket,"STOP");state.modal=false;poll();dirty=true;}
    void icon(int x,int y,int kind,Color c){
        if(kind==0){for(int a=0;a<2;++a)for(int b=0;b<2;++b)round(x+a*11,y+b*11,8,8,2,c);}
        if(kind==1){outline(x,y,23,16,c);rule(x+11,y+17,x+11,y+21,c);rule(x+5,y+21,x+18,y+21,c);}
        if(kind==2){outline(x,y+1,23,18,c);rule(x+5,y+7,x+18,y+7,c);rule(x+5,y+12,x+13,y+12,c);}
    }
    void sidebar(){
        int sw=compact?68:208;rect(0,0,sw,h,dark);
        round(compact?17:25,compact?20:30,36,36,10,green);text(compact?27:35,compact?22:32,"R",24,dark,true);
        if(!compact){text(73,28,"RasterIX",24,paper,true);text(74,60,"PLAY STATION",12,{143,167,147});}
        const std::array<std::string,3> labels={"游戏库","显示偏好","操作指南"};
        for(int i=0;i<3;++i){int yy=(compact?110:157)+i*(compact?60:64);bool active=int(state.page)==i;
            if(active)round(compact?10:16,yy-11,compact?48:176,48,10,green);
            icon(compact?22:30,yy+2,i,active?dark:Color{166,185,167});
            if(!compact)text(66,yy-2,labels[i],18,active?dark:Color{184,199,184},active);
            hits.push_back({{compact?10:16,yy-11,compact?48:176,48},[this,i]{state.page=Page(i);tabFocus=-1;dirty=true;}});
        }
        if(!compact){rule(25,h-118,182,h-118,{63,81,66});circle(33,h-84,3,green);text(45,h-95,"AXU3EG",16,{219,229,211},true);text(25,h-56,"本地游戏 · 键鼠操作",12,{143,167,147});}
        else{text(17,h-40,"FPGA",12,{143,167,147},true);}
    }
    void header(const std::string& title,const std::string& subtitle){
        const int x=compact?92:248;
        if(!compact){text(x,27,"RASTERIX  /  游戏工作台",14,muted,true);text(x,65,title,36,ink,true);text(x,116,subtitle,16,muted);}
        else{text(x,15,title,24,ink,true);}
        const std::string status=backend.mode=="board"?"开发板控制服务":backend.mode=="preview"?"交互预览服务":"本地界面预览";
        int sx=w-(compact?151:209),sy=compact?21:36;
        circle(sx,sy+8,3,backend.mode=="board"?Color{73,132,72}:amber);
        text(sx+10,sy-3,status,compact?12:14,muted);
    }
    void library(){
        const auto& game=kGames.at(state.selected);
        header("玩点什么？",std::to_string(kGames.size())+" 款游戏 · 收藏、搜索、分页浏览 · 一次运行一款");
        int x=compact?92:248,ww=w-x-(compact?24:40),yy=compact?63:158,hh=compact?136:254;
        round(x,yy,ww,hh,compact?12:18,paper);
        int picw=compact?190:520;
        SDL_Rect pic{x+ww-picw-(compact?10:15),yy+(compact?12:14),picw,hh-(compact?24:28)};
        round(pic.x,pic.y,pic.w,pic.h,12,pale);image(state.selected,pic);
        int tx=x+(compact?16:28),tw=ww-picw-(compact?35:90);
        text(tx,yy+(compact?10:18),game.genre,compact?12:14,muted,true);
        text(tx,yy+(compact?30:49),game.title,compact?24:44,ink,true,tw);
        if(!compact){text(tx,yy+112,game.description,18,muted,false,tw);text(tx,yy+145,game.controls,14,muted,false,tw);}
        else{text(tx,yy+67,game.controls,12,muted,false,tw);}
        button({tx,yy+hh-(compact?43:65),compact?122:170,compact?31:44},std::string(game.adapter)=="pending"?"查看接入状态":"开始游戏",[this]{start();},true,false,compact?14:18);
        button({tx+(compact?136:188),yy+hh-(compact?43:65),compact?145:190,compact?31:44},
            state.preferences.fsr?"FPGA FSR：开":"FPGA FSR：关",[this]{state.preferences.fsr=!state.preferences.fsr;savePreferences();
                notify(state.preferences.fsr?"下次启动使用 FPGA FSR 超分。":"下次启动使用原始放大。 ");},false,state.preferences.fsr,compact?14:18);
        button({tx+(compact?294:395),yy+hh-(compact?43:65),compact?64:100,compact?31:44},state.favorites.count(game.id)?"已收藏":"收藏",[this]{const auto id=std::string(kGames[state.selected].id);if(state.favorites.count(id))state.favorites.erase(id);else state.favorites.insert(id);state.normalize(kGames);savePreferences(false);dirty=true;},false,state.favorites.count(game.id)!=0,compact?12:16);
        button({w-(compact?460:700),compact?14:66,compact?285:400,compact?28:39},searching?"输入关键词，Enter 确认":state.query.empty()?"搜索游戏 /":"搜索："+state.query,[this]{searching=true;SDL_StartTextInput();dirty=true;},false,searching,compact?12:16);
        if(!compact){round(pic.x+8,pic.y+pic.h-31,186,25,5,{29,46,40,225});text(pic.x+17,pic.y+pic.h-29,"游戏画面 · 非实时",12,paper);}
        const int sy=yy+hh+(compact?14:27);
        text(x,sy,compact?"游戏库":"全部游戏",compact?16:20,ink,true);
        const std::array<std::string,5> filters={"全部","休闲益智","射击弹幕","方块世界","收藏"};
        int fx=x+(compact?89:168);
        for(int i=0;i<5;++i){int bw=compact?(i==4?52:i?83:48):(i?106:65);
            button({fx,sy-(compact?0:2),bw,compact?27:32},filters[i],[this,i]{state.setFilter(Filter(i),kGames);tabFocus=-1;dirty=true;},false,int(state.filter)==i,compact?12:14);fx+=bw+(compact?5:8);
        }
        const int gap=compact?10:18,cardW=(ww-3*gap)/4,cardH=compact?94:163,startY=sy+(compact?40:49);
        const auto ids=state.visible(kGames);
        const int page=state.pageIndex(kGames),pages=std::max(1,int((ids.size()+7)/8));
        button({x+ww-(compact?171:232),sy,compact?48:60,compact?27:32},"上页",[this]{state.turnPage(-1,kGames);tabFocus=-1;dirty=true;},false,false,compact?12:14);
        text(x+ww-(compact?112:150),sy+7,std::to_string(page+1)+" / "+std::to_string(pages),compact?12:14,muted);
        button({x+ww-(compact?48:60),sy,compact?48:60,compact?27:32},"下页",[this]{state.turnPage(1,kGames);tabFocus=-1;dirty=true;},false,false,compact?12:14);
        const unsigned begin=unsigned(page*8),end=std::min(unsigned(ids.size()),begin+8);
        for(unsigned index=begin;index<end;++index){unsigned pos=index-begin;int id=ids[index],cx=x+(pos%4)*(cardW+gap),cy=startY+(pos/4)*(cardH+(compact?10:15));
            const bool selected=id==state.selected;
            if(selected)round(cx-2,cy-2,cardW+4,cardH+4,compact?10:15,dark);
            round(cx,cy,cardW,cardH,compact?8:13,paper);
            int ih=compact?48:96;
            image(id,{cx+(compact?5:7),cy+(compact?5:7),cardW-(compact?10:14),ih},true);
            text(cx+(compact?7:12),cy+ih+(compact?8:12),kGames[id].title,compact?12:18,ink,true,cardW-17);
            text(cx+(compact?7:12),cy+ih+(compact?25:38),kGames[id].genre,12,muted);
            bool pending=std::string(kGames[id].adapter)=="pending";
            if(!compact){const std::string label=pending?"待接入":backend.mode=="board"&&!backend.canStart(kGames[id].id)?"未就绪":"可启动";text(cx+cardW-69,cy+ih+38,label,12,pending?amber:muted);}
            if(selected){int bx=cx+cardW-(compact?24:31),by=cy+11,bs=compact?16:21;round(bx,by,bs,bs,5,green);rule(bx+4,by+bs/2,bx+bs/2-1,by+bs-5,dark);rule(bx+bs/2-1,by+bs-5,bx+bs-4,by+5,dark);}
            hits.push_back({{cx,cy,cardW,cardH},[this,id]{state.selected=id;dirty=true;}});
        }
        if(ids.empty())text(x,startY+30,"没有匹配的游戏。按 / 搜索，清空关键词后重试。",compact?14:16,muted);
        else if(ids.size()<5)text(x,startY+cardH+28,"方向键选择，Enter 启动。PgUp / PgDn 翻页。",compact?14:16,muted);
    }
    void choice(SDL_Rect box,const std::string& title,const std::string& description,bool selected,std::function<void()> action){
        round(box.x,box.y,box.w,box.h,12,selected?dark:line);
        round(box.x+2,box.y+2,box.w-4,box.h-4,10,selected?Color{237,245,224}:paper);
        circle(box.x+22,box.y+25,8,selected?dark:line);if(selected)circle(box.x+22,box.y+25,3,green);
        text(box.x+40,box.y+10,title,compact?16:20,ink,true,box.w-50);
        if(!compact)text(box.x+20,box.y+56,description,14,muted,false,box.w-35);
        hits.push_back({box,std::move(action)});
    }
    void display(){
        header("把画面，放到大屏幕。","设置输出偏好。真实模式与连接状态由后续显示服务确认。");
        const int x=compact?92:248,ww=w-x-(compact?24:40),y=compact?68:173;
        round(x,y,ww,compact?104:165,16,paper);
        icon(x+23,y+23,1,ink);text(x+62,y+12,"miniDP / DisplayPort",compact?18:24,ink,true);
        text(x+23,y+(compact?48:67),"1920 × 1080  ·  60 Hz",compact?20:28,ink,true);
        text(x+23,y+(compact?79:120),"目标模式 · 当前未应用到物理显示器",compact?12:16,amber);
        int yy=y+(compact?123:200),bw=(ww-18)/2;
        text(x,yy,"输出设备",compact?16:20,ink,true);yy+=compact?32:43;
        choice({x,yy,bw,compact?49:102},"外接显示器","通过 PS DisplayPort 显示游戏画面。",state.preferences.output=="dp",[this]{state.preferences.output="dp";dirty=true;});
        choice({x+bw+18,yy,bw,compact?49:102},"RGB LCD","保留 800×480 本地屏幕。",state.preferences.output=="lcd",[this]{state.preferences.output="lcd";dirty=true;});
        yy+=compact?67:139;text(x,yy,"画面比例",compact?16:20,ink,true);yy+=compact?31:43;
        choice({x,yy,bw,compact?49:102},"保持比例","400×240 → 1800×1080，左右各留 60 像素。",state.preferences.aspect=="fit",[this]{state.preferences.aspect="fit";dirty=true;});
        choice({x+bw+18,yy,bw,compact?49:102},"整数放大","400×240 → 1600×960，适合像素风画面。",state.preferences.aspect=="integer",[this]{state.preferences.aspect="integer";dirty=true;});
        yy+=compact?65:136;button({x,yy,compact?128:170,compact?34:45},"保存显示偏好",[this]{savePreferences();},true,false,compact?14:18);
        if(!compact)text(x+192,yy+10,"60 Hz 是显示刷新率，游戏帧率单独统计。",16,muted);
    }
    void help(){
        header("随时开始，轻松返回。","方向键、鼠标都可以操作。每款游戏保留自己的控制方式。");
        int x=compact?92:248,y=compact?70:178,ww=w-x-(compact?24:40);
        const std::array<std::pair<std::string,std::string>,5> rows={{{"↑ ↓ ← →","在游戏库中选择游戏"},{"ENTER","启动所选游戏"},{"TAB / SHIFT+TAB","切换可操作控件"},{"ESC","关闭提示或返回游戏库"},{"CTRL + ALT + M","请求正常退出并返回总菜单"}}};
        round(x,y,ww,compact?292:410,15,paper);
        for(unsigned i=0;i<rows.size();++i){int yy=y+(compact?14:23)+i*(compact?51:69);
            round(x+18,yy,compact?160:235,compact?32:42,8,pale);text(x+28,yy+4,rows[i].first,compact?12:16,ink,true);
            text(x+(compact?196:294),yy+5,rows[i].second,compact?14:20,ink);
        }
        text(x,y+(compact?310:444),"游戏自己的 Esc 菜单仍然保留，退出会先尝试保存与正常关闭。",compact?12:16,muted,false,ww);
        text(x,y+(compact?336:483),"CTRL + ALT + M 请求正常退出并返回总菜单。",compact?12:14,muted);
    }
    void footer(){
        int x=compact?92:248;rule(x,h-(compact?29:45),w-(compact?24:40),h-(compact?29:45),line);
        text(x,h-(compact?24:34),compact?"方向键选择  ·  Enter 启动  ·  Esc 返回":"↑ ↓ ← → 选择    Enter 启动    Tab 切换控件    Esc 返回",compact?12:14,muted);
        if(!compact){std::string value=state.preferences.output=="dp"?"目标输出 1080p / 60 Hz":"目标输出 RGB LCD";text(w-268,h-34,value,14,muted);}
    }
    void modalLayer(){
        SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_BLEND);rect(0,0,w,h,{20,33,27,160});
        int mw=compact?560:650,mh=compact?200:255,mx=(w-mw)/2,my=(h-mh)/2;
        round(mx,my,mw,mh,18,paper);text(mx+28,my+24,modalTitle,compact?24:28,ink,true);
        text(mx+28,my+(compact?75:91),modalBody,compact?14:18,muted,false,mw-56);
        // Modal controls exclusively receive mouse/Tab actions.
        hits.clear();button({mx+28,my+mh-64,mw-56,40},"返回游戏库",[this]{if(backend.phase=="preview")stop();else{state.modal=false;dirty=true;}},true,false,16);
    }
    void publishFrame(){
        if(opt.frameOutput.empty())return;
        SDL_Surface* rgb=SDL_ConvertSurfaceFormat(outputSurface,SDL_PIXELFORMAT_RGB565,0);fail(rgb,"RGB565 conversion failed");
        fs::path pending=opt.frameOutput;pending+=".new";
        std::ofstream file(pending,std::ios::binary|std::ios::trunc);
        if(!file){SDL_FreeSurface(rgb);throw std::runtime_error("Cannot publish UI frame");}
        for(int y=0;y<rgb->h;++y)file.write(static_cast<char*>(rgb->pixels)+y*rgb->pitch,rgb->w*2);
        file.close();SDL_FreeSurface(rgb);fs::rename(pending,opt.frameOutput);
        auto metadata=opt.frameOutput;metadata+=".json";pending=metadata;pending+=".new";
        std::ofstream meta(pending);meta<<"{\"source\":\"launcher-ui\",\"frame_id\":"<<++frameId<<",\"width\":"<<pixelW<<",\"height\":"<<pixelH<<",\"stride\":"<<pixelW*2<<",\"format\":\"RGB565\",\"display_applied\":false}\n";meta.close();fs::rename(pending,metadata);
    }
    void createSurface(int width,int height){
        if(renderer){SDL_DestroyTexture(font);for(auto p:pictures)SDL_DestroyTexture(p);pictures.clear();SDL_DestroyRenderer(renderer);SDL_FreeSurface(surface);SDL_FreeSurface(outputSurface);}
        compact=width<1100;w=compact?800:1600;h=compact?480:900;pixelW=width;pixelH=height;
        surface=SDL_CreateRGBSurfaceWithFormat(0,w,h,32,SDL_PIXELFORMAT_ARGB8888);fail(surface,"Cannot allocate UI surface");
        outputSurface=SDL_CreateRGBSurfaceWithFormat(0,width,height,32,SDL_PIXELFORMAT_ARGB8888);fail(outputSurface,"Cannot allocate output surface");
        renderer=SDL_CreateSoftwareRenderer(surface);fail(renderer,"Cannot create software renderer");
        SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_BLEND);
        SDL_RenderSetLogicalSize(renderer,w,h);scale=std::min(float(width)/w,float(height)/h);
        font=SDL_CreateTexture(renderer,SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_STATIC,kAtlasWidth,kAtlasHeight);fail(font,"Cannot create font atlas");
        std::ifstream file(opt.assets/"font.rgba",std::ios::binary);std::vector<char> bytes(size_t(kAtlasWidth)*kAtlasHeight*4);
        file.read(bytes.data(),bytes.size());fail(bool(file)&&file.peek()==EOF,"Font atlas size mismatch");
        fail(SDL_UpdateTexture(font,nullptr,bytes.data(),kAtlasWidth*4)==0,"Cannot upload font atlas");SDL_SetTextureBlendMode(font,SDL_BLENDMODE_BLEND);
        for(const auto& game:kGames){auto image=SDL_LoadBMP((opt.assets/(std::string(game.id)+".bmp")).c_str());fail(image,"Cannot load preview image");auto tex=SDL_CreateTextureFromSurface(renderer,image);SDL_FreeSurface(image);fail(tex,"Cannot create preview texture");pictures.push_back(tex);}
        dirty=true;
    }
    void draw(){
        hits.clear();color(bg);SDL_RenderClear(renderer);sidebar();
        if(state.page==Page::Library)library();else if(state.page==Page::Display)display();else help();footer();
        if(state.modal)modalLayer();
        if(tabFocus>=0&&tabFocus<int(hits.size())){const auto& r=hits[tabFocus].rect;outline(r.x-4,r.y-4,r.w+8,r.h+8,{83,144,81});}
        if(opt.lcdInput&&cursorVisible){
            for(int row=0;row<18;++row){int width=row<12?row+1:5;rect(cursorX,cursorY+row,width,1,paper);}
            rule(cursorX,cursorY,cursorX,cursorY+17,ink);rule(cursorX,cursorY,cursorX+12,cursorY+12,ink);
        }
        if(!toast.empty()&&SDL_GetTicks64()<toastUntil){int width=std::min(w-120,textWidth(toast,compact?14:16)+36);round((w-width)/2,h-(compact?80:100),width,42,10,dark);text((w-width)/2+18,h-(compact?72:93),toast,compact?14:16,paper);}
        SDL_RenderPresent(renderer);
        SDL_FillRect(outputSurface,nullptr,SDL_MapRGB(outputSurface->format,bg.r,bg.g,bg.b));
        SDL_Rect outputRect{int((pixelW-w*scale)/2),int((pixelH-h*scale)/2),int(w*scale),int(h*scale)};
        if(pixelW==w&&pixelH==h)fail(SDL_BlitSurface(surface,nullptr,outputSurface,&outputRect)==0,"Cannot copy native UI output");
        else fail(SDL_SoftStretchLinear(surface,nullptr,outputSurface,&outputRect)==0,"Cannot scale UI output");
        publishFrame();
        if(window&&!hidden){auto target=SDL_GetWindowSurface(window);SDL_BlitScaled(outputSurface,nullptr,target,nullptr);SDL_UpdateWindowSurface(window);}
        dirty=false;
    }
    SDL_Point inputPoint(int x,int y) const {
        int width=opt.lcdInput?400:pixelW,height=opt.lcdInput?240:pixelH;
        if(window)SDL_GetWindowSize(window,&width,&height);
        float ox=(pixelW-w*scale)/2,oy=(pixelH-h*scale)/2;
        return {int((float(x)*pixelW/std::max(1,width)-ox)/scale),int((float(y)*pixelH/std::max(1,height)-oy)/scale)};
    }
    void handle(const SDL_Event& e){
        if(e.type==SDL_QUIT){quit=true;return;}
        if(e.type==SDL_TEXTINPUT&&searching){if(state.query.size()+std::strlen(e.text.text)<=80)state.query+=e.text.text;state.normalize(kGames);dirty=true;return;}
        if(e.type==SDL_WINDOWEVENT&&e.window.event==SDL_WINDOWEVENT_SIZE_CHANGED&&!opt.lcdInput){createSurface(e.window.data1,e.window.data2);tabFocus=-1;return;}
        if(e.type==SDL_KEYDOWN){
            if(cursorVisible){cursorVisible=false;dirty=true;}
            auto key=e.key.keysym.sym;
            if((e.key.keysym.mod&KMOD_CTRL)&&(e.key.keysym.mod&KMOD_ALT)&&key==SDLK_m){stop();return;}
            if(searching){
                if(key==SDLK_RETURN||key==SDLK_ESCAPE){searching=false;SDL_StopTextInput();}
                if(key==SDLK_BACKSPACE&&!state.query.empty()){while(!state.query.empty()&&(static_cast<unsigned char>(state.query.back())&0xc0)==0x80)state.query.pop_back();if(!state.query.empty())state.query.pop_back();state.normalize(kGames);}
                dirty=true;return;
            }
            if(key==SDLK_SLASH&&state.page==Page::Library&&!state.modal){searching=true;SDL_StartTextInput();dirty=true;return;}
            if(key==SDLK_TAB){if(!hits.empty()){int delta=(e.key.keysym.mod&KMOD_SHIFT)?-1:1;tabFocus=(tabFocus+delta+int(hits.size()))%int(hits.size());}dirty=true;return;}
            if(key==SDLK_ESCAPE){if(state.modal){if(backend.phase=="preview")stop();else state.modal=false;}else state.page=Page::Library;tabFocus=-1;dirty=true;return;}
            if(key==SDLK_RETURN||key==SDLK_SPACE){if(tabFocus>=0&&tabFocus<int(hits.size()))hits[tabFocus].action();else if(state.modal){if(backend.phase=="preview")stop();else{state.modal=false;dirty=true;}}else if(state.page==Page::Library)start();return;}
            if(!state.modal&&state.page==Page::Library){
                if(key==SDLK_LEFT)state.move(-1,0,kGames);
                if(key==SDLK_RIGHT)state.move(1,0,kGames);
                if(key==SDLK_UP)state.move(0,-1,kGames);
                if(key==SDLK_DOWN)state.move(0,1,kGames);
                const auto ids=state.visible(kGames);
                if(key==SDLK_HOME&&!ids.empty())state.selected=ids.front();
                if(key==SDLK_END&&!ids.empty())state.selected=ids.back();
                if(key==SDLK_PAGEUP)state.turnPage(-1,kGames);
                if(key==SDLK_PAGEDOWN)state.turnPage(1,kGames);
                tabFocus=-1;dirty=true;
            }
        }
        if(e.type==SDL_MOUSEWHEEL&&state.page==Page::Library&&!state.modal&&!searching){state.turnPage(e.wheel.y>0?-1:1,kGames);tabFocus=-1;dirty=true;}
        if(e.type==SDL_MOUSEMOTION&&opt.lcdInput){
            auto p=inputPoint(e.motion.x,e.motion.y);cursorX=std::clamp(p.x,0,w-1);cursorY=std::clamp(p.y,0,h-1);cursorVisible=true;dirty=true;
        }
        if(e.type==SDL_MOUSEBUTTONDOWN&&e.button.button==SDL_BUTTON_LEFT){
            SDL_Point p=inputPoint(e.button.x,e.button.y);
            for(auto it=hits.rbegin();it!=hits.rend();++it)if(SDL_PointInRect(&p,&it->rect)){auto action=it->action;action();tabFocus=-1;break;}
        }
    }
public:
    explicit UI(Options options):opt(std::move(options)){
        if(opt.headless)SDL_setenv("SDL_VIDEODRIVER","dummy",1);
        fail(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_EVENTS)==0,"SDL initialization failed");
        SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY,"1");
        if(!opt.headless){window=SDL_CreateWindow("RasterIX · 游戏库",SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,opt.lcdInput?400:opt.width,opt.lcdInput?240:opt.height,opt.lcdInput?(SDL_WINDOW_BORDERLESS|SDL_WINDOW_FULLSCREEN_DESKTOP):SDL_WINDOW_RESIZABLE);fail(window,"Cannot create window");}
        if(!opt.selected.empty()){auto it=std::find_if(kGames.begin(),kGames.end(),[this](const Game& g){return opt.selected==g.id;});if(it==kGames.end())throw std::runtime_error("Unknown selected game");state.selected=int(it-kGames.begin());}
        if(opt.page=="display")state.page=Page::Display;else if(opt.page=="help")state.page=Page::Help;
        readPreferences();createSurface(opt.width,opt.height);poll();
    }
    ~UI(){if(renderer){SDL_DestroyTexture(font);for(auto p:pictures)SDL_DestroyTexture(p);SDL_DestroyRenderer(renderer);}if(surface)SDL_FreeSurface(surface);if(outputSurface)SDL_FreeSurface(outputSurface);if(window)SDL_DestroyWindow(window);SDL_Quit();}
    void testInteractions(){
        if(backend.mode=="board")throw std::runtime_error("UI self-check must not connect to board control");
        std::vector<std::string> checks;
        auto check=[&](bool passed,const std::string& label){if(!passed)throw std::runtime_error("UI interaction check failed: "+label);checks.push_back(label);};
        auto key=[&](SDL_Keycode code){SDL_Event event{};event.type=SDL_KEYDOWN;event.key.keysym.sym=code;handle(event);draw();};
        auto click=[&](SDL_Rect r){SDL_Event event{};event.type=SDL_MOUSEBUTTONDOWN;event.button.button=SDL_BUTTON_LEFT;
            event.button.x=int((pixelW-w*scale)/2+(r.x+r.w/2)*scale);
            event.button.y=int((pixelH-h*scale)/2+(r.y+r.h/2)*scale);
            int iw=opt.lcdInput?400:pixelW,ih=opt.lcdInput?240:pixelH;if(window)SDL_GetWindowSize(window,&iw,&ih);
            event.button.x=int(float(event.button.x)*iw/pixelW);event.button.y=int(float(event.button.y)*ih/pixelH);handle(event);draw();};
        state.page=Page::Library;state.filter=Filter::All;state.selected=0;draw();
        click(hits.at(4).rect);check(state.preferences.fsr,"fsr-enable-is-launch-preference");
        click(hits.at(4).rect);check(!state.preferences.fsr,"fsr-disable-is-launch-preference");
        key(SDLK_RIGHT);key(SDLK_DOWN);check(state.selected==5,"keyboard-grid-navigation");
        if(backend.mode=="preview"){
            state.selected=0;draw();backend.phase="returning";key(SDLK_RETURN);
            check(state.modal&&backend.phase=="preview","preview-launch-uses-control-service");
            key(SDLK_ESCAPE);check(!state.modal&&backend.phase=="menu","preview-return-stops-session");
        }
        click(hits.back().rect);check(state.selected==7,"mouse-card-selection");
        key(SDLK_RETURN);check(state.modal&&hits.size()==1,"launch-modal-exclusive-focus");
        click({10,100,40,40});check(state.modal&&state.page==Page::Library,"modal-blocks-background-clicks");
        key(SDLK_ESCAPE);check(!state.modal,"escape-dismisses-modal");
        state.setFilter(Filter::Voxel,kGames);state.selected=6;draw();key(SDLK_RIGHT);
        check(state.selected==7&&state.visible(kGames).size()==2,"filtered-grid-navigation");
        key(SDLK_TAB);check(tabFocus==0,"tab-focus");key(SDLK_RETURN);check(state.page==Page::Library,"focused-control-activation");
        state.filter=Filter::All;state.selected=0;tabFocus=-1;draw();key(SDLK_PAGEDOWN);
        check(state.selected==8&&state.pageIndex(kGames)==1,"page-down-reaches-expansion-games");key(SDLK_PAGEUP);check(state.selected==0,"page-up-restores-first-page");
        key(SDLK_SLASH);SDL_Event input{};input.type=SDL_TEXTINPUT;std::strcpy(input.text.text,"arcade");handle(input);draw();key(SDLK_RETURN);
        check(!searching&&state.visible(kGames).size()==6,"search-finds-six-native-games");
        state.query.clear();state.selected=0;draw();click(hits.at(5).rect);check(state.favorites.count("tuxracer")!=0,"favorite-button-updates-library");
        state.setFilter(Filter::Favorites,kGames);draw();check(state.visible(kGames)==std::vector<int>({0}),"favorite-filter");
        state.favorites.clear();readPreferences();check(state.favorites.count("tuxracer")!=0,"favorite-persists-with-preferences");
        state.favorites.clear();state.filter=Filter::All;state.query.clear();state.selected=0;savePreferences(false);
        state.page=Page::Display;state.preferences={"dp","fit"};tabFocus=-1;draw();
        click(hits.at(4).rect);click(hits.at(6).rect);
        check(state.preferences==Preferences{"lcd","integer"},"mouse-display-preferences");
        click(hits.back().rect);check(fs::exists(opt.stateDir/"preferences.conf"),"atomic-preference-save");
        state.preferences={"dp","fit"};readPreferences();check(state.preferences==Preferences{"lcd","integer"},"preference-readback");
        state.page=Page::Help;draw();key(SDLK_ESCAPE);check(state.page==Page::Library,"escape-returns-library");
        state.filter=Filter::All;state.selected=0;state.preferences={"dp","fit"};tabFocus=-1;toast.clear();draw();
        std::ofstream result(opt.testOutput);result<<"{\"passed\":true,\"width\":"<<pixelW<<",\"height\":"<<pixelH<<",\"hardware_access\":false,\"checks\":[";
        for(unsigned i=0;i<checks.size();++i)result<<(i?",":"")<<"\""<<checks[i]<<"\"";
        result<<"]}\n";result.close();std::cout<<"LAUNCHER_INTERACTIONS_PASS "<<checks.size()<<"\n";
    }
    int run(){
        draw();
        if(!opt.testOutput.empty())testInteractions();
        if(!opt.snapshot.empty()){fail(SDL_SaveBMP(outputSurface,opt.snapshot.c_str())==0,"Cannot save UI snapshot");std::cout<<"LAUNCHER_SNAPSHOT "<<opt.snapshot<<" "<<pixelW<<"x"<<pixelH<<"\n";return 0;}
        Uint64 nextPoll=SDL_GetTicks64()+1000;
        while(!quit){SDL_Event e;if(SDL_WaitEventTimeout(&e,80)){handle(e);while(SDL_PollEvent(&e))handle(e);}
            if(SDL_GetTicks64()>=nextPoll){poll();nextPoll=SDL_GetTicks64()+1000;}
            if(!toast.empty()&&SDL_GetTicks64()>=toastUntil){toast.clear();dirty=true;}
            if(dirty&&!hidden)draw();
        }return 0;
    }
};
int main(int argc,char** argv){
    try{
        Options options;auto executable=fs::canonical("/proc/self/exe");options.assets=executable.parent_path()/"assets";options.stateDir=executable.parent_path()/"ui-state";
        for(int i=1;i<argc;++i){std::string arg=argv[i];auto value=[&](){if(++i>=argc)throw std::runtime_error("Missing option value");return std::string(argv[i]);};
            if(arg=="--assets")options.assets=value();else if(arg=="--state-dir")options.stateDir=value();else if(arg=="--socket")options.socket=value();
            else if(arg=="--snapshot")options.snapshot=value();else if(arg=="--frame-output")options.frameOutput=value();
            else if(arg=="--test-ui")options.testOutput=value();
            else if(arg=="--selected")options.selected=value();else if(arg=="--page")options.page=value();
            else if(arg=="--headless")options.headless=true;
            else if(arg=="--input-size"){if(value()!="400x240")throw std::runtime_error("Supported input size is 400x240");options.lcdInput=true;}
            else if(arg=="--size"){auto size=value();auto split=size.find('x');if(split==std::string::npos)throw std::runtime_error("Expected WIDTHxHEIGHT");options.width=std::stoi(size.substr(0,split));options.height=std::stoi(size.substr(split+1));}
            else if(arg=="--help"){std::cout<<"rix-launcher [--size 1920x1080] [--assets DIR] [--socket PATH] [--state-dir DIR] [--headless --snapshot FILE.bmp] [--selected GAME] [--page display|help] [--frame-output FILE] [--size 800x480 --input-size 400x240]\n";return 0;}
            else throw std::runtime_error("Unknown option: "+arg);
        }
        if(options.width<640||options.height<360||options.width>3840||options.height>2160)throw std::runtime_error("Invalid UI dimensions");
        if(options.lcdInput&&(options.width!=800||options.height!=480))throw std::runtime_error("400x240 input requires 800x480 UI output");
        if(options.page!=""&&options.page!="display"&&options.page!="help")throw std::runtime_error("Invalid page");
        if(options.headless&&options.snapshot.empty())throw std::runtime_error("Headless mode requires a snapshot output");
        UI app(options);return app.run();
    }catch(const std::exception& e){std::cerr<<"LAUNCHER_ERROR "<<e.what()<<"\n";return 1;}
}
