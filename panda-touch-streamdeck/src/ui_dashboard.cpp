#include "ui_dashboard.h"
#include "ui_main.h"
#include "storage.h"
#include <time.h>

#define ORB_CORE_SIZE 170
#define ORB_GLOW_SIZE 260
#define TILE_W 76
#define TILE_H 64

lv_obj_t* g_dashboard_screen = nullptr;

static lv_obj_t* g_clock_label = nullptr;
static lv_obj_t* g_status_label = nullptr;
static lv_obj_t* g_open_grid_btn = nullptr;
static lv_obj_t* g_orb_glow = nullptr;
static lv_obj_t* g_orb_core = nullptr;
static lv_obj_t* g_tile_row = nullptr;
static lv_obj_t* g_tile_btns[MAX_HA_TILES] = {nullptr};
static lv_timer_t* g_clock_timer = nullptr;

static void open_grid_cb(lv_event_t* e) {
    g_current_screen = SCREEN_GRID;
    refresh_main_ui();
    lv_scr_load(g_main_screen);
}

static void dashboard_gesture_cb(lv_event_t* e) {
    lv_indev_t* indev = lv_indev_active();
    if (!indev) return;
    if (lv_indev_get_gesture_dir(indev) == LV_DIR_LEFT) {
        g_current_screen = SCREEN_GRID;
        refresh_main_ui();
        lv_scr_load(g_main_screen);
    }
}

static void tile_event_cb(lv_event_t* e) {
    uint8_t idx = (uint8_t)(uintptr_t)lv_event_get_user_data(e);
    if (idx >= MAX_HA_TILES) return;
    ha_toggle_entity(g_ha_tiles[idx].entity_id);
}

static void clock_timer_cb(lv_timer_t* t) {
    if (!g_clock_label) return;
    time_t now = time(nullptr);
    struct tm timeinfo;
    localtime_r(&now, &timeinfo);
    char buf[16];
    strftime(buf, sizeof(buf), "%H:%M:%S", &timeinfo);
    lv_label_set_text(g_clock_label, buf);
}

// Static (non-animated) orb appearance per state - a continuous per-frame
// pulse (animating transform_zoom + a blurred, uncached shadow every tick)
// was visibly laggy on this hardware, so state changes just recolor the orb
// once instead of driving a running animation.
static void set_orb_color(uint32_t color, lv_opa_t glow_opa) {
    if (!g_orb_core || !g_orb_glow) return;
    lv_obj_set_style_bg_color(g_orb_core, lv_color_hex(color), 0);
    lv_obj_set_style_bg_color(g_orb_glow, lv_color_hex(color), 0);
    lv_obj_set_style_shadow_color(g_orb_core, lv_color_hex(color), 0);
    lv_obj_set_style_opa(g_orb_glow, glow_opa, 0);
}

void set_orb_state(HaAssistState state) {
    switch (state) {
        case HA_ASSIST_LISTENING:  set_orb_color(THEME_CYAN, 160); break;
        case HA_ASSIST_PROCESSING: set_orb_color(THEME_AMBER, 190); break;
        case HA_ASSIST_RESPONDING: set_orb_color(THEME_GREEN, 170); break;
        default:                   set_orb_color(THEME_CYAN_DIM, 90); break; // idle/unknown
    }
}

