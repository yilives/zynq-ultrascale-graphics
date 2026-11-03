// SPDX-License-Identifier: MIT
#include "rix_fsr1_hls.hpp"
#include <fstream>
#include <iostream>
#include <vector>
int main(int argc,char**argv){
 if(argc!=3)return 2;std::vector<uint32_t> source(96000),output(384000);std::ifstream f(argv[1],std::ios::binary);
 f.read(reinterpret_cast<char*>(source.data()),384000);if(!f||f.peek()!=EOF)return 3;
 uint32_t tag=0;if(rix_fsr1_hls(2,nullptr,nullptr,0,tag)||rix_fsr1_hls(0,source.data(),nullptr,7,tag)||tag!=7)return 4;
 if(rix_fsr1_hls(1,nullptr,output.data(),0,tag)||tag!=7)return 5;
 std::ofstream g(argv[2],std::ios::binary);g.write(reinterpret_cast<char*>(output.data()),1536000);if(!g)return 6;
 std::cout<<"FSR_FIXED_V23_REFERENCE_PASS 384000\n";return 0;
}
