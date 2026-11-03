// SPDX-License-Identifier: MIT
// Aligned Device reads from the same reserved idle PS staging arena as v4.
#include "../neural_style/pl_frames.hpp"
#include <iostream>
int main(int argc,char**argv){try{
 if(argc!=3)throw std::runtime_error("compressed byte count and new/payload required");
 size_t bytes=std::stoul(argv[1]);std::string kind=argv[2];
 if(!bytes||bytes>4194304||(kind!="new"&&kind!="payload"))throw std::runtime_error("invalid staging request");
 int fd=open("/dev/mem",O_RDONLY|O_SYNC);if(fd<0)throw std::runtime_error("open devmem");
 rix_pl::Map regs(fd,0xa0010000,65536,PROT_READ),memory(fd,0x60800000,4194304,PROT_READ);
 if(regs.read(0)!=0x52495801||regs.read(8)!=3||regs.read(0x44)!=0x60000000||regs.read(0x48)!=0x02000000||regs.read(0x7c))throw std::runtime_error("reserved arena/snapshot guard mismatch");
 size_t padded=(bytes+31)&~size_t(31);std::vector<uint32_t> data(padded/4);
 rix_pl::read_words(memory.p,data.data(),data.size());rix_pl::barrier();
 std::string path="/tmp/rix-fpga-fsr/"+kind+"-staging-read.bin";
 int out=open(path.c_str(),O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW,0600);if(out<0)throw std::runtime_error("preserve previous staging output");
 ssize_t done=write(out,data.data(),bytes);close(out);if(done!=ssize_t(bytes))throw std::runtime_error("short RAM staging write");
 std::cout<<"PS_FSR_STAGE_READ_OK "<<kind<<' '<<bytes<<'\n';close(fd);return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
