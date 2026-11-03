// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "DataTransferCmdBase.hpp"
#include <array>
#include <cstdint>

namespace rr {
// CPU-only opcode. Encode addresses as two 32-bit words because this stream
// guarantees four-byte alignment, not native-pointer alignment.
using PushVertexBatchCmd=DataTransferCmdBase<std::array<uint32_t,2>,0xA0000000u>;
template<class T>inline PushVertexBatchCmd vertexBatchCommand(const T* pointer){
    const uint64_t address=reinterpret_cast<uintptr_t>(pointer);
    return PushVertexBatchCmd(std::array<uint32_t,2>{uint32_t(address),uint32_t(address>>32)});
}
template<class T>inline const T* vertexBatchPointer(const PushVertexBatchCmd& cmd){
    const auto& words=cmd.payload()[0];
    return reinterpret_cast<const T*>(uintptr_t(uint64_t(words[0])|(uint64_t(words[1])<<32)));
}
} // namespace rr
