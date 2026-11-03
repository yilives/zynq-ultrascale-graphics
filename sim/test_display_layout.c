/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "rasterix_display_layout.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    assert(RIX_UI_WIDTH * RIX_CORE_MAX_DISPLAY_HEIGHT ==
           RIX_UI_HEIGHT * RIX_CORE_MAX_DISPLAY_WIDTH);
    for (int x=0; x<RIX_CORE_MAX_DISPLAY_WIDTH; ++x)
        assert(rix_window_x(rix_ui_x(x)) == x);
    for (int y=0; y<RIX_CORE_MAX_DISPLAY_HEIGHT; ++y)
        assert(rix_window_y(rix_ui_y(y)) == y);
    assert(rix_ui_x(0)==0 && rix_ui_y(0)==0);
    assert(rix_ui_x(RIX_CORE_MAX_DISPLAY_WIDTH)==RIX_UI_WIDTH);
    assert(rix_ui_y(RIX_CORE_MAX_DISPLAY_HEIGHT)==RIX_UI_HEIGHT);
    int tile=rix_splash_tile_size();
    for (int x=-1; x<=0; ++x) for (int y=-1; y<=0; ++y) {
        int left=RIX_UI_WIDTH/2+x*tile, bottom=RIX_UI_HEIGHT/2+y*tile;
        assert(left>=0 && bottom>=0);
        assert(left+tile<=RIX_UI_WIDTH && bottom+tile<=RIX_UI_HEIGHT);
    }
    /* Previous fixed 512-square splash overran both axes at 400x240. */
    assert(512>RIX_CORE_MAX_DISPLAY_WIDTH && 512>RIX_CORE_MAX_DISPLAY_HEIGHT);
    printf("DISPLAY_LAYOUT_PASS: UI %dx%d, viewport %dx%d, splash %dx%d, mouse roundtrip 640 points\n",
           RIX_UI_WIDTH,RIX_UI_HEIGHT,RIX_CORE_MAX_DISPLAY_WIDTH,
           RIX_CORE_MAX_DISPLAY_HEIGHT,2*tile,2*tile);
    return 0;
}
