// SPDX-License-Identifier: GPL-3.0-or-later
#include "TouchControls.hpp"
#include <cassert>
#include <cstdio>
using namespace th06touch;
int main(){
    Controls touch;
    auto press=[&](int slot,int x,int y){touch.feed(EV_ABS,ABS_MT_SLOT,slot);touch.feed(EV_ABS,ABS_MT_TRACKING_ID,slot+1);touch.feed(EV_ABS,ABS_MT_POSITION_X,x);touch.feed(EV_ABS,ABS_MT_POSITION_Y,y);touch.feed(EV_SYN,SYN_REPORT,0);};
    press(0,300,240);assert(touch.buttons(false)==Shoot);assert(touch.buttons(false)==0);
    touch.feed(EV_ABS,ABS_MT_TRACKING_ID,-1);touch.feed(EV_SYN,SYN_REPORT,0);assert(touch.buttons(true)==0);
    press(0,300,240);assert(touch.buttons(true)==(Shoot|Focus));
    touch.feed(EV_ABS,ABS_MT_POSITION_X,330);touch.feed(EV_ABS,ABS_MT_POSITION_Y,210);touch.feed(EV_SYN,SYN_REPORT,0);
    assert(touch.buttons(true)==(Shoot|Focus|Right|Up));
    press(1,650,400);assert(touch.buttons(true)==(Shoot|Focus|Right|Up|Bomb));
    assert(touch.buttons(true)==(Shoot|Focus|Right|Up));
    press(2,650,40);assert(touch.buttons(true)==(Shoot|Focus|Right|Up|Menu));
    touch.feed(EV_SYN,SYN_DROPPED,0);touch.feed(EV_SYN,SYN_REPORT,0);assert(touch.buttons(true)==0);
    Controls scaled(0,1599,0,959);scaled.feed(EV_ABS,ABS_MT_TRACKING_ID,1);scaled.feed(EV_ABS,ABS_MT_POSITION_X,1500);scaled.feed(EV_ABS,ABS_MT_POSITION_Y,500);scaled.feed(EV_SYN,SYN_REPORT,0);assert(scaled.buttons(false)==Bomb);
    std::puts("TH06_TOUCH_MAPPING_TEST_PASS menu_drag_multitouch_release_dropped_sync_scaled_axes");
}
