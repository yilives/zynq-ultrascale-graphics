cmake_minimum_required(VERSION 3.16)
project(RasterIXTH06 LANGUAGES C CXX)
find_package(Threads REQUIRED)
include("${TH06_WORK}/rix_flags.cmake")
file(GLOB game_sources "${TH06_WORK}/source/src/*.cpp")
file(GLOB archive_sources "${TH06_WORK}/source/src/pbg3/*.cpp")
add_executable(th06-rix ${game_sources} ${archive_sources}
    "${TH06_WORK}/source/src/graphics/FixedFunctionGL.cpp"
    "${TH06_WORK}/source/src/graphics/GLFunc.cpp"
    "${TH06_WORK}/source/src/thirdparty/sjis_converter.cpp"
    "${TH06_WORK}/source/src/midi/MidiDefault.cpp"
    RasterIXBackend.cpp RasterIXPacing.cpp RasterIXTextures.cpp RasterIXAtlasQA.cpp RasterIXInput.cpp)
target_compile_features(th06-rix PRIVATE cxx_std_17)
target_compile_options(th06-rix PRIVATE -O3 -Wno-narrowing)
target_compile_definitions(th06-rix PRIVATE ${RIX_IMPORTED_DEFINITIONS}
    RIX_TH06=1 SDL_FLOATWORDORDER=SDL_BYTEORDER GAME_WINDOW_WIDTH_REAL=400 GAME_WINDOW_HEIGHT_REAL=240)
target_include_directories(th06-rix PRIVATE ${RIX_IMPORTED_INCLUDES}
    "${TH06_WORK}/source/src" "${CMAKE_CURRENT_SOURCE_DIR}"
    "${RIX_PROJECT_ROOT}/linux/include"
    "${RIX_PROJECT_ROOT}/build/touhou/runtime/include"
    "${RIX_PROJECT_ROOT}/build/game-ports/runtime/include")
set(runtime "${RIX_PROJECT_ROOT}/build/touhou/runtime/lib")
set(rix_static "${RIX_PROJECT_ROOT}/build/tuxracer-aarch64/RasterIX/lib")
# The shared GLX library creates its own DMA owner before main(). This backend
# owns the context explicitly and resolves GL entry points through RIXGL.
target_link_libraries(th06-rix PRIVATE
    "${rix_static}/gl/libgl.a"
    "${rix_static}/driver/dmaproxy/libdmaproxy.a"
    "${rix_static}/3rdParty/spdlog-1.10.0/libspdlog.a"
    "${rix_static}/gl/libgl.a"
    "${rix_static}/3rdParty/spdlog-1.10.0/libspdlog.a"
    "${runtime}/libSDL2_image.so" "${runtime}/libSDL2_ttf.so" "${runtime}/libSDL2.so" Threads::Threads m)
target_link_options(th06-rix PRIVATE "-Wl,-rpath-link,${runtime}")
set_target_properties(th06-rix PROPERTIES SKIP_BUILD_RPATH TRUE)
