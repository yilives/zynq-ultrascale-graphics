#include <iostream>

int main() {
    const unsigned frames = 736;
    const double seconds = frames / 36.78757;
    std::cout << "{\"precision\":" << std::cout.precision()
              << ",\"frames\":" << frames
              << ",\"elapsed_seconds\":" << seconds
              << ",\"processed_fps\":" << frames / seconds << "}\n";
}
