// RasterIX
// https://github.com/ToNi3141/RasterIX
// Copyright (c) 2025 ToNi3141

// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

#include "GLImpl.h"
#include "RIXGL.hpp"
#include "vertexpipeline/VertexPipeline.hpp"
#include <spdlog/spdlog.h>

using namespace rr;

GLAPI void APIENTRY impl_glGetTexLevelParameterfv(
    [[maybe_unused]] GLenum target,
    [[maybe_unused]] GLint level,
    [[maybe_unused]] GLenum pname,
    [[maybe_unused]] GLfloat* params)
{
    SPDLOG_WARN("glGetTexLevelParameterfv not implemented");
}

GLAPI void APIENTRY impl_glGetTexLevelParameteriv(
    [[maybe_unused]] GLenum target,
    [[maybe_unused]] GLint level,
    [[maybe_unused]] GLenum pname,
    [[maybe_unused]] GLint* params)
{
    if (!params || target != GL_TEXTURE_2D || level < 0 ||
        static_cast<std::size_t>(level) > RIXGL::getInstance().getMaxLOD()) {
        RIXGL::getInstance().setError(GL_INVALID_VALUE); return;
    }
    const auto& texture = RIXGL::getInstance().pipeline().texture().getTexture();
    switch (pname) {
    case GL_TEXTURE_WIDTH: *params = texture.getWidth(level); break;
    case GL_TEXTURE_HEIGHT: *params = texture.getHeight(level); break;
    default: RIXGL::getInstance().setError(GL_INVALID_ENUM); break;
    }
}
