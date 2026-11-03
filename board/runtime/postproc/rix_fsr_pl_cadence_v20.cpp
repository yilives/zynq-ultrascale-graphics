// SPDX-License-Identifier: MIT
// Isolated scheduling experiment: request next SNP1 near COMPUTE completion.
// CPU controls ownership and presentation; every EASU / RCAS pixel is computed
// by the AXI master in PL. The existing CPU FSR program remains independent.
#include "../neural_style/pl_frames.hpp"
#include "fsr_pl_build.hpp"
#include <fstream>
#include <iostream>
#include <sstream>
#include <sys/file.h>
#include <sys/stat.h>
#include <exception>
#include <functional>
#ifdef RIX_FSR_PREFETCH_TEST
#include "../../sim/fixtures/fsr_prefetch_mock.hpp"
#endif
using namespace rix_pl;
struct WallTime {
 static Clock::time_point now(){return Clock::now();}
 static void sleep_us(unsigned us){usleep(us);}
};
#ifdef RIX_FSR_PREFETCH_TEST
using ScheduleMap=fsr_prefetch_mock::MockMap;
using ScheduleTime=fsr_prefetch_mock::MockTime;
#else
using ScheduleMap=Map;
using ScheduleTime=WallTime;
#endif
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
#ifdef RIX_FSR_PREFETCH_TEST
 fsr_prefetch_mock::env->quarantined=true;
 fsr_prefetch_mock::env->receipt_revoked=true;
 fsr_prefetch_mock::env->event("QUARANTINE");
 (void)why;
#else
 int fd=open(quarantine_path,O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW,0600);
 if(fd>=0){auto written=write(fd,why,strlen(why));if(written>=0)fsync(fd);close(fd);}
 // Revoke the capability before releasing any lock. Reusing PL requires a
 // new, boot-bound manager transaction, including recovery from SIGKILL.
 unlink(receipt_path);
