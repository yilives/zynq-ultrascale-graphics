// SPDX-License-Identifier: MIT
// Called only by the trial parent with its inherited POST lock description.
#include "mc_snapshot_copy.hpp"
#include <fstream>
#include <iostream>
#include <sys/file.h>
#include <sys/stat.h>
using namespace rix_pl;
int main(int argc,char**argv){try{
 if(argc!=3)throw std::runtime_error("prefix inherited-post-lock-fd");
 std::string prefix=argv[1];int lock=std::stoi(argv[2]);
 if(prefix.rfind("/tmp/postproc-tests/java256-world-",0)!=0||prefix.find("..")!=std::string::npos)throw std::runtime_error("world evidence path refused");
 struct stat owned{},named{};
 if(fstat(lock,&owned)||lstat("/tmp/rix-superres.lock",&named)||!S_ISREG(named.st_mode)||owned.st_dev!=named.st_dev||owned.st_ino!=named.st_ino||flock(lock,LOCK_EX|LOCK_NB))throw std::runtime_error("parent POST lock required");
 int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0)throw std::runtime_error("devmem");
 Map regs(fd,0xa0010000,65536),pl(fd,0xa1000000,0x1000000);
 if(regs.read(0)!=0x52495801||regs.read(0x98)!=0x54584332||regs.read(0xb4)!=2||regs.read(8)!=3||regs.read(0x74)!=0x534e5031||regs.read(0x88)!=0xa1400000||regs.read(0x90)!=384000||regs.read(0x7c)||regs.read(0x8c))throw std::runtime_error("dual profile / snapshot not ready");
 Snapshot snap(regs,pl);std::vector<uint16_t> pixels(96000);
 if(!snap.read(pixels,nullptr,4,copy_snapshot_neon)||!snap.frame)throw std::runtime_error("immutable world snapshot failed");
 snap.release();if(regs.read(0x7c)||regs.read(0x8c))throw std::runtime_error("snapshot lease not released");
 std::ofstream raw(prefix+".bin",std::ios::binary);raw.write(reinterpret_cast<char*>(pixels.data()),192000);raw.close();if(!raw)throw std::runtime_error("snapshot output");
 std::ofstream meta(prefix+".json");meta<<"{\"frame_id\":"<<snap.frame<<",\"width\":400,\"height\":240,\"bytes\":192000,\"format\":\"RGB565\",\"immutable_snp1\":true,\"lease_released\":true}\n";meta.close();if(!meta)throw std::runtime_error("metadata output");
 close(fd);std::cout<<"JAVA_WORLD_SNAPSHOT_PASS frame="<<snap.frame<<" pixels=96000\n";return 0;
}catch(const std::exception&e){std::cerr<<"world snapshot: "<<e.what()<<'\n';return 1;}}
