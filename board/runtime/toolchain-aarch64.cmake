# Source the matching PetaLinux SDK environment before CMake.
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
if(NOT DEFINED ENV{SDKTARGETSYSROOT} OR NOT DEFINED ENV{CC} OR NOT DEFINED ENV{CXX})
    message(FATAL_ERROR "Source the AXU3EG AArch64 PetaLinux SDK environment first")
endif()
if(NOT "$ENV{CC}" MATCHES "aarch64")
    message(FATAL_ERROR "SDK compiler must target AArch64")
endif()
set(CMAKE_SYSROOT "$ENV{SDKTARGETSYSROOT}")
# CMake imports CC/CXX and their mandatory SDK flags from the environment.
set(CMAKE_FIND_ROOT_PATH "${CMAKE_SYSROOT}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
# SDK executable links are supported. Static-only probes incorrectly report
# pthread symbols as part of libc and omit the required glibc 2.30 thread DSO.
set(THREADS_PREFER_PTHREAD_FLAG TRUE)
