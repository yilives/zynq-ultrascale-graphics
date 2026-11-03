// SPDX-License-Identifier: MIT
#include "cnn_fsr_pl.hpp"
#include <sys/file.h>
int main(int argc,char**argv){try{
 using namespace rix_pl;using rix_cnn_fsr::require;
 require(argc==3,"test-cnn-fsr input400.xrgb output800.xrgb");
 int lock=open("/tmp/rix-superres.lock",O_CREAT|O_RDWR|O_NOFOLLOW,0600);require(lock>=0&&flock(lock,LOCK_EX|LOCK_NB)==0,"post lock busy");
 rix_cnn_fsr::gate();signal(SIGTERM,stop);signal(SIGINT,stop);
 int mem=open("/dev/mem",O_RDWR|O_SYNC);require(mem>=0,"mem open failed");Map regs(mem,0xa0010000,65536),pl(mem,0xa1000000,0x1000000);
 require(!(regs.read(0x7c)&3)&&regs.read(0x54)==regs.read(0x58),"snapshot/display busy");
 std::vector<uint32_t> source(96000),result(384000);std::ifstream input(argv[1],std::ios::binary);input.read(reinterpret_cast<char*>(source.data()),384000);require(bool(input)&&input.peek()==EOF,"wrong source length");
 rix_cnn_fsr::Kernel kernel(mem);kernel.invalidate();kernel.call(99,0,0,0,0,2);kernel.call(1,0,0,0,0,1);
 write_words(static_cast<char*>(pl.p)+0x500000,source.data(),source.size());unsigned bank=((regs.read(0x58)>>9)&1)^1;
 auto load_us=kernel.call(0,0x21500000,0,0x43465331,0x43465331);
 auto compute_us=kernel.call(1,0,0x21000000+bank*0x200000,0x43465331,0x43465331);
 read_words(static_cast<char*>(pl.p)+bank*0x200000,result.data(),result.size());barrier();
 std::ofstream output(argv[2],std::ios::binary);output.write(reinterpret_cast<const char*>(result.data()),1536000);require(bool(output),"output failed");
 std::cout<<"{\"passed\":true,\"load_us\":"<<load_us<<",\"compute_us\":"<<compute_us<<",\"pixels\":384000,\"presented\":false}\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
