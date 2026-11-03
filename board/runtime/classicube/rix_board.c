/* SPDX-License-Identifier: MIT
 * Bounded diagnostics around real ClassiCube frames. No replacement renderer.
 */
#define _POSIX_C_SOURCE 200809L
#include "Game.h"
#include "World.h"
#include "Entity.h"
#include "Input.h"
#include "Window.h"
#include "Picking.h"
#include "Inventory.h"
#include "BlockID.h"
#include "Formats.h"
#include "Stream.h"
#include "Deflate.h"
#include "String_.h"
#include "Gui.h"
#include "Widgets.h"
#include "Event.h"
#include "Graphics.h"
#include <GL/gl.h>
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <time.h>
#include <math.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <stdint.h>

static volatile sig_atomic_t stopped;
static double started,world_started,measure_started,seconds;
static unsigned long frames,vertices;
static unsigned max_vertices;
static int autoplay,captured,reported;
static int qa,qa_stage,deleted,placed,save_result=-1;
static IVec3 dug,placed_at;
static Vec3 initial;
static int gpu_fd=-1;static uint32_t gpu_start;
static double loading_since;
static void input_qa_init(void);
static void input_qa_tick(void);
static void input_qa_after_present(void);
static double mono(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static void stop_requested(int sig){(void)sig;stopped=1;}
static unsigned world_hash(void){
    unsigned hash=2166136261u;int i;
    for(i=0;i<World.Volume;i++){hash^=World_GetRawBlock(i);hash*=16777619u;}
    return hash;
}
static int save_world(const char*path){
    struct Stream file,gzip;
    struct GZipState*state=calloc(1,sizeof(*state));
    cc_string name=String_FromReadonly(path);cc_result result,closed;
    if(!state)return -2;
    result=Stream_CreateFile(&file,&name);
    if(!result){
        GZip_MakeStream(&gzip,state,&file);result=Cw_Save(&gzip);
        closed=gzip.Close(&gzip);if(!result)result=closed;
        closed=file.Close(&file);if(!result)result=closed;
    }
    free(state);return result;
}
static void draw_cursor(float delta){
    int x,y,row,width;(void)delta;
    if(!Gui.InputGrab || !Window_Main.Focused)return;
    x=Pointers[0].x;y=Pointers[0].y;
    /* The PL LCD scans RasterIX, so the X server's separate cursor is invisible.
     * Draw a small contrasting pointer in the same 2D frame as menu widgets. */
    Gfx_SetAlphaTest(false);Gfx_SetAlphaBlending(false);
    for(row=0;row<11;row++)Gfx_Draw2DFlat(x,y+row,row/2+1,1,PackedCol_Make(0,0,0,255));
    Gfx_Draw2DFlat(x+3,y+8,3,5,PackedCol_Make(0,0,0,255));
    for(row=3;row<10;row++){
        width=row/2-1;if(width>0)Gfx_Draw2DFlat(x+1,y+row,width,1,PACKEDCOL_WHITE);
    }
    Gfx_Draw2DFlat(x+4,y+8,1,4,PACKEDCOL_WHITE);
}
void Rix_BoardBegin(void){
    const char*s=getenv("RIX_SECONDS");unsigned i;
    seconds=s?atof(s):0; if(seconds<0||seconds>3600)seconds=60;
    autoplay=getenv("RIX_AUTOPLAY")!=NULL;
    qa=getenv("RIX_GAMEPLAY_QA")!=NULL;
    started=mono();signal(SIGTERM,stop_requested);signal(SIGINT,stop_requested);
    gpu_fd=open("/dev/plgpu_display",O_RDWR|O_CLOEXEC);
    for(i=0;i<sizeof(Game.Draw2DHooks)/sizeof(Game.Draw2DHooks[0]);i++)
        if(!Game.Draw2DHooks[i]){Game.Draw2DHooks[i]=draw_cursor;break;}
    input_qa_init();
}
void Rix_BoardTick(void){
    if(stopped){Game_Running=false;return;}
    if(!World.Loaded || !World.Blocks){
        if(!loading_since)loading_since=mono();
        if(mono()-loading_since>45)Game_Running=false;
        return;
    }
    loading_since=0;input_qa_tick();
    if(!world_started){world_started=mono();initial=Entities.CurPlayer->Base.Position;
        printf("RIX_WORLD_READY %d %d %d\n",World.Width,World.Height,World.Length);fflush(stdout);}
    if(!measure_started && mono()-world_started>2){measure_started=mono();
        uint32_t words[16];if(gpu_fd>=0 && !ioctl(gpu_fd,0x80405200u,words))gpu_start=words[7];
        puts("RIX_MEASURE_BEGIN");fflush(stdout);}
    if(autoplay){
        struct Entity*e=&Entities.CurPlayer->Base;
        struct LocationUpdate u={0};
        double t=mono()-world_started;
        u.flags=LU_HAS_PITCH|LU_HAS_YAW;u.pitch=qa&&t>=3?50:15;u.yaw=qa&&t>=3?30:(float)fmod(t*12,360);
        e->VTABLE->SetLocation(e,&u);
        Input_SetNonRepeatable(CCKEY_W,(qa?t<3:fmod(t,10)<4));
        Input_SetNonRepeatable(CCKEY_SPACE,!qa&&fmod(t,6)<0.3);
        if(qa && t>=4 && qa_stage==0 && Game_SelectedPos.valid){
            dug=Game_SelectedPos.pos;
            if(World_Contains(dug.x,dug.y,dug.z)){
                Input_SetPressed(CCMOUSE_L);qa_stage=1;
            }
        }
        if(qa && t>=4.3 && qa_stage==1){
            Input_SetReleased(CCMOUSE_L);
            deleted=World_GetBlock(dug.x,dug.y,dug.z)==BLOCK_AIR;qa_stage=2;
        }
        if(qa && t>=5 && qa_stage==2 && Game_SelectedPos.valid){
            placed_at=Game_SelectedPos.translatedPos;
            if(World_Contains(placed_at.x,placed_at.y,placed_at.z)){
                Inventory_SetSelectedBlock(BLOCK_BRICK);Input_SetPressed(CCMOUSE_R);qa_stage=3;
            }
        }
        if(qa && t>=5.3 && qa_stage==3){
            Input_SetReleased(CCMOUSE_R);
            placed=World_GetBlock(placed_at.x,placed_at.y,placed_at.z)==BLOCK_BRICK;qa_stage=4;
            printf("RIX_GAMEPLAY_CHECK delete=%d place=%d\n",deleted,placed);fflush(stdout);
        }
        if(qa && t>=7 && save_result==-1 && getenv("RIX_SAVE")){
            save_result=save_world(getenv("RIX_SAVE"));
            printf("RIX_MAP_SAVED result=%d hash=%u\n",save_result,world_hash());fflush(stdout);
        }
    }
}
static int capture_presented(void){
    double until=mono()+5,stable=0;uint32_t previous=0,words[16];
    struct timespec pause={0,2000000};
    if(gpu_fd<0)return 0;
    while(mono()<until){
        int idle;
        if(ioctl(gpu_fd,0x80405200u,words) || words[0]!=0x52495801u ||
           words[1]!=0x9adb505eu || words[2]!=3 || words[9] || words[10] ||
           words[11] || words[12] || words[13])return 0;
        idle=words[4]==words[5] && words[4]==words[6] && words[4]==words[7] && words[4]==words[8];
        if(!idle || words[4]!=previous || !stable){stable=idle?mono():0;previous=words[4];}
        else if(mono()-stable>=0.03){
            printf("RIX_CAPTURE_PRESENTED %u\n",words[4]);fflush(stdout);return 1;
        }
        nanosleep(&pause,NULL);
    }
    return 0;
}
static int capture_frame(const char*path){
    if(path){
        unsigned char*rgba=calloc(400*240,4);int x,y,ok=1;
        if(!rgba){stopped=1;return 0;}
        /* Read the just-presented front buffer. RasterIX supports RGBA only.
         * OpenGL returns bottom-up rows; PPM and LCD samples are top-down. */
        while(glGetError()!=GL_NO_ERROR){}
        glPixelStorei(GL_PACK_ALIGNMENT,1);
        glReadPixels(0,0,400,240,GL_RGBA,GL_UNSIGNED_BYTE,rgba);
        if(glGetError()!=GL_NO_ERROR){free(rgba);stopped=1;return 0;}
        /* This first read drains both asynchronous CPU queues and DMA. The
         * GPU/LCD can still be completing that frame. Discard the priming
         * pixels, fence real presentation, then read the stable front again. */
        if(!capture_presented()){free(rgba);stopped=1;return 0;}
        glReadPixels(0,0,400,240,GL_RGBA,GL_UNSIGNED_BYTE,rgba);
        if(glGetError()!=GL_NO_ERROR){free(rgba);stopped=1;return 0;}
        FILE*f=fopen(path,"wb");
        if(f){
            if(fprintf(f,"P6\n400 240\n255\n")<0)ok=0;
            for(y=239;y>=0;y--)for(x=0;x<400;x++)
                if(fwrite(rgba+(y*400+x)*4,1,3,f)!=3)ok=0;
            if(fclose(f))ok=0;
        }else ok=0;
        free(rgba);return ok;
    }
    return 0;
}
#include "rix_input_qa.h"
void Rix_BoardAfterPresent(void){
    if(!world_started)return;
    input_qa_after_present();
    if(measure_started){
        frames++;vertices+=Game_Vertices;if((unsigned)Game_Vertices>max_vertices)max_vertices=Game_Vertices;
    }
    if(!stopped && Game_Running && Window_Main.Exists && (!seconds || mono()-world_started<seconds))return;
    if(!reported){
        struct Entity*e=&Entities.CurPlayer->Base;
        uint32_t hw_count=0,hw_words[16];int hw_valid=0;
        if(gpu_fd>=0 && !ioctl(gpu_fd,0x80405200u,hw_words)){
            hw_count=measure_started?hw_words[7]-gpu_start:0;hw_valid=1;
        }
        double elapsed=measure_started?mono()-measure_started:0;
        if(getenv("RIX_CAPTURE"))captured=capture_frame(getenv("RIX_CAPTURE"));
        printf("RIX_CLASSICUBE_RESULT {\"frames\":%lu,\"seconds\":%.6f,\"fps\":%.6f,\"vertices\":%lu,\"max_vertices\":%u,\"world\":[%d,%d,%d],\"start\":[%.5f,%.5f,%.5f],\"end\":[%.5f,%.5f,%.5f],\"autoplay\":%s,\"capture\":%s}\n",frames,elapsed,elapsed>0?frames/elapsed:0,vertices,max_vertices,World.Width,World.Height,World.Length,initial.x,initial.y,initial.z,e->Position.x,e->Position.y,e->Position.z,autoplay?"true":"false",captured?"true":"false");
        fflush(stdout);reported=1;
        if(gpu_fd>=0){if(hw_valid){
            printf("RIX_HARDWARE_WINDOW {\"seconds\":%.6f,\"presented\":%u,\"fps\":%.6f,\"native_telemetry\":true}\n",elapsed,hw_count,elapsed>0?hw_count/elapsed:0);
        }close(gpu_fd);gpu_fd=-1;}
        printf("RIX_CLASSICUBE_WORLD {\"hash_fnv1a32\":%u,\"qa_stage\":%d,\"deleted\":%s,\"placed\":%s,\"save_result\":%d}\n",world_hash(),qa_stage,deleted?"true":"false",placed?"true":"false",save_result);fflush(stdout);
        if(getenv("RIX_HOLD")){int hold=atoi(getenv("RIX_HOLD"));if(hold>0&&hold<=30)sleep(hold);}
    }
    Game_Running=false;
}
