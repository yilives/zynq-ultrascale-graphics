// SPDX-License-Identifier: MIT
// Offline load-contention diagnostic. Reuse the reviewed driver's exact
// completion, quarantine, receipt and mapping code without altering production.
#define main rix_fsr_original_main
#include "rix_fsr_pl.cpp"
#undef main

int main(int argc,char**argv){try{
 require(argc==3,"usage: rix-fsr-load-probe source.rgb565 golden.xrgb");
 Fd game_lock("/tmp/rasterix-game-launch.lock",O_CREAT|O_RDWR|O_NOFOLLOW,0600);
 Fd style_lock("/tmp/rix-mc-style-extract.lock",O_CREAT|O_RDWR|O_NOFOLLOW,0600);
 Fd post_lock("/tmp/rix-superres.lock",O_CREAT|O_RDWR|O_NOFOLLOW,0600);
 for(int fd:{game_lock.fd,style_lock.fd,post_lock.fd})
  require(flock(fd,LOCK_EX|LOCK_NB)==0,"another client owns a required diagnostic lock");
 signal(SIGINT,stop);signal(SIGTERM,stop);gate();
 Fd mem("/dev/mem",O_RDWR|O_SYNC);Map regs(mem.fd,0xa0010000,65536);
 require(regs.read(0x50)==0x50535431&&regs.read(0x74)==0x534e5031&&
         regs.read(0x88)==0xa1400000&&regs.read(0x90)==384000,"PST1/SNP1 layout mismatch");
 require(regs.read(0x54)==1&&regs.read(0x58)==1&&regs.read(0x7c)==0&&regs.read(0x8c)==0,
         "probe requires idle bilinear/style0 and no lease errors");
 Kernel kernel(mem.fd);Map pl(mem.fd,0xa1000000,0x1000000);
 std::vector<uint16_t> raw(96000);std::ifstream input(argv[1],std::ios::binary);
 input.read(reinterpret_cast<char*>(raw.data()),192000);
 require(bool(input)&&input.peek()==EOF,"input must be exactly 192000 RGB565 bytes");
 std::vector<uint32_t> source(96000),golden(384000),actual(384000);
 for(unsigned i=0;i<source.size();++i){uint32_t p=raw[i];unsigned r=p>>11,g=(p>>5)&63,b=p&31;
  source[i]=(((r<<3)|(r>>2))<<16)|(((g<<2)|(g>>4))<<8)|((b<<3)|(b>>2));}
 std::ifstream reference(argv[2],std::ios::binary);
 reference.read(reinterpret_cast<char*>(golden.data()),1536000);
 require(bool(reference)&&reference.peek()==EOF,"golden must be exactly 1536000 XRGB bytes");
 // Same independent scratch range as accepted static validation, never SNP1.
 write_words(static_cast<char*>(pl.p)+0x500000,source.data(),source.size());barrier();
 kernel.invalidate();std::ostringstream rows;bool first=true;unsigned checked=0;
 auto one=[&](unsigned mode,unsigned run,unsigned sample){
  require(!stopped(),"probe stop requested");
  require(regs.read(0x54)==mode&&regs.read(0x58)==mode&&regs.read(0x7c)==0,
          "display or snapshot ownership changed during probe");
  unsigned bank=((regs.read(0x58)>>9)&1)^1;
  uint32_t load=kernel.call(0,0x21500000,0,0x46535231,0x46535231);
  uint32_t compute=kernel.call(1,0,0x21000000+bank*0x200000,0x46535231,0x46535231);
  read_words(static_cast<char*>(pl.p)+bank*0x200000,actual.data(),actual.size());barrier();
  require(actual==golden,"full-frame golden mismatch during load probe");++checked;
  if(!first)rows<<',';first=false;
  rows<<"{\"run\":"<<run<<",\"sample\":"<<sample<<",\"post\":"<<mode
      <<",\"load_us\":"<<load<<",\"compute_us\":"<<compute<<",\"pixels\":384000,\"mismatches\":0}";
 };
 try{
  one(1,0,0); // Also initialize bank1 with a verified full-size golden frame.
  unsigned sequence[4]={1,514,514,1};
  for(unsigned run=0;run<4;++run){
   set_post(regs,sequence[run]);
   for(unsigned sample=0;sample<5;++sample)one(sequence[run],run+1,sample+1);
  }
  set_post(regs,1);kernel.invalidate();
  require(regs.read(0x54)==1&&regs.read(0x58)==1&&regs.read(0x7c)==0&&regs.read(0x8c)==0,
          "diagnostic restoration failed");
 }catch(...){if(!kernel.inflight){try{set_post(regs,1);kernel.invalidate();}catch(...){fail_stop("load probe restoration failed");}}throw;}
 std::cout<<"{\"passed\":true,\"offline_only\":true,\"scratch_source\":\"0x21500000\",\"checked_frames\":"<<checked
          <<",\"restored_post\":1,\"samples\":["<<rows.str()<<"]}"<<std::endl;
 return 0;
}catch(const std::exception&e){std::cerr<<"rix-fsr-load-probe: "<<e.what()<<'\n';return 1;}}
