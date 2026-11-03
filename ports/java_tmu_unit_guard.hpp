// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "RenderConfigs.hpp"
#include "RIXGL.hpp"
// Invalid fixed-function units must not mutate any current unit or array.
static bool javaValidTextureUnit(const GLenum unit)
{
    if (unit >= GL_TEXTURE0 && unit - GL_TEXTURE0 < rr::RenderConfig::TMU_COUNT) return true;
    rr::RIXGL::getInstance().setError(GL_INVALID_ENUM);
    return false;
}
