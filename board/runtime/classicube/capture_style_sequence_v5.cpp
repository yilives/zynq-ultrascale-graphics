// SPDX-License-Identifier: MIT
// Immutable SNP1 samples only; no framebuffer changes or live PS-slot reads.
#include "mc_snapshot_copy.hpp"
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sys/file.h>
using namespace rix_pl;
int main(int argc,char**argv){try{
 if(argc!=4)throw std::runtime_error("directory count interval-ms");
 std::string path=argv[1];unsigned count=std::stoul(argv[2]),interval=std::stoul(argv[3]);
 if(path.rfind("/tmp/postproc-tests/cc_v5_data_",0)!=0||path.find("..")!=std::string::npos||count<2||count>32||interval<100||interval>2000)throw std::runtime_error("invalid capture bounds");
 int lock=open("/tmp/rix-superres.lock",O_CREAT|O_RDWR,0600);
 if(lock<0||flock(lock,LOCK_EX|LOCK_NB))throw std::runtime_error("postprocessor busy");
 if(access("/proc/device-tree/rasterix-frame-snapshot/rasterix,snapshot-version",F_OK))throw std::runtime_error("SNP1 DT missing");
 int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0)throw std::runtime_error("devmem");
 Map regs(fd,0xa0010000,65536),pl(fd,0xa1000000,0x1000000);
 if(regs.read(0)!=0x52495801||regs.read(0x0c)!=0x9adb505e||regs.read(8)!=3||regs.read(0x74)!=0x534e5031||regs.read(0x88)!=0xa1400000||regs.read(0x90)!=384000||regs.read(0x7c)||regs.read(0x8c))throw std::runtime_error("snapshot/GPU preflight");
 Snapshot snap(regs,pl);std::vector<uint16_t> pixels(96000);uint32_t previous=0;
 std::ofstream meta(path+"/captures.json");meta<<"[";
 auto began=Clock::now();
 for(unsigned i=0;i<count;i++){
  if(!snap.read(pixels,nullptr,4,copy_snapshot_neon)||!snap.frame||snap.frame==previous)throw std::runtime_error("failed/duplicate immutable snapshot");
  previous=snap.frame;
  std::string name="source"+std::to_string(i)+".bin";
  std::ofstream raw(path+"/"+name,std::ios::binary);raw.write(reinterpret_cast<char*>(pixels.data()),192000);raw.close();if(!raw)throw std::runtime_error("capture write");
  if(i)meta<<",";
  meta<<"{\"index\":"<<i<<",\"file\":\""<<name<<"\",\"frame_id\":"<<snap.frame<<",\"monotonic_seconds\":"<<std::setprecision(15)<<std::chrono::duration<double>(Clock::now().time_since_epoch()).count()<<",\"lease_verified_after_copy\":true}";
  std::this_thread::sleep_until(began+std::chrono::milliseconds(interval*(i+1)));
 }
 snap.release();if(regs.read(0x7c)||regs.read(0x8c))throw std::runtime_error("snapshot lease not clear");
 meta<<"]\n";meta.close();if(!meta)throw std::runtime_error("metadata write");
 close(fd);close(lock);std::cout<<"CAPTURE_V5_PASS "<<count<<"\n";return 0;
}catch(const std::exception&e){std::cerr<<"capture v5: "<<e.what()<<'\n';return 1;}}
