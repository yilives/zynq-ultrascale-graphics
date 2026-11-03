// Optional diagnostic only: read the completed front buffer before renderer teardown.
#pragma once
#include "vertexpipeline/VertexPipeline.hpp"
#include <array>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/ioctl.h>
#include <thread>
#include <unistd.h>
#include <vector>

namespace java_front_capture {
struct Fd {
    int value;
    explicit Fd(int n):value(n){if(n<0)throw std::runtime_error("front capture open failed");}
    ~Fd(){::close(value);}
    Fd(const Fd&)=delete;
};
using GpuStatusWords=std::array<uint32_t,16>;
inline GpuStatusWords status(int fd) {
    GpuStatusWords s{};
    if(::ioctl(fd,0x80405200,s.data())<0)throw std::runtime_error("front capture status ioctl failed");
    if(s[0]!=0x52495801||s[1]!=0x9adb505e||s[2]!=3)throw std::runtime_error("front capture GPU not ready");
    for(int i=9;i<=13;i++)if(s[i])throw std::runtime_error("front capture GPU errors present");
    return s;
}
inline bool drained(const GpuStatusWords&s){for(int i=5;i<=8;i++)if(s[i]!=s[4])return false;return true;}
inline void file(const std::string&path,const void*data,size_t count) {
    Fd fd(::open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600));
    const char* p=static_cast<const char*>(data);
    while(count) {
        const auto n=::write(fd.value,p,count);
        if(n<0&&errno==EINTR)continue;
        if(n<=0)throw std::runtime_error("front capture file write failed");
        p+=n;count-=n;
    }
    if(::fsync(fd.value))throw std::runtime_error("front capture file sync failed");
}
inline void capture(rr::RIXGL&gl,uint64_t swaps) {
    const char* input=std::getenv("RIX_JAVA_LAST_FRONT");
    if(!input||!swaps)return;
    const std::string path(input);
    if(path.rfind("/tmp/postproc-tests/",0)!=0||path.find("..")!=std::string::npos||path.size()>1024)
        throw std::runtime_error("front capture requires owned RAM result path");
    const auto width=gl.pipeline().getFramebufferWidth(),height=gl.pipeline().getFramebufferHeight();
    if(!width||!height||width>400||height>240)throw std::runtime_error("front capture resolution outside profile");
    Fd ctl(::open("/dev/plgpu_display",O_RDWR|O_CLOEXEC));
    const auto until=std::chrono::steady_clock::now()+std::chrono::seconds(5);
    GpuStatusWords before{};
    do {
        before=status(ctl.value);
        if(drained(before))break;
        if(std::chrono::steady_clock::now()>until)throw std::runtime_error("front capture queues did not drain");
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }while(true);
    std::vector<uint8_t> pixels(width*height*2);
    if(!gl.pipeline().readFrontColorBuffer({pixels.data(),pixels.size()}))
        throw std::runtime_error("front capture memory read failed");
    const auto after=status(ctl.value);
    if(!drained(after))throw std::runtime_error("front capture queues changed");
    for(int i=4;i<=8;i++)if(before[i]!=after[i])throw std::runtime_error("front capture frame changed");
    file(path,pixels.data(),pixels.size());
    std::ostringstream json;
    json<<"{\"format\":\"RGB565\",\"before_default_buffer_reset\":true,\"width\":"<<width
        <<",\"height\":"<<height<<",\"bytes\":"<<pixels.size()<<",\"renderer_swaps\":"<<swaps<<",\"before\":[";
    for(size_t i=0;i<before.size();i++)json<<(i?",":"")<<before[i];
    json<<"],\"after\":[";
    for(size_t i=0;i<after.size();i++)json<<(i?",":"")<<after[i];
    json<<"]}\n";
    const auto metadata=json.str();file(path+".json",metadata.data(),metadata.size());
    std::fprintf(stderr,"JAVA_FRONT_CAPTURE before_reset=1 frame=%u swaps=%llu size=%zux%zu\n",
        after[4],static_cast<unsigned long long>(swaps),width,height);
}
}
