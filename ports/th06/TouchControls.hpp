// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <linux/input.h>

namespace th06touch {
enum Button : uint16_t {Shoot=1,Bomb=2,Focus=4,Menu=8,Up=16,Down=32,Left=64,Right=128};
class Controls {
    struct Contact {int x=0,y=0;bool down=false,fresh=false;int anchorX=0,anchorY=0;};
    std::array<Contact,10> pending{},current{};
    int slot=0,minX=0,maxX=799,minY=0,maxY=479;
    bool recovering=false;
    int scale(int value,int low,int high,int extent)const{return std::clamp(int((int64_t(value)-low)*extent/std::max(1,high-low)),0,extent);}
public:
    Controls(int x0=0,int x1=799,int y0=0,int y1=479):minX(x0),maxX(x1),minY(y0),maxY(y1){}
    void feed(unsigned type,unsigned code,int value){
        if(type==EV_SYN&&code==SYN_DROPPED){pending={};current={};slot=0;recovering=true;return;}
        if(recovering){if(type==EV_SYN&&code==SYN_REPORT)recovering=false;return;}
        if(type==EV_ABS){
            if(code==ABS_MT_SLOT){slot=value;return;}
            if(slot<0||slot>=int(pending.size()))return;
            auto& contact=pending[slot];
            if(code==ABS_MT_TRACKING_ID)contact.down=value>=0;
            if(code==ABS_MT_POSITION_X)contact.x=scale(value,minX,maxX,799);
            if(code==ABS_MT_POSITION_Y)contact.y=scale(value,minY,maxY,479);
        }
        if(type==EV_SYN&&code==SYN_REPORT){
            for(unsigned i=0;i<current.size();++i){
                auto next=pending[i];const auto& previous=current[i];
                next.fresh=next.down&&(!previous.down||previous.fresh);
                if(next.down&&!previous.down){next.anchorX=next.x;next.anchorY=next.y;}
                else{next.anchorX=previous.anchorX;next.anchorY=previous.anchorY;}
                current[i]=next;
            }
        }
    }
    uint16_t buttons(bool inGame){
        uint16_t result=0;bool steering=false;
        for(auto& contact:current){
            if(!contact.down)continue;
            if(!inGame){
                if(contact.x>=720){if(contact.fresh)result|=Bomb;}
                else if(contact.y<160)result|=Up;
                else if(contact.y>320)result|=Down;
                else if(contact.x<160)result|=Left;
                else if(contact.x>640)result|=Right;
                else if(contact.fresh)result|=Shoot;
            }else if(contact.x>=560){
                if(contact.fresh&&contact.y<100)result|=Menu;
                if(contact.fresh&&contact.y>320)result|=Bomb;
            }else if(!steering){
                steering=true;result|=Shoot|Focus;
                if(contact.x-contact.anchorX>6)result|=Right;
                if(contact.x-contact.anchorX<-6)result|=Left;
                if(contact.y-contact.anchorY>6)result|=Down;
                if(contact.y-contact.anchorY<-6)result|=Up;
            }
            contact.fresh=false;
        }
        return result;
    }
};
}
