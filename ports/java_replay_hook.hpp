// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "java_replay_device.hpp"
#include "plgpu-display.h"
#include "mc_snapshot_copy.hpp"
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <memory>
#include <string>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>

namespace rr::java_replay {
class Hook {
    using Clock=std::chrono::steady_clock;
    struct Pair {plgpu_status state{};uint64_t begin,end;};
public:
    explicit Hook(Device& device):m_device(device){}
    ~Hook(){m_snapshot.reset();m_pl.reset();m_regs.reset();if(m_mem>=0)close(m_mem);if(m_status>=0)close(m_status);}
    void initialize(){
        const char* request=std::getenv("RIX_JAVA_REPLAY_REQUEST");if(!request)return;
        m_request=request;const auto split=m_request.rfind('/');
        if(m_request.rfind("/tmp/postproc-tests/java256-world-r",0)!=0||m_request.find("..")!=std::string::npos||split==std::string::npos)throw std::runtime_error("Replay path refused");
        m_out=m_request.substr(0,split)+"/replay";
        if(mkdir(m_out.c_str(),0700))throw std::runtime_error("Replay output must be new");
        m_status=open("/dev/plgpu_display",O_RDWR|O_CLOEXEC);if(m_status<0)throw std::runtime_error("Replay status open");
        const auto state=status().state;
        if(state.frame_id!=state.swap_requests||state.swap_requests!=state.copy_done||state.copy_done!=state.presented||m_device.swapsSubmitted())throw std::runtime_error("Replay initial state not drained");
        m_origin=state.swap_requests;
        m_device.enableResourceShadow();
    }
    bool active()const{return !m_request.empty()&&m_phase>0&&m_phase<4;}
    bool requested()const{return !m_request.empty()&&m_phase==0&&access(m_request.c_str(),F_OK)==0;}
    void cancel(const std::exception&error)noexcept{
        m_phase=4;m_device.cancel();
        if(m_snapshot)m_snapshot->release();
        std::fprintf(stderr,"JAVA_REPLAY_FAILED %s\n",error.what());
        if(!m_out.empty()){if(FILE*f=std::fopen((m_out+"/failure.txt").c_str(),"wbx")){std::fprintf(f,"%s\n",error.what());std::fclose(f);}}
    }
    // Invoked only after the GLX owner has joined CPU/upload/DMA queues.
    void afterFrame(){
        if(m_request.empty()||m_phase==4)return;
        if(m_phase==0){
            if(!requested())return;
            waitAll();
            m_mem=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);if(m_mem<0)throw std::runtime_error("Replay MMIO open");
            m_regs=std::make_unique<rix_pl::Map>(m_mem,0xa0010000,65536);
            m_pl=std::make_unique<rix_pl::Map>(m_mem,0xa1000000,0x1000000);
            if(m_regs->read(0xb4)!=2||m_regs->read(0xb8)!=1||m_regs->read(0x74)!=0x534e5031||m_regs->read(0x7c)||m_regs->read(0x8c))throw std::runtime_error("Replay profile/SNP capability");
            // SNP1 copies the NEXT swap, not the already presented front. Arm
            // before returning to Java so its next real frame can fulfill it.
            m_snapshot=std::make_unique<rix_pl::Snapshot>(*m_regs,*m_pl);
            if(!m_snapshot->request())throw std::runtime_error("Replay next-frame snapshot arm");
            m_device.begin();m_phase=1;std::fprintf(stderr,"JAVA_REPLAY_CAPTURE_BEGIN\n");return;
        }
        m_device.endFrame();waitAll();
        const auto index=m_device.frames().size()-1;
        auto pixels=snapshot();writeBytes("reference-"+std::to_string(index)+".bin",pixels.data(),pixels.size()*2);m_reference.push_back(std::move(pixels));
        if(m_device.frames().size()!=3){if(!m_snapshot->request())throw std::runtime_error("Replay snapshot arm");return;}
        m_phase=3;saveTrace();
        for(unsigned cycle=0;cycle<2;++cycle){m_device.restoreResources();for(unsigned i=0;i<3;++i){
            if(!m_snapshot->request())throw std::runtime_error("Replay validation snapshot arm");
            m_device.replay(m_device.frames()[i]);waitAll();const auto pixels=snapshot();
            writeBytes("validation-"+std::to_string(cycle)+"-"+std::to_string(i)+".bin",pixels.data(),pixels.size()*2);
            if(pixels!=m_reference[i])throw std::runtime_error("Replay exact frame pixels differ");
        }}
        // Replay no longer runs the JVM game logic or geometry; these are backend
        // throughput results, never unique game FPS. Preserve ordered stores.
        m_device.restoreResources();for(const auto&frame:m_device.frames())m_device.replay(frame);waitAll();
        const auto before=status();const auto began=Clock::now();unsigned cycles=0;
        do{m_device.restoreResources();for(const auto&frame:m_device.frames())m_device.replay(frame);waitAll();++cycles;}
        while(Clock::now()-began<std::chrono::seconds(3));
        const auto after=status();const double seconds=double((after.begin+after.end)-(before.begin+before.end))/2e9;
        const uint32_t completed=after.state.presented-before.state.presented;
        if(completed!=cycles*3||seconds<=0)throw std::runtime_error("Replay counter/time pairing");
        // A separate final draw fulfills SNP after the benchmark timestamps.
        if(!m_snapshot->request())throw std::runtime_error("Replay final snapshot arm");
        m_device.replay(m_device.frames().back());waitAll();
        const auto final=snapshot();if(final!=m_reference.back())throw std::runtime_error("Replay final pixels differ");
        writeBytes("final.bin",final.data(),final.size()*2);
        FILE*f=newFile("result.json");
        std::fprintf(f,"{\"resource_restore_bytes_per_cycle\":%zu,\"resource_restore_included_in_benchmark\":true,\"result\":",m_device.restoreBytes());
        std::fprintf(f,"{\"passed\":true,\"diagnostic_only\":true,\"game_fps\":false,\"source_frames\":3,\"validation_cycles\":2,\"captured_bytes\":%zu,\"cycles\":%u,\"completed_frames\":%u,\"seconds\":%.12f,\"backend_fps\":%.12f,\"ordered_texture_stores_included\":true,\"group_completion_fence\":true,\"snapshot_excluded_from_benchmark\":true,\"before\":",m_device.capturedBytes(),cycles,completed,seconds,completed/seconds);
        writePair(f,before);std::fprintf(f,",\"after\":");writePair(f,after);std::fprintf(f,"}}\n");if(std::fclose(f))throw std::runtime_error("Replay result flush");
        m_phase=4;std::fprintf(stderr,"JAVA_REPLAY_PASS source_frames=3 validation_cycles=2 exact_pixels=1 ordered_stores=1 backend_fps=%.6f game_fps=0\n",completed/seconds);
    }
private:
    static uint64_t now(){return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();}
    Pair status(){Pair p;p.begin=now();const int rc=ioctl(m_status,PLGPU_GET_STATUS,&p.state);p.end=now();const auto&s=p.state;
        if(rc||s.abi!=0x52495801||s.configuration!=0x9adb505e||s.status!=3||!s.enabled||s.read_errors||s.write_errors||s.timeouts||s.scan_underflows||s.scan_errors)throw std::runtime_error("Replay status fault");return p;}
    void waitAll(){const uint32_t target=m_origin+uint32_t(m_device.swapsSubmitted());const auto deadline=Clock::now()+std::chrono::seconds(5);
        for(;;){const auto s=status().state;if(s.frame_id==target&&s.swap_requests==target&&s.copy_done==target&&s.presented==target&&s.last_presented_id==target)return;
            if(Clock::now()>deadline)throw std::runtime_error("Replay exact swap completion timeout");usleep(100);}}
    std::vector<uint16_t>snapshot(){std::vector<uint16_t>p(96000);
        if(!m_snapshot||!m_snapshot->token)throw std::runtime_error("Replay snapshot was not armed before draw");
        if(!m_snapshot->read(p,nullptr,4,rix_pl::copy_snapshot_neon)||m_snapshot->frame!=m_origin+uint32_t(m_device.swapsSubmitted()))throw std::runtime_error("Replay immutable source frame mismatch");
        m_snapshot->release();if(m_regs->read(0x7c)||m_regs->read(0x8c))throw std::runtime_error("Replay SNP release");return p;}
    FILE*newFile(const std::string&name){FILE*f=std::fopen((m_out+"/"+name).c_str(),"wbx");if(!f)throw std::runtime_error("Replay output exists or cannot open");return f;}
    void writeBytes(const std::string&name,const void*p,std::size_t n){FILE*f=newFile(name);const bool ok=std::fwrite(p,1,n,f)==n;const int rc=std::fclose(f);if(!ok||rc)throw std::runtime_error("Replay evidence write");}
    static void writePair(FILE*f,const Pair&p){std::fprintf(f,"{\"begin_ns\":%llu,\"end_ns\":%llu,\"status\":[",(unsigned long long)p.begin,(unsigned long long)p.end);const auto*v=reinterpret_cast<const uint32_t*>(&p.state);for(unsigned i=0;i<16;++i)std::fprintf(f,"%s%u",i?",":"",v[i]);std::fprintf(f,"]}");}
    void saveTrace(){FILE*f=newFile("trace.bin");const char magic[8]={'R','I','X','R','P','L','2',0};auto put=[&](const void*p,std::size_t n){if(std::fwrite(p,1,n,f)!=n)throw std::runtime_error("Replay trace write");};
        put(magic,8);uint32_t n=3;put(&n,4);for(const auto&frame:m_device.frames()){n=frame.events.size();put(&n,4);for(const auto&e:frame.events){uint32_t h[4]={e.kind,e.index,e.address,uint32_t(e.bytes.size())};put(h,sizeof(h));put(e.bytes.data(),e.bytes.size());}}
        n=m_device.resourceRestore().size();put(&n,4);for(const auto&e:m_device.resourceRestore()){uint32_t h[4]={e.kind,e.index,e.address,uint32_t(e.bytes.size())};put(h,sizeof(h));put(e.bytes.data(),e.bytes.size());}
        if(std::fclose(f))throw std::runtime_error("Replay trace close");}
    Device&m_device;std::string m_request,m_out;unsigned m_phase=0;uint32_t m_origin=0;int m_status=-1,m_mem=-1;
    std::unique_ptr<rix_pl::Map>m_regs,m_pl;std::unique_ptr<rix_pl::Snapshot>m_snapshot;std::vector<std::vector<uint16_t>>m_reference;
};
}
