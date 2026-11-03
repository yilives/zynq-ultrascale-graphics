// SPDX-License-Identifier: MIT
#include "stage_bilinear.hpp"
#include <fstream>
#include <iostream>
int main(int argc,char**argv){try{
 if(argc!=3)return 2;std::vector<uint32_t> source(96000),output(384000);
 std::ifstream f(argv[1],std::ios::binary);f.read(reinterpret_cast<char*>(source.data()),384000);if(!f||f.peek()!=EOF)return 3;
 rix_frames::StageBilinear2 scaler;scaler.upscale(source,output);std::ofstream g(argv[2],std::ios::binary);
 g.write(reinterpret_cast<const char*>(output.data()),1536000);if(!g)return 4;
 std::cout<<"BILINEAR_STAGE_REFERENCE_PASS 384000\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
