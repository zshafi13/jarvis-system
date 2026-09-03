#pragma once
#ifndef UI_DASHBOARD_H
#define UI_DASHBOARD_H

#include <lvgl.h>
#include "ha_client.h"

extern lv_obj_t* g_dashboard_screen;

// Creates the dashboard screen the first time, rebuilds its children on
// subsequent calls (mirrors create_main_ui()'s lv_obj_clean()+rebuild pattern).
// Does not itself call lv_scr_load() - the caller decides when to switch to it.
void create_dashboard_ui();

// Cheap refresh of the clock/status labels and entity tile colors without
// rebuilding the whole screen.
void refresh_dashboard_ui();

// Updates the central orb's color/pulse speed/intensity for the given Jarvis
// state. Safe to call even when the dashboard isn't the active screen.
void set_orb_state(HaAssistState state);

#endif
