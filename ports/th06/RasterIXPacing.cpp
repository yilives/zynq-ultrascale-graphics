// SPDX-License-Identifier: GPL-3.0-or-later
#include "GameWindow.hpp"
#include "AnmManager.hpp"
#include "Chain.hpp"
#include "SoundPlayer.hpp"
#include "Stage.hpp"
#include "Supervisor.hpp"
#include <SDL2/SDL.h>
#include <algorithm>
#include <chrono>
#include <cstdio>

// The existing SwapBuffers waits for a real FPGA presentation acknowledgement.
// Account for that elapsed time once; the upstream loop otherwise adds another
// timer wait after a blocking swap and often drops from 30 to 20 rendered FPS.
int RasterIXRenderFrame()
{
    using Clock = std::chrono::steady_clock;
    constexpr double step = 1.0 / 60.0;
    static auto previous = Clock::now();
    static double pending = step;
    static unsigned dropped = 0;
    const auto now = Clock::now();
    pending += std::chrono::duration<double>(now - previous).count();
    previous = now;
    if (!g_GameWindow.lastActiveAppValue)
    {
        pending = 0;
        SDL_Delay(1);
        return RENDER_RESULT_KEEP_RUNNING;
    }
    // Bound catch-up to avoid a spiral after loading assets or a paused process.
    if (pending > 6 * step)
    {
        pending = 6 * step;
        ++dropped;
        std::fprintf(stderr, "TH06_LOGIC_CATCHUP_CLAMP count=%u\n", dropped);
    }
    if (pending < step)
    {
        SDL_Delay(1);
        return RENDER_RESULT_KEEP_RUNNING;
    }
    g_Supervisor.framerateMultiplier = 1.0f;
    g_Supervisor.effectiveFramerateMultiplier = 1.0f;
    while (pending >= step)
    {
        const int result = g_Chain.RunCalcChain();
        g_SoundPlayer.PlaySounds();
        pending -= step;
        if (result == 0) return RENDER_RESULT_EXIT_SUCCESS;
        if (result == -1) return RENDER_RESULT_EXIT_ERROR;
    }
    ZunViewport viewport;
    viewport.x = viewport.y = 0;
    viewport.width = GAME_WINDOW_WIDTH;
    viewport.height = GAME_WINDOW_HEIGHT;
    viewport.minZ = 0.0;
    viewport.maxZ = 1.0;
    viewport.Set();
    const auto color = g_Stage.skyFog.color;
    g_GfxBackend->SetClearColor(((color >> 16) & 255) / 255.f,
                               ((color >> 8) & 255) / 255.f,
                               (color & 255) / 255.f, (color >> 24) / 255.f);
    g_GfxBackend->Clear(CLEAR_COLOR_BUFFER | CLEAR_DEPTH_BUFFER);
    g_AnmManager->SetProjectionMode(PROJECTION_MODE_PERSPECTIVE);
    g_Supervisor.viewport.Set();
    g_AnmManager->ClearVertexBuffer();
    g_AnmManager->flushesThisFrame = 0;
    g_Chain.RunDrawChain();
    g_AnmManager->SetCurrentTexture(0);
    g_AnmManager->FlushVertexBuffer();
    GameWindow::Present();
    return RENDER_RESULT_KEEP_RUNNING;
}
