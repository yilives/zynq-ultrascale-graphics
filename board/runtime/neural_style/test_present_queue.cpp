// SPDX-License-Identifier: MIT
#include "present_queue.hpp"
#include <array>
#include <iostream>
#include <string>

static void require(bool ok,const char*why){if(!ok)throw std::runtime_error(why);}
struct Panel;
struct SimTime {
 using Clock=std::chrono::steady_clock;
 static Clock::time_point instant;
 static Panel*panel;
 static auto now(){return instant;}
 static void advance(unsigned milliseconds);
 static void pause(){advance(1);}
};
SimTime::Clock::time_point SimTime::instant{};
Panel*SimTime::panel=nullptr;
struct Panel {
 uint32_t active=0,requested=0;
 std::array<unsigned,2> memory{{0,0}};
 unsigned visible=0,delay=17,writes=0,acknowledged=0;
 bool pending=false,ack_enabled=true;
 SimTime::Clock::time_point due;
 uint32_t read(unsigned offset){require(offset==0x58,"invalid read");return active;}
 void write(unsigned offset,uint32_t value){
  require(offset==0x54&&!pending,"overwritten pending flip");
  require(((value>>9)&1)!=((active>>9)&1),"submitted active bank");
  requested=value;due=SimTime::now()+std::chrono::milliseconds(delay);pending=true;writes++;
 }
 void tick(){
  require(memory[(active>>9)&1]==visible,"scanout buffer was overwritten");
  if(pending&&ack_enabled&&SimTime::now()>=due){
   active=requested;visible=memory[(active>>9)&1];pending=false;acknowledged++;
  }
 }
 void fill(unsigned bank,unsigned frame){
  tick();require(bank!=((active>>9)&1),"writing active bank");
  require(!pending||bank!=((requested>>9)&1),"writing submitted bank before acknowledgement");
  memory[bank]=frame;
 }
};
void SimTime::advance(unsigned milliseconds){instant+=std::chrono::milliseconds(milliseconds);panel->tick();}

static void run(bool overlap,unsigned initial_bank,uint32_t mode){
 Panel panel;panel.active=mode|(initial_bank<<9);SimTime::instant={};SimTime::panel=&panel;
 rix_pl::PresentQueue<Panel,SimTime> queue(panel,mode,overlap);
 unsigned expected=initial_bank^1;
 for(unsigned frame=1;frame<=200;frame++){
  // Include inference shorter and longer than a refresh, and an abnormally
  // delayed ACK. A producer must never overwrite either front or queued bank.
  panel.delay=frame%13==0?250:frame%23+1;
  auto bank=queue.acquire();require(bank==expected,"bank did not alternate");expected^=1;
  panel.fill(bank,frame);auto before=SimTime::now();queue.submit(bank);
  if(overlap)require(SimTime::now()==before,"submit blocked before useful CPU work");
  else require(!panel.pending&&panel.visible==frame,"blocking mode returned before ACK");
  if(frame!=200)SimTime::advance(frame%3==0?40:3);
 }
 // Simulate duration/SIGTERM immediately after the final submit: finish must
 // retire exactly that frame, rather than reporting merely submitted FPS.
 queue.finish();
 require(panel.visible==200&&!panel.pending,"last frame was not scanned");
 require(queue.submitted()==200&&queue.completed()==200&&panel.acknowledged==200,"frame counts differ");
 require(queue.wait_seconds()>0,"wait accounting missing");
 bool rejected=false;try{queue.submit(0);}catch(const std::runtime_error&){rejected=true;}
 require(rejected&&panel.writes==200,"accepted submission without bank ownership");
}
int main(){try{
 for(auto mode:{2u,3u})for(auto bank:{0u,1u})for(auto overlap:{false,true})run(overlap,bank,mode);
 Panel panel;SimTime::instant={};SimTime::panel=&panel;panel.ack_enabled=false;
 rix_pl::PresentQueue<Panel,SimTime> queue(panel,3,true);
 auto bank=queue.acquire();panel.fill(bank,1);queue.submit(bank);
 bool timed_out=false;try{queue.acquire();}catch(const std::runtime_error&e){timed_out=std::string(e.what())=="native output flip timeout";}
 require(timed_out&&panel.memory[0]==0&&panel.writes==1&&queue.completed()==0,"timeout allowed unsafe reuse or counted unseen frame");
 std::cout<<"PRESENT_QUEUE_OWNERSHIP_PASS frames=1600 modes=2 banks=2 delayed_ack final_drain timeout\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