void create_dashboard_ui() {
    if (!g_dashboard_screen) {
        g_dashboard_screen = lv_obj_create(NULL);
        lv_obj_add_event_cb(g_dashboard_screen, dashboard_gesture_cb, LV_EVENT_GESTURE, NULL);
    }
    lv_obj_clean(g_dashboard_screen);
    lv_obj_set_style_bg_color(g_dashboard_screen, lv_color_hex(THEME_BG), LV_PART_MAIN);

    // Slim header: clock left, WiFi/HA status + Deck button right.
    lv_obj_t* header = lv_obj_create(g_dashboard_screen);
    lv_obj_set_size(header, lv_pct(100), 40);
    lv_obj_align(header, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_set_style_bg_opa(header, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(header, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(header, 8, LV_PART_MAIN);
    lv_obj_set_flex_flow(header, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(header, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    g_clock_label = lv_label_create(header);
    lv_obj_set_style_text_color(g_clock_label, lv_color_hex(THEME_TEXT), 0);
    lv_obj_set_style_text_font(g_clock_label, &lv_font_montserrat_18, 0);
    lv_label_set_text(g_clock_label, "--:--:--");

    lv_obj_t* right_row = lv_obj_create(header);
    lv_obj_set_size(right_row, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_style_bg_opa(right_row, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(right_row, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(right_row, 0, LV_PART_MAIN);
    lv_obj_set_flex_flow(right_row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(right_row, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    g_status_label = lv_label_create(right_row);
    lv_obj_set_style_text_color(g_status_label, lv_color_hex(THEME_CYAN_DIM), 0);
    lv_obj_set_style_text_font(g_status_label, &lv_font_montserrat_12, 0);
    lv_obj_set_style_pad_right(g_status_label, 10, 0);

    g_open_grid_btn = lv_btn_create(right_row);
    lv_obj_set_style_bg_color(g_open_grid_btn, lv_color_hex(THEME_BG_PANEL), LV_PART_MAIN);
    lv_obj_set_style_border_color(g_open_grid_btn, lv_color_hex(THEME_BORDER), LV_PART_MAIN);
    lv_obj_set_style_border_width(g_open_grid_btn, 1, LV_PART_MAIN);
    lv_obj_t* lbl = lv_label_create(g_open_grid_btn);
    lv_obj_set_style_text_color(lbl, lv_color_hex(THEME_TEXT), 0);
    lv_label_set_text(lbl, "Deck");
    lv_obj_add_event_cb(g_open_grid_btn, open_grid_cb, LV_EVENT_CLICKED, NULL);

    // Central pulsing orb - glow ring behind a solid core, both animated.
    g_orb_glow = lv_obj_create(g_dashboard_screen);
    lv_obj_set_size(g_orb_glow, ORB_GLOW_SIZE, ORB_GLOW_SIZE);
    lv_obj_set_style_radius(g_orb_glow, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_border_width(g_orb_glow, 0, 0);
    lv_obj_set_style_shadow_width(g_orb_glow, 40, 0);
    lv_obj_set_style_shadow_spread(g_orb_glow, 10, 0);
    lv_obj_align(g_orb_glow, LV_ALIGN_CENTER, 0, -20);
    lv_obj_clear_flag(g_orb_glow, LV_OBJ_FLAG_CLICKABLE);

    g_orb_core = lv_obj_create(g_dashboard_screen);
    lv_obj_set_size(g_orb_core, ORB_CORE_SIZE, ORB_CORE_SIZE);
    lv_obj_set_style_radius(g_orb_core, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_border_width(g_orb_core, 0, 0);
    lv_obj_set_style_shadow_width(g_orb_core, 30, 0);
    lv_obj_set_style_shadow_spread(g_orb_core, 4, 0);
    lv_obj_set_style_transform_pivot_x(g_orb_core, ORB_CORE_SIZE / 2, 0);
    lv_obj_set_style_transform_pivot_y(g_orb_core, ORB_CORE_SIZE / 2, 0);
    lv_obj_align(g_orb_core, LV_ALIGN_CENTER, 0, -20);
    lv_obj_clear_flag(g_orb_core, LV_OBJ_FLAG_CLICKABLE);

    // Bottom row of "lab controls" - configured HA entity tiles.
    g_tile_row = lv_obj_create(g_dashboard_screen);
    lv_obj_set_size(g_tile_row, lv_pct(100), 90);
    lv_obj_align(g_tile_row, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_opa(g_tile_row, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(g_tile_row, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(g_tile_row, 8, LV_PART_MAIN);
    lv_obj_set_style_pad_gap(g_tile_row, 8, LV_PART_MAIN);
    lv_obj_set_flex_flow(g_tile_row, LV_FLEX_FLOW_ROW_WRAP);
    lv_obj_set_flex_align(g_tile_row, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_clear_flag(g_tile_row, LV_OBJ_FLAG_SCROLLABLE);

    memset(g_tile_btns, 0, sizeof(g_tile_btns));
    for (int i = 0; i < MAX_HA_TILES; i++) {
        if (g_ha_tiles[i].entity_id[0] == '\0') continue;

        lv_obj_t* btn = lv_btn_create(g_tile_row);
        lv_obj_set_size(btn, TILE_W, TILE_H);
        lv_obj_set_style_border_width(btn, 1, LV_PART_MAIN);
        lv_obj_set_style_border_color(btn, lv_color_hex(THEME_BORDER), LV_PART_MAIN);
        lv_obj_set_style_bg_color(btn, lv_color_hex(g_ha_tile_on[i] ? THEME_CYAN : THEME_BG_PANEL), LV_PART_MAIN);
        lv_obj_set_style_shadow_color(btn, lv_color_hex(THEME_CYAN), LV_PART_MAIN);
        lv_obj_set_style_shadow_width(btn, g_ha_tile_on[i] ? 14 : 0, LV_PART_MAIN);

        lv_obj_t* tile_label = lv_label_create(btn);
        lv_obj_set_style_text_color(tile_label, lv_color_hex(g_ha_tile_on[i] ? THEME_BG : THEME_TEXT), 0);
        lv_obj_set_style_text_font(tile_label, &lv_font_montserrat_12, 0);
        lv_obj_set_style_text_align(tile_label, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_set_width(tile_label, TILE_W - 10);
        const char* text = g_ha_tiles[i].label[0] ? g_ha_tiles[i].label : g_ha_tiles[i].entity_id;
        lv_label_set_text(tile_label, text);
        lv_obj_center(tile_label);

        lv_obj_add_event_cb(btn, tile_event_cb, LV_EVENT_CLICKED, (void*)(uintptr_t)i);
        g_tile_btns[i] = btn;
    }

    if (!g_clock_timer) {
        g_clock_timer = lv_timer_create(clock_timer_cb, 1000, NULL);
    }

    set_orb_state(g_ha_assist_state);
    refresh_dashboard_ui();
}

void refresh_dashboard_ui() {
    if (!g_dashboard_screen) return;
    if (g_status_label) {
        String t = g_wifi_status + " / " + (g_ha_connected ? "HA OK" : "HA --");
        lv_label_set_text(g_status_label, t.c_str());
    }
    for (int i = 0; i < MAX_HA_TILES; i++) {
        if (!g_tile_btns[i]) continue;
        bool on = g_ha_tile_on[i];
        lv_obj_set_style_bg_color(g_tile_btns[i], lv_color_hex(on ? THEME_CYAN : THEME_BG_PANEL), LV_PART_MAIN);
        lv_obj_set_style_shadow_width(g_tile_btns[i], on ? 14 : 0, LV_PART_MAIN);
        lv_obj_t* tile_label = lv_obj_get_child(g_tile_btns[i], 0);
        if (tile_label) lv_obj_set_style_text_color(tile_label, lv_color_hex(on ? THEME_BG : THEME_TEXT), 0);
    }
}
