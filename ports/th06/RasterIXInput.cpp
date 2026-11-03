// SPDX-License-Identifier: GPL-3.0-or-later
#include "TouchControls.hpp"
#include "Controller.hpp"
#include "Supervisor.hpp"
#include "GameManager.hpp"
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <glob.h>
#include <memory>
#include <sys/ioctl.h>
#include <unistd.h>

static_assert(uint16_t(th06touch::Shoot)==uint16_t(TH_BUTTON_SHOOT)&&uint16_t(th06touch::Bomb)==uint16_t(TH_BUTTON_BOMB)&&uint16_t(th06touch::Focus)==uint16_t(TH_BUTTON_FOCUS)&&uint16_t(th06touch::Menu)==uint16_t(TH_BUTTON_MENU)&&uint16_t(th06touch::Up)==uint16_t(TH_BUTTON_UP)&&uint16_t(th06touch::Down)==uint16_t(TH_BUTTON_DOWN)&&uint16_t(th06touch::Left)==uint16_t(TH_BUTTON_LEFT)&&uint16_t(th06touch::Right)==uint16_t(TH_BUTTON_RIGHT),"Touch button ABI");
namespace {
class TouchInput {
    int fd=-1;std::unique_ptr<th06touch::Controls> controls;
    unsigned logs=0;uint16_t previous=0;
    bool openDevice(const char* path,bool explicitDevice){
        const int probe=open(path,O_RDONLY|O_NONBLOCK|O_CLOEXEC);if(probe<0)return false;
        char name[160]{};input_absinfo x{},y{};
        const bool valid=ioctl(probe,EVIOCGNAME(sizeof(name)),name)>=0&&(explicitDevice||std::strstr(name,"Goodix"))&&ioctl(probe,EVIOCGABS(ABS_MT_POSITION_X),&x)>=0&&ioctl(probe,EVIOCGABS(ABS_MT_POSITION_Y),&y)>=0&&x.maximum>x.minimum&&y.maximum>y.minimum;
        if(!valid){close(probe);return false;}
        fd=probe;controls=std::make_unique<th06touch::Controls>(x.minimum,x.maximum,y.minimum,y.maximum);
        std::printf("TH06_TOUCH_READY device=%s name=%s x=%d..%d y=%d..%d grabbed=0\n",path,name,x.minimum,x.maximum,y.minimum,y.maximum);std::fflush(stdout);return true;
    }
public:
    TouchInput(){
        const char* enabled=std::getenv("TH06_TOUCH");if(enabled&&!std::strcmp(enabled,"0"))return;
        if(const char* path=std::getenv("TH06_TOUCH_DEVICE")){openDevice(path,true);return;}
        glob_t devices{};if(glob("/dev/input/event*",0,nullptr,&devices)==0)for(size_t i=0;i<devices.gl_pathc;++i)if(openDevice(devices.gl_pathv[i],false))break;globfree(&devices);
    }
    ~TouchInput(){if(fd>=0)close(fd);}
    uint16_t poll(){
        if(fd<0)return 0;
        input_event events[64];
        for(unsigned block=0;block<8;++block){
            const ssize_t count=read(fd,events,sizeof(events));
            if(count<0){if(errno==EINTR)continue;if(errno!=EAGAIN){close(fd);fd=-1;controls.reset();}break;}
            if(!count){close(fd);fd=-1;controls.reset();break;}
            for(ssize_t i=0;i<count/ssize_t(sizeof(input_event));++i)controls->feed(events[i].type,events[i].code,events[i].value);
        }
        if(!controls)return 0;
        const bool playing=g_Supervisor.curState==SUPERVISOR_STATE_GAMEMANAGER&&!g_GameManager.isInGameMenu&&!g_GameManager.isInRetryMenu;
        const auto buttons=controls->buttons(playing);
        if(buttons!=previous&&logs<48){std::printf("TH06_TOUCH_BUTTONS state=%d mask=%u\n",g_Supervisor.curState,buttons);std::fflush(stdout);++logs;}
        previous=buttons;return buttons;
    }
};
}
u16 RasterIXTouchButtons(){static TouchInput input;return input.poll();}
