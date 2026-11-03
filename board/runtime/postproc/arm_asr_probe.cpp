// SPDX-License-Identifier: MIT
#include "ffxm_fsr2.h"
#include <cmath>
#include <iostream>
#include <vector>
using namespace arm;
int main(){
 int phases=ffxmFsr2GetJitterPhaseCount(400,800);if(phases<=0)return 1;
 for(int i=0;i<phases;i++){float x=0,y=0;if(ffxmFsr2GetJitterOffset(&x,&y,i,phases)!=FFXM_OK||!std::isfinite(x)||!std::isfinite(y)||std::abs(x)>.5||std::abs(y)>.5)return 2;}
 auto context=new FfxmFsr2Context{};FfxmFsr2ContextDescription desc{};desc.maxRenderSize={400,240};desc.displaySize={800,480};
 auto result=ffxmFsr2ContextCreate(context,&desc);delete context;
 if(result!=FFXM_ERROR_INCOMPLETE_INTERFACE){std::cerr<<"Unexpected backend validation result "<<result<<'\n';return 3;}
 std::cout<<"{\"arm_asr_official_api\":\"linked_and_executed\",\"render_width\":400,\"display_width\":800,\"jitter_phases\":"<<phases<<",\"backend_validation\":\"FFXM_ERROR_INCOMPLETE_INTERFACE\",\"rendering_available\":false,\"missing\":[\"shader execution backend\",\"per pixel motion vectors\",\"32bit depth export\",\"camera jitter integration\"]}\n";
}
