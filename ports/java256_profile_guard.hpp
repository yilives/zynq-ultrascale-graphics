// SPDX-License-Identifier: GPL-3.0-or-later
// A 256-texel driver must never attach to the old 128-texel bitstream.
#pragma once
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <cstdint>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
static bool verifyJava256Profile()
{
    const char* path="/tmp/rix-fpga-java256/active-receipt.txt";
    struct stat info{};
    if(lstat(path,&info)||!S_ISREG(info.st_mode)||info.st_uid||((info.st_mode&0022)!=0))
    { std::fprintf(stderr,"JAVA256_PROFILE_REFUSED missing trusted active receipt\n");std::abort(); }
    std::ifstream file(path),bootFile("/proc/sys/kernel/random/boot_id");
    std::string magic,boot,bit,source,current;
    std::getline(file,magic);std::getline(file,boot);std::getline(file,bit);std::getline(file,source);std::getline(bootFile,current);
    if(magic!="RIX_TEX256_CACHE_ACTIVE_V1"||boot!=current||bit.size()!=64||source.size()!=64)
    { std::fprintf(stderr,"JAVA256_PROFILE_REFUSED receipt/boot mismatch\n");std::abort(); }
    // Only the new, journaled profile permits probing its added control CSRs.
    int fd=open("/dev/mem",O_RDONLY|O_SYNC);
    void* p=fd<0?MAP_FAILED:mmap(nullptr,4096,PROT_READ,MAP_SHARED,fd,0xa0010000);
    if(p==MAP_FAILED){std::fprintf(stderr,"JAVA256_PROFILE_REFUSED control mapping\n");std::abort();}
    auto csr=static_cast<volatile const uint32_t*>(p);
    bool ok=csr[0]==0x52495801&&csr[3]==0x9adb505e&&csr[0x98/4]==0x54584331
        &&csr[0x9c/4]==0x01000100&&csr[0xa0/4]==1024&&csr[0xa4/4]==7;
    munmap(p,4096);close(fd);
    if(!ok){std::fprintf(stderr,"JAVA256_PROFILE_REFUSED hardware profile mismatch\n");std::abort();}
    std::fprintf(stderr,"JAVA256_FULL_TEXTURE_PROFILE max=256 cache=1024 resampled=0\n");
    return true;
}
static const bool java256ProfileVerified=verifyJava256Profile();
