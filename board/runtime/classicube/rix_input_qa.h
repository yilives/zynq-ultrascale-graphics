/* SPDX-License-Identifier: MIT
 * Optional observation only: no synthetic keys, camera or world mutations.
 * X11/SDL QA uses this to observe the same input path as attached keyboards.
 */
#include <ctype.h>
#include <string.h>
static const char*input_dir;
static double input_next;
static unsigned input_down,input_up,button_down,button_up,input_wheels,input_motion;
static unsigned user_deleted,user_placed;
static void input_changed(void*obj,IVec3 pos,BlockID old,BlockID now){
    (void)obj;(void)pos;
    if(old!=BLOCK_AIR && now==BLOCK_AIR)user_deleted++;
    if(old==BLOCK_AIR && now!=BLOCK_AIR)user_placed++;
}
void Rix_SdlInput(int kind,int a,int b){
    (void)a;
    if(!input_dir)return;
    if(kind==1){if(b)input_down++;else input_up++;}
    if(kind==2){if(b)button_down++;else button_up++;}
    if(kind==3)input_wheels++;
    if(kind==4)input_motion++;
}
static void input_qa_init(void){
    input_dir=getenv("RIX_INPUT_QA");
    if(input_dir)Event_Register_(&UserEvents.BlockChanged,NULL,input_changed);
}
static void input_qa_tick(void){
    char path[512],temporary[512];FILE*f;int i,comma=0;
    struct Entity*e;
    if(!input_dir || mono()<input_next)return;
    input_next=mono()+0.1;e=&Entities.CurPlayer->Base;
    snprintf(path,sizeof(path),"%s/input.json",input_dir);
    snprintf(temporary,sizeof(temporary),"%s/input.json.tmp",input_dir);
    f=fopen(temporary,"w");if(!f)return;
    fprintf(f,"{\"time\":%.6f,\"focus\":%d,\"raw\":%d,\"gui_grab\":%d,\"cursor_visible\":%d,\"size\":[%d,%d],\"position\":[%.5f,%.5f,%.5f],\"yaw\":%.5f,\"pitch\":%.5f,\"slot\":%d,\"block\":%u,\"picked_valid\":%d,\"picked_block\":%u,\"picked\":[%d,%d,%d],\"adjacent\":[%d,%d,%d],\"W\":%d,\"Space\":%d,\"left\":%d,\"right\":%d,\"sdl\":{\"key_down\":%u,\"key_up\":%u,\"button_down\":%u,\"button_up\":%u,\"wheel\":%u,\"motion\":%u},\"deleted\":%u,\"placed\":%u,\"pointer\":[%d,%d],\"widgets\":[",
        mono(),Window_Main.Focused,Input.RawMode,Gui.InputGrab!=NULL,DisplayInfo.CursorVisible,
        Window_Main.Width,Window_Main.Height,e->Position.x,e->Position.y,e->Position.z,e->Yaw,e->Pitch,
        Inventory.SelectedIndex,(unsigned)Inventory_SelectedBlock,Game_SelectedPos.valid,
        Game_SelectedPos.valid?(unsigned)World_SafeGetBlock(Game_SelectedPos.pos.x,Game_SelectedPos.pos.y,Game_SelectedPos.pos.z):0,
        Game_SelectedPos.pos.x,Game_SelectedPos.pos.y,Game_SelectedPos.pos.z,
        Game_SelectedPos.translatedPos.x,Game_SelectedPos.translatedPos.y,Game_SelectedPos.translatedPos.z,
        Input.Pressed[CCKEY_W],Input.Pressed[CCKEY_SPACE],Input.Pressed[CCMOUSE_L],Input.Pressed[CCMOUSE_R],
        input_down,input_up,button_down,button_up,input_wheels,input_motion,user_deleted,user_placed,Pointers[0].x,Pointers[0].y);
    if(Gui.InputGrab)for(i=0;i<Gui.InputGrab->numWidgets;i++){
        struct Widget*w=Gui.InputGrab->widgets[i];
        if(!w || w->width<=0 || w->height<=0)continue;
        fprintf(f,"%s{\"i\":%d,\"x\":%d,\"y\":%d,\"w\":%d,\"h\":%d}",comma?",":"",i,w->x,w->y,w->width,w->height);comma=1;
    }
    fputs("]}\n",f);fclose(f);rename(temporary,path);
}
static void input_qa_after_present(void){
    char request[512],path[512],token[33];FILE*f;size_t i;int ok;
    if(!input_dir)return;
    snprintf(request,sizeof(request),"%s/request.txt",input_dir);
    f=fopen(request,"r");if(!f)return;
    ok=fscanf(f,"%32s",token)==1;fclose(f);unlink(request);
    if(!ok)return;
    for(i=0;token[i];i++)if(!isalnum((unsigned char)token[i])&&token[i]!='_')return;
    snprintf(path,sizeof(path),"%s/%s.ppm",input_dir,token);ok=capture_frame(path);
    snprintf(path,sizeof(path),"%s/%s.done",input_dir,token);
    f=fopen(path,"w");if(f){fprintf(f,"%d\n",ok);fclose(f);}
    /* Freeze only this requested frame until independent LCD sampling ends. */
    snprintf(path,sizeof(path),"%s/%s.release",input_dir,token);
    {double deadline=mono()+8;struct timespec interval={0,10000000};
     while(access(path,F_OK)&&mono()<deadline&&!stopped)nanosleep(&interval,NULL);}
    unlink(path);
}
