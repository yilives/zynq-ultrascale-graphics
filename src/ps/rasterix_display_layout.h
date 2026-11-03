/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef RASTERIX_DISPLAY_LAYOUT_H
#define RASTERIX_DISPLAY_LAYOUT_H

/* The legacy UI needs a 480-line canvas. Render it at half size, then the
 * existing PL scaler repeats each pixel twice on the 800x480 LCD. Keep the
 * same 5:3 aspect ratio in UI, perspective projection and physical output. */
enum { RIX_UI_WIDTH = 800, RIX_UI_HEIGHT = 480 };
#if RIX_CORE_MAX_DISPLAY_WIDTH != 400 || RIX_CORE_MAX_DISPLAY_HEIGHT != 240
#error "Update the LCD layout when changing the board render profile"
#endif
static inline int rix_ui_x(int x) {
    return x * RIX_UI_WIDTH / RIX_CORE_MAX_DISPLAY_WIDTH;
}
static inline int rix_ui_y(int y) {
    return y * RIX_UI_HEIGHT / RIX_CORE_MAX_DISPLAY_HEIGHT;
}
static inline int rix_window_x(int x) {
    return x * RIX_CORE_MAX_DISPLAY_WIDTH / RIX_UI_WIDTH;
}
static inline int rix_window_y(int y) {
    return y * RIX_CORE_MAX_DISPLAY_HEIGHT / RIX_UI_HEIGHT;
}
static inline int rix_splash_tile_size(void) {
    /* Four square tiles form the complete splash, including its start text. */
    return (RIX_UI_WIDTH < RIX_UI_HEIGHT ? RIX_UI_WIDTH : RIX_UI_HEIGHT) / 2;
}
#endif
