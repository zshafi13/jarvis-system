#pragma once
#ifndef HA_CLIENT_H
#define HA_CLIENT_H

#include "constants.h"

enum HaAssistState {
    HA_ASSIST_UNKNOWN = 0,
    HA_ASSIST_IDLE,
    HA_ASSIST_LISTENING,
    HA_ASSIST_PROCESSING,
    HA_ASSIST_RESPONDING
};

extern volatile bool g_ha_state_changed;
extern volatile HaAssistState g_ha_assist_state;
extern volatile bool g_ha_connected;

// Mirrors g_ha_tiles[] in storage.h by index. Set from the initial REST fetch
// on connect and kept live afterward via each tile's own subscribe_trigger.
extern volatile bool g_ha_tile_on[MAX_HA_TILES];
extern volatile bool g_ha_tiles_changed;

// Fires a generic homeassistant.toggle service call for this entity. No
// optimistic UI update - the tile's own subscription reports the result.
void ha_toggle_entity(const char* entity_id);

// Set this (never call start/stop_ha_client directly) from any context that
// isn't the main Arduino task - e.g. the AsyncWebServer /api/save handler,
// which runs on the network task. Opening/closing a socket from that context
// can stall the whole network stack. check_ha_client() (main loop) picks this
// up and does the actual restart safely.
extern volatile bool g_ha_restart_requested;

// Registers the WebSocket event handler. Call once during setup(), before WiFi connects.
void init_ha_client();

// Opens (or re-opens) the connection using the current g_ha_host/g_ha_port/g_ha_token.
// Call on the WiFi connected edge, and again after HA settings are changed via the web dashboard.
void start_ha_client();

// Tears down the connection. Call on the WiFi disconnected edge.
void stop_ha_client();

// Non-blocking, cheap to call every loop tick.
void check_ha_client();

#endif
