// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
#include <type_traits>
namespace rix_geometry_r1 {
// Proposed device-resident vertex storage, not an enabled GPU command ABI.
// All fields are IEEE binary32, little-endian; no process pointer/sourceIndex.
// Keep normal/point size for the full frontend, unlike the earlier 64B subset.
struct VertexF32 {
    float position[4];
    float color[4];
    float texture[2][4];
    float normal[3];
    float point_size;
};
static_assert(sizeof(float)==4 && sizeof(VertexF32)==80);
static_assert(std::is_trivially_copyable<VertexF32>::value);
static_assert(offsetof(VertexF32,color)==16 && offsetof(VertexF32,texture)==32);
static_assert(offsetof(VertexF32,normal)==64 && offsetof(VertexF32,point_size)==76);
}
