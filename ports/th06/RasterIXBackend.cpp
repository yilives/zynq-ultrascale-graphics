// SPDX-License-Identifier: GPL-3.0-or-later
#include "RasterIXBackend.hpp"
#include "RasterIXTextures.hpp"
#include "RIXGL.hpp"
#include "DMAProxyBusConnector.hpp"
#include "StdThreadRunner.hpp"
#include "renderer/devicedatauploader/DeviceDataUploader.hpp"
#include "renderer/threadedvertextransformer/ThreadedVertexTransformer.hpp"
#include "Supervisor.hpp"
#include "GameManager.hpp"
#include "BulletManager.hpp"
#include "EnemyManager.hpp"
#include "AnmManager.hpp"
#include "plgpu-display.h"
#include <algorithm>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <stdexcept>
#include <sys/ioctl.h>
#include <thread>
#include <unordered_map>
#include <unistd.h>
int RasterIXAtlasQA(GfxInterface&,RasterIXTextures&,const char*);

namespace {
#if defined(__FLOAT_WORD_ORDER__)
static_assert(__FLOAT_WORD_ORDER__==__BYTE_ORDER__,"This port requires matching integer/float byte order");
#endif
using Clock=std::chrono::steady_clock;
float presentedFPS=0;
volatile std::sig_atomic_t requestedStop=0;
void stopSignal(int){requestedStop=1;}
void checked(int fd,unsigned long op,void* p){if(ioctl(fd,op,p)<0)throw std::runtime_error("RasterIX display ioctl failed");}
plgpu_status getStatus(int fd){
    plgpu_status s{};checked(fd,PLGPU_GET_STATUS,&s);
    if(s.abi!=0x52495801||s.configuration!=0x9adb505e||s.status!=3)throw std::runtime_error("RasterIX hardware ABI/config/status mismatch");
    return s;
}
bool sameErrors(const plgpu_status& a,const plgpu_status& b){return a.read_errors==b.read_errors&&a.write_errors==b.write_errors&&a.timeouts==b.timeouts&&a.scan_underflows==b.scan_underflows&&a.scan_errors==b.scan_errors;}
}
struct RasterIXBackend::State {
    int display=-1;bool created=false;SDL_Window* window=nullptr;
    std::unique_ptr<rr::DMAProxyBusConnector> bus;
    std::unique_ptr<rr::devicedatauploader::DeviceDataUploader> upload;
    rr::StdThreadRunner worker,transfer;
    std::unique_ptr<rr::threadedvertextransformer::ThreadedVertexTransformer> device;
    std::unique_ptr<RasterIXTextures> textures;
    RasterIXTextures::Stats reportedTextures;
    double drawMs=0,reportedDrawMs=0,drainMs=0,waitMs=0;
    plgpu_status baseline{},current{};
    Clock::time_point began=Clock::now(),lastReport=began;unsigned frames=0;
    u32 reportedBusy=0,reportedBeats=0;
    std::array<double,30> frameTimes{};unsigned rateIndex=0,rateSamples=0;double rateSum=0;
    Clock::time_point lastPresent=began;
    void wait(u32 target){
        const auto deadline=Clock::now()+std::chrono::seconds(5);
        for(;;){
            current=getStatus(display);
            if(!sameErrors(baseline,current))throw std::runtime_error("RasterIX error counters increased");
            if(current.presented&&static_cast<int32_t>(current.last_presented_id-target)>=0)return;
            if(Clock::now()>=deadline)throw std::runtime_error("RasterIX presentation timeout");
            std::this_thread::sleep_for(std::chrono::microseconds(300));
        }
    }
    void drain(){if(device)device->deinit();}
    void shutdown(){
        if(created){
            drain();textures.reset();const auto target=getStatus(display).frame_id+1;
            rr::RIXGL::destroy();created=false;drain();wait(target);
        }
    }
    ~State(){
        try{shutdown();}catch(const std::exception& e){std::fprintf(stderr,"TH06_RIX_SHUTDOWN: %s\n",e.what());}
        device.reset();upload.reset();bus.reset();
        if(window)SDL_DestroyWindow(window);
        if(display>=0)close(display);
    }
};
float RasterIXPresentedFPS(){return presentedFPS;}
GfxInterface* RasterIXBackend::Init(){
    std::unique_ptr<RasterIXBackend> self(new RasterIXBackend());
    self->state=std::make_unique<State>();auto& s=*self->state;
    try{
        s.display=open("/dev/plgpu_display",O_RDWR|O_CLOEXEC);
        if(s.display<0)throw std::runtime_error("Load plgpu_display before running th06-rix");
        s.baseline=s.current=getStatus(s.display);
        s.reportedBusy=s.current.gpu_busy_cycles;s.reportedBeats=s.current.command_beats;
        if(s.current.frame_id!=s.current.last_presented_id)s.wait(s.current.frame_id);
        __u32 enable=1;checked(s.display,PLGPU_ENABLE,&enable);
        s.bus=std::make_unique<rr::DMAProxyBusConnector>();
        s.upload=std::make_unique<rr::devicedatauploader::DeviceDataUploader>(*s.bus);
        s.device=std::make_unique<rr::threadedvertextransformer::ThreadedVertexTransformer>(*s.upload,s.worker,s.transfer);
        if(!rr::RIXGL::createInstance(*s.device))throw std::runtime_error("RIXGL context creation failed");s.created=true;
        if(!rr::RIXGL::getInstance().setRenderResolution(400,240))throw std::runtime_error("400x240 resolution failed");
        // SDL provides events only. Prevent implicit accelerated X11 framebuffer
        // creation from loading another GL implementation with its own DMA bus.
        SDL_SetHint(SDL_HINT_FRAMEBUFFER_ACCELERATION,"0");
        SDL_SetHint(SDL_HINT_RENDER_DRIVER,"software");
        std::fprintf(stderr,"TH06_RIX_STAGE SDL_INIT\n");
        if(SDL_Init(SDL_INIT_VIDEO)!=0)throw std::runtime_error(SDL_GetError());
        std::fprintf(stderr,"TH06_RIX_STAGE SDL_WINDOW\n");
        s.window=SDL_CreateWindow("TH06 RasterIX FPGA",SDL_WINDOWPOS_UNDEFINED,SDL_WINDOWPOS_UNDEFINED,400,240,SDL_WINDOW_SHOWN);
        if(!s.window)throw std::runtime_error(SDL_GetError());
        SDL_RaiseWindow(s.window);
        std::signal(SIGINT,stopSignal);std::signal(SIGTERM,stopSignal);
        std::fprintf(stderr,"TH06_RIX_STAGE GL_TABLE\n");
        g_glFuncTable.ResolveFunctions(false);
        s.textures=std::make_unique<RasterIXTextures>();
        g_glFuncTable.glEnable(GL_TEXTURE_2D);g_glFuncTable.glEnableClientState(GL_VERTEX_ARRAY);
        g_glFuncTable.glEnable(GL_ALPHA_TEST);g_glFuncTable.glAlphaFunc(GL_GEQUAL,4/255.f);
        g_glFuncTable.glEnable(GL_FOG);g_glFuncTable.glFogf(GL_FOG_MODE,GL_LINEAR);g_glFuncTable.glFogf(GL_FOG_DENSITY,1);
        g_glFuncTable.glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_COMBINE);
        for(const auto component:{GL_COMBINE_RGB,GL_COMBINE_ALPHA})g_glFuncTable.glTexEnvi(GL_TEXTURE_ENV,component,GL_MODULATE);
        g_glFuncTable.glTexEnvi(GL_TEXTURE_ENV,GL_SRC0_RGB,GL_TEXTURE);g_glFuncTable.glTexEnvi(GL_TEXTURE_ENV,GL_SRC0_ALPHA,GL_TEXTURE);
        g_glFuncTable.glTexEnvi(GL_TEXTURE_ENV,GL_SRC1_RGB,GL_CONSTANT);g_glFuncTable.glTexEnvi(GL_TEXTURE_ENV,GL_SRC1_ALPHA,GL_CONSTANT);
        g_glFuncTable.glTexEnvi(GL_TEXTURE_ENV,GL_OPERAND0_RGB,GL_SRC_COLOR);g_glFuncTable.glTexEnvi(GL_TEXTURE_ENV,GL_OPERAND1_RGB,GL_SRC_COLOR);
        g_glFuncTable.glTexEnvi(GL_TEXTURE_ENV,GL_OPERAND0_ALPHA,GL_SRC_ALPHA);g_glFuncTable.glTexEnvi(GL_TEXTURE_ENV,GL_OPERAND1_ALPHA,GL_SRC_ALPHA);
        g_glFuncTable.glViewport(0,0,400,240);g_glFuncTable.glClearColor(0,0,0,1);g_glFuncTable.glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        u32 viewport[4]{};self->GetViewport(viewport);
        if(viewport[0]!=0||viewport[1]!=0||viewport[2]!=400||viewport[3]!=240)throw std::runtime_error("RasterIX viewport roundtrip failed");
        std::printf("TH06_RIX_VIEWPORT_SELFTEST_PASS 0,0,400,240\n");
        std::printf("TH06_RASTERIX_READY render=400x240 content=320x240+40 texture_limit=128 trial=0.13\n");
        std::printf("TH06_TEXTURE_MODE=%s page_limit=192\n",s.textures->mode());
        if(const char* prefix=std::getenv("TH06_ATLAS_QA")){
            const int result=RasterIXAtlasQA(*self,*s.textures,prefix);
            self.reset();std::exit(result);
        }
        return self.release();
    }catch(const std::exception& e){std::fprintf(stderr,"TH06_RIX_INIT: %s\n",e.what());return nullptr;}
}
RasterIXBackend::~RasterIXBackend(){Exit();}
void RasterIXBackend::Exit(){state.reset();}
void RasterIXBackend::GetViewport(u32* viewport){
    // This core's glGetIntegerv converts only the first GL_VIEWPORT element.
    // The engine needs all four to form its inverse screen-space projection;
    // uninitialized width/height otherwise clip away the player and HUD.
    GLfloat values[4]{};g_glFuncTable.glGetFloatv(GL_VIEWPORT,values);
    for(unsigned i=0;i<4;++i)viewport[i]=static_cast<u32>(values[i]);
}
void RasterIXBackend::SwapBuffers(){
    auto& s=*state;const auto target=s.current.frame_id+1;
    const auto submit=Clock::now();rr::RIXGL::getInstance().swapDisplayList();s.drain();
    const auto drained=Clock::now();s.wait(target);const auto presented=Clock::now();
    s.rateSum-=s.frameTimes[s.rateIndex];s.frameTimes[s.rateIndex]=std::chrono::duration<double>(presented-s.lastPresent).count();s.rateSum+=s.frameTimes[s.rateIndex];
    s.rateIndex=(s.rateIndex+1)%s.frameTimes.size();s.rateSamples=std::min(30u,s.rateSamples+1);s.lastPresent=presented;
    presentedFPS=s.rateSum>0?s.rateSamples/s.rateSum:0;
    s.drainMs+=std::chrono::duration<double,std::milli>(drained-submit).count();
    s.waitMs+=std::chrono::duration<double,std::milli>(presented-drained).count();
    ++s.frames;s.textures->frame(s.frames);
    if(s.frames%60==0){
        const auto now=Clock::now();
        const double elapsed=std::chrono::duration<double>(now-s.began).count();
        const double interval=std::chrono::duration<double>(now-s.lastReport).count();
        const u32 busy=s.current.gpu_busy_cycles-s.reportedBusy,beats=s.current.command_beats-s.reportedBeats;
        std::printf("TH06_RIX_FRAME frames=%u seconds=%.3f fps=%.3f window_fps=%.3f state=%d stage=%d bullets=%d enemies=%d logic_ticks=%d game_frames=%u flushes=%d gpu_ms_per_frame=%.3f command_beats_per_frame=%.1f presented=%u\n",s.frames,elapsed,s.frames/elapsed,60/interval,g_Supervisor.curState,g_GameManager.currentStage,g_BulletManager.bulletCount,g_EnemyManager.enemyCount,g_Supervisor.calcCount,g_GameManager.gameFrames,g_AnmManager?g_AnmManager->flushesThisFrame:0,busy/6000000.,beats/60.,s.current.presented);
        s.lastReport=now;s.reportedBusy=s.current.gpu_busy_cycles;s.reportedBeats=s.current.command_beats;std::fflush(stdout);
        const auto& t=s.textures->stats();const auto& p=s.reportedTextures;
        std::printf("TH06_TEXTURE_STATS frames=%u mode=%s resident=%u uploads=%llu upload_bytes=%llu draw_calls=%llu triangles=%llu clipped=%llu fast_vertices=%llu evictions=%llu fallbacks=%llu cpu_draw_ms_per_frame=%.3f worker_dma_ms_per_frame=%.3f present_wait_ms_per_frame=%.3f\n",s.frames,s.textures->mode(),t.resident,(unsigned long long)(t.uploads-p.uploads),(unsigned long long)(t.uploadBytes-p.uploadBytes),(unsigned long long)(t.draws-p.draws),(unsigned long long)(t.triangles-p.triangles),(unsigned long long)(t.clipped-p.clipped),(unsigned long long)(t.fastVertices-p.fastVertices),(unsigned long long)(t.evictions-p.evictions),(unsigned long long)(t.fallbacks-p.fallbacks),(s.drawMs-s.reportedDrawMs)/60,s.drainMs/60,s.waitMs/60);
        s.reportedTextures=t;s.reportedDrawMs=s.drawMs;s.drainMs=s.waitMs=0;std::fflush(stdout);
    }
    const char* limit=std::getenv("TH06_RUN_SECONDS");
    if(requestedStop||(limit&&std::chrono::duration<double>(Clock::now()-s.began).count()>=std::atof(limit))){
        const char* path=std::getenv("TH06_CAPTURE_PATH");
        if(path&&*path){
            std::vector<u8> data(400*240*4);g_glFuncTable.glReadPixels(0,0,400,240,GL_RGBA,GL_UNSIGNED_BYTE,data.data());s.drain();
            std::ofstream file(path,std::ios::binary);file<<"P6\n400 240\n255\n";
            for(int y=239;y>=0;--y)for(int x=0;x<400;++x)file.write(reinterpret_cast<const char*>(&data[(y*400+x)*4]),3);
            file.close();std::printf("TH06_RIX_CAPTURED %s\n",path);std::fflush(stdout);
            const char* hold=std::getenv("TH06_HOLD_LAST_SECONDS");
            if(hold)std::this_thread::sleep_for(std::chrono::seconds(std::max(0,std::min(10,std::atoi(hold)))));
        }
        SDL_Event quit{};quit.type=SDL_QUIT;SDL_PushEvent(&quit);
    }
}
GfxTextureHandle RasterIXBackend::CreateTexture(){return state->textures->create();}
void RasterIXBackend::BindTexture(GfxTextureHandle id){state->textures->bind(id);}
void RasterIXBackend::DeleteTexture(GfxTextureHandle id){state->textures->erase(id);}
void RasterIXBackend::SetTextureImage(u32 w,u32 h,PixelFormat f,PixelDataType t,const void* data){state->textures->image(w,h,f,t,data);}
void RasterIXBackend::SetTextureSubImage(i32 x,i32 y,i32 w,i32 h,const void* data){state->textures->subImage(x,y,w,h,data);}
void RasterIXBackend::SetTextureFilter(){state->textures->filter();}
void RasterIXBackend::ToggleVertexAttribute(u8 attributes,bool enabled){FixedFunctionGL::ToggleVertexAttribute(attributes,enabled);state->textures->toggle(attributes,enabled);}
void RasterIXBackend::SetAttributePointer(VertexAttributeArrays kind,std::size_t stride,void* pointer){FixedFunctionGL::SetAttributePointer(kind,stride,pointer);state->textures->attribute(kind,stride,pointer);}
void RasterIXBackend::SetTransformMatrix(TransformMatrix kind,const ZunMatrix& matrix){FixedFunctionGL::SetTransformMatrix(kind,matrix);state->textures->matrix(kind,matrix);}
void RasterIXBackend::Draw(PrimitiveType type,i32 start,i32 count){
    const auto began=Clock::now();state->textures->draw(type,start,count);
    state->drawMs+=std::chrono::duration<double,std::milli>(Clock::now()-began).count();
}
