// SPDX-License-Identifier: MIT
// CPU controls ownership and presentation; every EASU / RCAS pixel is computed
// by the AXI master in PL. The existing CPU FSR program remains independent.
#include "../neural_style/pl_frames.hpp"
#include "fsr_pl_build.hpp"
#include <fstream>
#include <iostream>
#include <sstream>
#include <sys/file.h>
#include <sys/stat.h>
using namespace rix_pl;
static const char* receipt_path="/tmp/rix-fpga-fsr/active-receipt.txt";
static const char* quarantine_path="/tmp/rix-fsr-pl.quarantine";
static void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
struct Fd {
 int fd;
 Fd(const char*path,int flags,mode_t mode=0):fd(open(path,flags,mode)){require(fd>=0,"open failed");}
 ~Fd(){close(fd);}
};
static std::string line(const char*path){std::ifstream f(path);std::string s;std::getline(f,s);require(bool(f),"cannot read identity");return s;}
static void gate(){
 require(geteuid()==0,"root required");
 require(std::string(FSR_PL_BIT_SHA256).size()==64,"runtime has no approved bitstream identity");
 require(access(quarantine_path,F_OK)!=0,"FSR is quarantined; recover PL before reuse");
 Fd f(receipt_path,O_RDONLY|O_NOFOLLOW);struct stat st{};
 require(fstat(f.fd,&st)==0&&S_ISREG(st.st_mode)&&st.st_uid==0&&!(st.st_mode&0077)&&st.st_size>0&&st.st_size<512,"invalid load receipt permissions/size");
 std::string text(size_t(st.st_size),'\0');require(read(f.fd,text.data(),text.size())==ssize_t(text.size()),"short load receipt");
 std::istringstream stream(text);std::string format,boot,bit,source,extra;
 require(bool(std::getline(stream,format))&&bool(std::getline(stream,boot))&&bool(std::getline(stream,bit))&&bool(std::getline(stream,source))&&!std::getline(stream,extra),"invalid load receipt format");
 require(format=="RIX_FSR_PL_ACTIVE_V1"&&boot==line("/proc/sys/kernel/random/boot_id")&&bit==FSR_PL_BIT_SHA256&&source==FSR_PL_SOURCE_SHA256,"receipt is not bound to this boot and approved FSR build");
}
static void save(const std::string&path,const void*data,size_t bytes){std::ofstream f(path,std::ios::binary);f.write(static_cast<const char*>(data),bytes);require(bool(f),"file write failed");}
static void quarantine(const char*why){
 int fd=open(quarantine_path,O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW,0600);
 if(fd>=0){auto written=write(fd,why,strlen(why));if(written>=0)fsync(fd);close(fd);}
 // Revoke the capability before releasing any lock. Reusing PL requires a
 // new, boot-bound manager transaction, including recovery from SIGKILL.
 unlink(receipt_path);
}
[[noreturn]] static void fail_stop(const char*why){
 sigset_t blocked;sigfillset(&blocked);sigprocmask(SIG_BLOCK,&blocked,nullptr);
 quarantine(why);std::cerr<<"FSR_QUARANTINE: "<<why<<"; keeping the display lock until a board reset\n"<<std::flush;
 // A possibly live AXI master owns its addresses until whole-PL reset. Keep
 // the shared postprocessor flock; SIGINT/SIGTERM must not publish/reuse a bank.
 for(;;)pause();
}
struct Kernel {
 Map r;bool inflight=false;
 explicit Kernel(int fd):r(fd,0xa0040000,65536){}
 uint32_t call(unsigned mode,uint32_t source,uint32_t output,uint32_t tag,uint32_t expected_tag,unsigned expected_return=0){
  require(!inflight,"FSR command already pending");
  uint32_t control=r.read(0);if(!(control&4)||(control&0x81))fail_stop("FSR is not idle or auto-restart is enabled");
  r.read(0x3c); // Clear the previous result-valid indication.
  r.write(0x18,mode);r.write(0x20,source);r.write(0x28,output);r.write(0x30,tag);
  inflight=true;auto start=Clock::now();r.write(0,1);
  // Signals request shutdown; they must never abandon an AXI reader/writer.
  while(!(r.read(0)&2)){
   if(Clock::now()-start>std::chrono::seconds(10)){
    fail_stop("FSR AXI completion timeout: cold boot is required before starting another client");
   }
   usleep(100);
  }
  inflight=false;barrier();
  require(r.read(0x10)==expected_return,"FSR command returned an error");
  require((r.read(0x3c)&1)&&r.read(0x38)==expected_tag,"FSR result tag mismatch");
  return uint32_t(std::chrono::duration_cast<std::chrono::microseconds>(Clock::now()-start).count());
 }
 void invalidate(){call(2,0,0,0,0);}
};
struct Lease {
 Map&r;uint32_t token=0,frame=0;bool readable=false;
 explicit Lease(Map&regs):r(regs){}
 bool owned(){return token&&r.read(0x80)==token&&(r.read(0x7c)&3)==3;}
 void release(){if(token&&r.read(0x80)==token&&(r.read(0x7c)&3))r.write(0x80,token);token=0;}
 ~Lease(){if(!readable)release();} // A timed-out reader must not release its lease.
 bool acquire(){
  auto deadline=Clock::now()+std::chrono::seconds(3);
  while(r.read(0x7c)&3){if(stopped())return false;require(Clock::now()<deadline,"snapshot remains busy");usleep(1000);}
  token=r.read(0x80)+1;if(!token)token=1;r.write(0x78,token);
  while(!owned()){
   if(stopped()){release();return false;}
   if(r.read(0x80)==token&&(r.read(0x7c)&3)==0){release();return false;}
   require(Clock::now()<deadline,"snapshot acquisition timeout");usleep(1000);
  }
  frame=r.read(0x84);return true;
 }
};
static void set_post(Map&r,uint32_t value){
 r.write(0x54,value);auto end=Clock::now()+std::chrono::seconds(2);
 while(r.read(0x54)!=value||r.read(0x58)!=value){require(Clock::now()<end,"LCD bank switch timeout");usleep(1000);}
}
static void dump_bank(Map&pl,unsigned bank,const std::string&path){
 std::vector<uint32_t> words(384000);read_words(static_cast<char*>(pl.p)+bank*0x200000,words.data(),words.size());barrier();save(path,words.data(),words.size()*4);
}
int main(int argc,char**argv){try{
 bool live=false,protocol=false,no_present=false;std::string input,output,reference;double seconds=10,hold=0;
 for(int i=1;i<argc;i++){
  std::string key=argv[i];auto value=[&](){require(++i<argc,"missing option value");return std::string(argv[i]);};
  if(key=="--live")live=true;else if(key=="--protocol-check")protocol=true;
  else if(key=="--no-present")no_present=true;else if(key=="--verify-output")reference=value();
  else if(key=="--input")input=value();else if(key=="--output")output=value();
  else if(key=="--seconds")seconds=std::stod(value());else if(key=="--hold-seconds")hold=std::stod(value());
  else if(key=="--help"){std::cout<<"rix-fsr-pl --live --seconds 10 [--output last.xrgb] [--hold-seconds 5]\nrix-fsr-pl --input 400x240.rgb565 --output 800x480.xrgb [--no-present] [--verify-output golden.xrgb]\nrix-fsr-pl --protocol-check\n";return 0;}
  else throw std::runtime_error("unknown option "+key);
 }
 require((live?1:0)+(protocol?1:0)+(!input.empty()?1:0)==1,"choose live, static input or protocol check");
 require(seconds>0&&seconds<=3600&&hold>=0&&hold<=120,"invalid duration");
 require(!live||(!no_present&&reference.empty()),"static verification options cannot be used in live mode");
 Fd lock("/tmp/rix-superres.lock",O_CREAT|O_RDWR|O_NOFOLLOW,0600);require(flock(lock.fd,LOCK_EX|LOCK_NB)==0,"another postprocessor owns the display");
 signal(SIGINT,stop);signal(SIGTERM,stop);gate();
 Fd mem("/dev/mem",O_RDWR|O_SYNC);Map regs(mem.fd,0xa0010000,65536);
 require(regs.read(0x50)==0x50535431&&regs.read(0x74)==0x534e5031&&regs.read(0x88)==0xa1400000&&regs.read(0x90)==384000,"PST1/SNP1 layout mismatch");
 require((regs.read(0x7c)&3)==0&&regs.read(0x54)==regs.read(0x58),"snapshot or display switch is busy");
 Kernel kernel(mem.fd);kernel.invalidate();kernel.call(99,0,0,0,0,2);kernel.call(1,0,0,0,0,1);
 if(protocol){std::cout<<"PASS FSR_PL protocol: invalidate, invalid mode, missing input\n";return 0;}
 Map pl(mem.fd,0xa1000000,0x1000000);Lease lease(regs);
 uint32_t saved=regs.read(0x54);bool displayed=false;unsigned frames=0,retries=0,last_bank=0;uint64_t load_us=0,compute_us=0;auto started=Clock::now();
 try{
  do{
   uint32_t source=0x21400000,tag=0;
   if(live){
    if(!lease.acquire()){++retries;continue;}tag=lease.frame;lease.readable=true;
    load_us+=kernel.call(0,source,0,tag,tag);lease.readable=false;
    bool valid=lease.owned();lease.release();if(!valid){kernel.invalidate();++retries;continue;}
   }else{
    // Static validation uses an independent scratch range, never the SNP1
    // destination owned by the frame bridge. Both postprocessors share a lock.
    std::vector<uint16_t> raw(96000);std::ifstream f(input,std::ios::binary);f.read(reinterpret_cast<char*>(raw.data()),192000);require(bool(f)&&f.peek()==EOF,"input must be exactly 192000 RGB565 bytes");
    std::vector<uint32_t> words(96000);for(unsigned i=0;i<words.size();++i){uint32_t p=raw[i];unsigned r=p>>11,g=(p>>5)&63,b=p&31;words[i]=(((r<<3)|(r>>2))<<16)|(((g<<2)|(g>>4))<<8)|((b<<3)|(b>>2));}
    write_words(static_cast<char*>(pl.p)+0x500000,words.data(),words.size());source=0x21500000;tag=0x46535231;
    load_us+=kernel.call(0,source,0,tag,tag);
   }
   unsigned bank=((regs.read(0x58)>>9)&1)^1;
   compute_us+=kernel.call(1,0,0x21000000+bank*0x200000,tag,tag);
   // AP_DONE is downstream of the final AXI B response. The C/RTL tests and
   // the full-image board comparison are required before enabling this path.
   if(!reference.empty()){
    std::vector<uint32_t> expected(384000),actual(384000);std::ifstream f(reference,std::ios::binary);f.read(reinterpret_cast<char*>(expected.data()),1536000);require(bool(f)&&f.peek()==EOF,"reference must be exactly 1536000 XRGB bytes");
    read_words(static_cast<char*>(pl.p)+bank*0x200000,actual.data(),actual.size());barrier();
    require(expected==actual,"PL FSR full-frame output differs from fixed-point golden; frame was not published");
    std::cout<<"PASS FSR_PL_FULL_FRAME_GOLDEN 384000 pixels\n";
   }
   if(!no_present){displayed=true;set_post(regs,2|(bank<<9));}last_bank=bank;++frames;
  }while(live&&!stopped()&&std::chrono::duration<double>(Clock::now()-started).count()<seconds);
  double elapsed=std::chrono::duration<double>(Clock::now()-started).count();
  require(frames>0,"no FSR frames processed");
  std::cout<<"{\"backend\":\"FPGA PL EASU12 + RCAS5 fixed point\",\"frames\":"<<frames<<",\"elapsed_seconds\":"<<elapsed<<",\"processed_fps\":"<<frames/elapsed<<",\"input_load_us\":"<<load_us<<",\"compute_us\":"<<compute_us<<",\"snapshot_retries\":"<<retries<<",\"last_source_frame\":"<<lease.frame<<",\"last_bank\":"<<last_bank<<",\"cpu_pixel_processing_live\":false}"<<std::endl;
  if(!output.empty())dump_bank(pl,last_bank,output);
  auto until=Clock::now()+std::chrono::duration<double>(hold);while(!stopped()&&Clock::now()<until)usleep(1000);
  if(displayed){set_post(regs,saved);displayed=false;}kernel.invalidate();
 }catch(...){if(!kernel.inflight){lease.readable=false;lease.release();if(displayed){try{set_post(regs,saved);}catch(...){fail_stop("LCD restoration failed; cold boot is required");}}}throw;}
 return 0;
}catch(const std::exception&e){std::cerr<<"rix-fsr-pl: "<<e.what()<<'\n';return 1;}}