#endif
}
[[noreturn]] static void fail_stop(const char*why){
#ifdef RIX_FSR_PREFETCH_TEST
 quarantine(why);throw fsr_prefetch_mock::FailStop(why);
#else
 sigset_t blocked;sigfillset(&blocked);sigprocmask(SIG_BLOCK,&blocked,nullptr);
 quarantine(why);std::cerr<<"FSR_QUARANTINE: "<<why<<"; keeping the display lock until a board reset\n"<<std::flush;
 // A possibly live AXI master owns its addresses until whole-PL reset. Keep
 // the shared postprocessor flock; SIGINT/SIGTERM must not publish/reuse a bank.
 for(;;)pause();
#endif
}
struct LeaseLostBeforeLoad:std::runtime_error{LeaseLostBeforeLoad():std::runtime_error("SNP lease lost before LOAD AP_START"){} };
struct Kernel {
 ScheduleMap r;bool inflight=false;
 explicit Kernel(int fd):r(fd,0xa0040000,65536){}
 uint32_t call(unsigned mode,uint32_t source,uint32_t output,uint32_t tag,uint32_t expected_tag,unsigned expected_return=0,const std::function<void(uint64_t)>&progress={},const std::function<bool()>&start_guard={}){
  require(!inflight,"FSR command already pending");
  uint32_t control=r.read(0);if(!(control&4)||(control&0x81))fail_stop("FSR is not idle or auto-restart is enabled");
  r.read(0x3c); // Clear the previous result-valid indication.
  r.write(0x18,mode);r.write(0x20,source);r.write(0x28,output);r.write(0x30,tag);
  if(start_guard&&!start_guard())throw LeaseLostBeforeLoad();
  inflight=true;auto start=ScheduleTime::now();r.write(0,1);std::exception_ptr progress_error;
  // Signals request shutdown; they must never abandon an AXI reader/writer.
  while(!(r.read(0)&2)){
   if(ScheduleTime::now()-start>std::chrono::seconds(10)){
    fail_stop("FSR AXI completion timeout: cold boot is required before starting another client");
   }
   // A progress failure must not unwind while the AXI master is active.
   if(progress&&!progress_error){try{progress(uint64_t(std::chrono::duration_cast<std::chrono::microseconds>(ScheduleTime::now()-start).count()));}catch(...){progress_error=std::current_exception();}}
   ScheduleTime::sleep_us(100);
  }
  inflight=false;barrier();
  require(r.read(0x10)==expected_return,"FSR command returned an error");
  require((r.read(0x3c)&1)&&r.read(0x38)==expected_tag,"FSR result tag mismatch");
  if(progress_error)std::rethrow_exception(progress_error);
  return uint32_t(std::chrono::duration_cast<std::chrono::microseconds>(ScheduleTime::now()-start).count());
 }
 void invalidate(){call(2,0,0,0,0);}
};
struct Lease {
 ScheduleMap&r;uint32_t token=0,frame=0,expiry_at_request=0;bool readable=false,prefetched=false;
 Clock::time_point requested{};
 explicit Lease(ScheduleMap&regs):r(regs){}
 bool owned(){return token&&r.read(0x80)==token&&(r.read(0x7c)&0x103)==3&&r.read(0x8c)==expiry_at_request;}
 uint64_t age_us(){return token?uint64_t(std::chrono::duration_cast<std::chrono::microseconds>(ScheduleTime::now()-requested).count()):0;}
 bool valid_for_load(){return token&&age_us()<1500000&&owned();}
 bool request_nonblocking(bool early=false){
  require(!readable,"snapshot request while LOAD reads its lease");
  if(token||stopped()||(r.read(0x7c)&3))return false;
  uint32_t next=r.read(0x80)+1;if(!next)next=1;
  expiry_at_request=r.read(0x8c);requested=ScheduleTime::now();prefetched=early;
  token=next; // Retain the token even if a progress callback later fails.
  r.write(0x78,token);return true;
 }
 void release(){if(token&&r.read(0x80)==token&&(r.read(0x7c)&3))r.write(0x80,token);token=0;}
 ~Lease(){
#ifdef RIX_FSR_PREFETCH_TEST
  if(fsr_prefetch_mock::env->quarantined)return; // Model non-unwinding fail_stop.
#endif
  if(!readable)release();
 } // A timed-out reader must not release its lease.
 bool acquire(){
  auto deadline=ScheduleTime::now()+std::chrono::seconds(3);
  while(r.read(0x7c)&3){if(stopped())return false;require(ScheduleTime::now()<deadline,"snapshot remains busy");ScheduleTime::sleep_us(1000);}
  if(!request_nonblocking())return false;
  while(!owned()){
   if(stopped()){release();return false;}
   if(r.read(0x80)==token&&(r.read(0x7c)&3)==0){release();return false;}
   require(ScheduleTime::now()<deadline,"snapshot acquisition timeout");ScheduleTime::sleep_us(1000);
  }
  frame=r.read(0x84);return true;
 }
};
static void set_post(ScheduleMap&r,uint32_t value){
 r.write(0x54,value);auto end=ScheduleTime::now()+std::chrono::seconds(2);
 while(r.read(0x54)!=value||r.read(0x58)!=value){require(ScheduleTime::now()<end,"LCD bank switch timeout");ScheduleTime::sleep_us(1000);}
}
static void dump_bank(ScheduleMap&pl,unsigned bank,const std::string&path){
 std::vector<uint32_t> words(384000);read_words(static_cast<char*>(pl.p)+bank*0x200000,words.data(),words.size());barrier();save(path,words.data(),words.size()*4);
}
// A release during COPYING cancels publication but the bridge must drain its
// accepted AXI responses before another client may use the shared snapshot.
static void drain_snapshot(ScheduleMap&r,Lease&lease){
 // An MMIO request may have been accepted just before a stop. Give its
 // token a bounded propagation interval before canceling that exact request.
 while(lease.token&&r.read(0x80)!=lease.token&&!(r.read(0x7c)&3)&&lease.age_us()<2000)ScheduleTime::sleep_us(100);
 lease.readable=false;lease.release();
 auto end=ScheduleTime::now()+std::chrono::seconds(3);
 while(r.read(0x7c)&3){
  if(ScheduleTime::now()>=end)fail_stop("snapshot did not drain; cold boot is required");
  ScheduleTime::sleep_us(1000);
 }
}
static uint64_t micros_since(Clock::time_point start){return uint64_t(std::chrono::duration_cast<std::chrono::microseconds>(ScheduleTime::now()-start).count());}
static void wait_post(ScheduleMap&r,uint32_t value,Clock::time_point submitted){
 while(r.read(0x54)!=value||r.read(0x58)!=value){
  require(ScheduleTime::now()-submitted<std::chrono::seconds(2),"LCD bank switch timeout");
  ScheduleTime::sleep_us(1000);
 }
}
static void run_live_prefetch(Kernel&kernel,ScheduleMap&regs,ScheduleMap&pl,Lease&lease,uint32_t saved,double seconds,double hold,const std::string&output){
 bool displayed=false,have_input=false;
 unsigned frames=0,retries=0,last_bank=0,loaded_frames=0;
 uint32_t input_tag=0,last_source_frame=0;
 uint64_t load_us=0,compute_us=0,all_load_us=0,input_load_us=0,snapshot_wait_us=0,post_wait_us=0,post_ack_observed_us=0;
 uint64_t estimate_us=0,prefetch_requests=0,fallback_requests=0,prefetch_used=0,prefetch_without_request=0;
 uint64_t prefetch_request_delay_us=0,prefetch_lead_us=0,prefetch_max_lead_us=0,prefetch_ready_at_done=0;
 uint64_t stale_dropped=0,canceled_retries=0,max_request_age_us=0;
 uint64_t duplicate_snapshot_retries=0;bool have_computed_tag=false;uint32_t last_computed_tag=0;
 std::vector<uint64_t> ack_timestamps_us;
 uint32_t initial_expirations=regs.read(0x8c);
 auto started=ScheduleTime::now();
 auto running=[&](){return !stopped()&&std::chrono::duration<double>(ScheduleTime::now()-started).count()<seconds;};
 // During COMPUTE the kernel consumes only its internal cache. A late SNP
 // request writes a different PL buffer and never touches that cache or HR.
 // LOAD remains serialized after COMPUTE and a fresh READY/lease check.
 auto load_next=[&](){
  require(!have_input&&!kernel.inflight,"input preparation overlaps an active kernel/cache");
  auto busy_started=ScheduleTime::now();
  while(running()){
   auto snapshot_start=ScheduleTime::now();
   if(!lease.token){
    if(!lease.request_nonblocking()){
     require(ScheduleTime::now()-busy_started<std::chrono::seconds(3),"snapshot remains busy");
     ScheduleTime::sleep_us(1000);snapshot_wait_us+=micros_since(snapshot_start);continue;
    }
    ++fallback_requests;
   }
   bool acquired=false;
   while(running()){
    max_request_age_us=std::max(max_request_age_us,lease.age_us());
    if(lease.valid_for_load()){lease.frame=regs.read(0x84);acquired=lease.valid_for_load();break;}
    uint32_t status=regs.read(0x7c),token=regs.read(0x80);
    if(token==lease.token&&(status&3)==0){++canceled_retries;break;}
    if(lease.age_us()>=1500000||regs.read(0x8c)!=lease.expiry_at_request||(status&0x100)||(token!=lease.token&&lease.age_us()>=2000)){++stale_dropped;break;}
    require(ScheduleTime::now()-snapshot_start<std::chrono::seconds(3),"snapshot acquisition timeout");
    ScheduleTime::sleep_us(1000);
   }
   snapshot_wait_us+=micros_since(snapshot_start);
   if(!running())return false;
   if(!acquired||!lease.valid_for_load()){
    drain_snapshot(regs,lease);++retries;busy_started=ScheduleTime::now();ScheduleTime::sleep_us(1000);continue;
   }
   // Equal tags represent the same source image, including near wraparound.
   // Never count another upscale of that image as a new FSR output frame.
   if(have_computed_tag&&lease.frame==last_computed_tag){
    drain_snapshot(regs,lease);++duplicate_snapshot_retries;++retries;ScheduleTime::sleep_us(1000);continue;
   }
   bool was_prefetched=lease.prefetched;
   input_tag=lease.frame;
   // No asynchronous cancellation or signal handler can release this lease
   // while the LOAD AXI reader is active. Revalidate again after its AP_DONE.
   lease.readable=true;
   try{input_load_us=kernel.call(0,0x21400000,0,input_tag,input_tag,0,{},[&](){return lease.valid_for_load();});}
   catch(const LeaseLostBeforeLoad&){lease.readable=false;drain_snapshot(regs,lease);++retries;busy_started=ScheduleTime::now();continue;}
   all_load_us+=input_load_us;++loaded_frames;lease.readable=false;
   bool valid=lease.valid_for_load();lease.release();
   if(!valid){kernel.invalidate();drain_snapshot(regs,lease);++retries;busy_started=ScheduleTime::now();continue;}
   if(was_prefetched)++prefetch_used;
   have_input=true;return true;
  }
  return false;
 };
 try{
  load_next();
  while(have_input&&running()){
   // A previously submitted HR bank must be active before selecting the
   // opposite bank. The previous iteration waits for that exact POST value.
   require(regs.read(0x54)==regs.read(0x58),"previous LCD bank switch is pending");
   require(!lease.token&&!lease.readable,"COMPUTE started before previous snapshot release");
   unsigned bank=((regs.read(0x58)>>9)&1)^1;
   uint32_t tag=input_tag;load_us+=input_load_us;have_input=false;
   uint64_t calibrated=estimate_us,request_delay=0;bool issued=false;
   // The first COMPUTE is calibration only. For short kernels, request in
   // their latter half instead of immediately taking an unnecessarily old frame.
   uint64_t request_after=calibrated>12000?calibrated-12000:std::max<uint64_t>(1000,calibrated/2);
   uint32_t elapsed=kernel.call(1,0,0x21000000+bank*0x200000,tag,tag,0,[&](uint64_t progress_us){
    if(calibrated&&progress_us>=request_after&&running()&&!lease.token&&lease.request_nonblocking(true)){
     issued=true;request_delay=progress_us;++prefetch_requests;
    }
   });
   compute_us+=elapsed;estimate_us=elapsed;
   last_computed_tag=tag;have_computed_tag=true;
   if(issued){
    uint64_t lead=elapsed>request_delay?elapsed-request_delay:0;
    prefetch_request_delay_us+=request_delay;prefetch_lead_us+=lead;
    prefetch_max_lead_us=std::max(prefetch_max_lead_us,lead);
    if(lease.valid_for_load())++prefetch_ready_at_done;
   }else if(calibrated)++prefetch_without_request;
   // AP_DONE is downstream of final AXI B, and return/tag were checked above.
   // Publish now; LOAD below touches only input_cache, never either HR bank.
   uint32_t value=2|(bank<<9);auto submitted=ScheduleTime::now();displayed=true;regs.write(0x54,value);
   if(running())load_next();
   auto ack_start=ScheduleTime::now();wait_post(regs,value,submitted);
   post_wait_us+=micros_since(ack_start);post_ack_observed_us+=micros_since(submitted);
   last_bank=bank;last_source_frame=tag;++frames;
   ack_timestamps_us.push_back(micros_since(started));
   if(!running())break;
  }
  // In particular, cancel/drain any unused prefetch before --hold-seconds.
  // Stop requests have already drained the kernel before reaching this point.
  drain_snapshot(regs,lease);
  std::ostringstream cadence_json;
  for(size_t i=0;i<ack_timestamps_us.size();++i){if(i)cadence_json<<',';cadence_json<<ack_timestamps_us[i];}
  double elapsed=std::chrono::duration<double>(ScheduleTime::now()-started).count();
  require(frames>0||stopped(),"no FSR frames processed");
  // ACK may have arrived during source preparation. This observed duration is
  // an upper bound, while post_remaining_wait_us is the unhidden CPU wait.
  std::cout<<"{\"backend\":\"FPGA PL EASU12 + RCAS5 fixed point\",\"schedule\":\"late SNP1 prefetch during COMPUTE; LOAD overlaps POST ACK\",\"frames\":"<<frames<<",\"elapsed_seconds\":"<<elapsed<<",\"processed_fps\":"<<(elapsed>0?frames/elapsed:0)<<",\"input_load_us\":"<<load_us<<",\"compute_us\":"<<compute_us<<",\"snapshot_retries\":"<<retries<<",\"last_source_frame\":"<<last_source_frame<<",\"last_bank\":"<<last_bank<<",\"loaded_frames\":"<<loaded_frames<<",\"all_input_load_us\":"<<all_load_us<<",\"prepared_input_unused\":"<<(have_input?1:0)<<",\"snapshot_wait_us\":"<<snapshot_wait_us<<",\"post_remaining_wait_us\":"<<post_wait_us<<",\"post_ack_observed_us\":"<<post_ack_observed_us<<",\"prefetch_requests\":"<<prefetch_requests<<",\"prefetch_fallback_requests\":"<<fallback_requests<<",\"prefetch_inputs_used\":"<<prefetch_used<<",\"prefetch_without_request\":"<<prefetch_without_request<<",\"prefetch_request_delay_us\":"<<prefetch_request_delay_us<<",\"prefetch_actual_lead_us\":"<<prefetch_lead_us<<",\"prefetch_max_actual_lead_us\":"<<prefetch_max_lead_us<<",\"prefetch_ready_at_compute_done\":"<<prefetch_ready_at_done<<",\"prefetch_stale_dropped\":"<<stale_dropped<<",\"prefetch_canceled_retries\":"<<canceled_retries<<",\"prefetch_max_request_age_us\":"<<max_request_age_us<<",\"unique_source_frames\":"<<frames<<",\"repeated_source_frames\":0,\"duplicate_snapshot_retries\":"<<duplicate_snapshot_retries<<",\"prefetch_lease_expirations\":"<<uint32_t(regs.read(0x8c)-initial_expirations)<<",\"ack_timestamps_us\":["<<cadence_json.str()<<"],\"cpu_pixel_processing_live\":false}"<<std::endl;
  if(!output.empty()&&frames)dump_bank(pl,last_bank,output);
  auto until=ScheduleTime::now()+std::chrono::duration<double>(hold);while(!stopped()&&ScheduleTime::now()<until)ScheduleTime::sleep_us(1000);
  drain_snapshot(regs,lease);
  if(displayed){set_post(regs,saved);displayed=false;}kernel.invalidate();
 }catch(...){
  if(!kernel.inflight){
   drain_snapshot(regs,lease);
   if(displayed){try{set_post(regs,saved);}catch(...){fail_stop("LCD restoration failed; cold boot is required");}}
  }
  throw;
 }
}
#ifndef RIX_FSR_PREFETCH_TEST
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
 if(live){run_live_prefetch(kernel,regs,pl,lease,saved,seconds,hold,output);return 0;}
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
#endif
