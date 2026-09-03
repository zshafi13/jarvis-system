#pragma once
#ifndef STORAGE_H
#define STORAGE_H

#include <Arduino.h>
#include "constants.h"

struct ButtonConfig {
    char label[16];
    char value[256];
    uint8_t type;
    uint32_t color;
    char icon[8];
    char imgPath[32];
};

struct HaTileConfig {
    char entity_id[48];
    char label[24];
};

extern ButtonConfig g_configs[MAX_BUTTONS];
extern HaTileConfig g_ha_tiles[MAX_HA_TILES];
extern uint32_t g_bg_color;
extern uint8_t g_rows;
extern uint8_t g_cols;
extern uint8_t g_target_os;
extern char g_wifi_ssid[32];
extern char g_wifi_pass[64];
extern uint8_t g_kb_lang;
extern uint8_t g_brightness;
extern String g_wifi_status;
extern String g_ip_addr;
extern char g_ha_host[64];
extern uint16_t g_ha_port;
extern char g_ha_token[300];
extern char g_ha_tz[48];

void init_storage();
void load_settings();
void save_settings(bool saveButtons = true);

#endif
