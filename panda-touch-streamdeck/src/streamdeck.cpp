#include "streamdeck.h"
#include "storage.h"
#include "ui_main.h"
#include "ui_dashboard.h"
#include "ble_actions.h"
#include "webserver.h"
#include "ha_client.h"
#include "l10n.h"
#include "pt/pt_display.h"
#include <ArduinoOTA.h>

// The orb lives on the dashboard and just updates its color/pulse in place -
// no screen switching needed for Jarvis state changes anymore. Safe to call
// even while the StreamDeck grid is the active screen (updates an object that
// isn't currently visible; it'll be correct whenever the user returns).
static void handle_ha_state_change(HaAssistState state) {
    set_orb_state(state);
}

void StreamDeckApp::setup() {
    WiFi.mode(WIFI_STA);

    init_storage();
    load_settings();

    g_main_screen = lv_scr_act();
    create_main_ui();

    init_ha_client();
    create_dashboard_ui();
    g_current_screen = SCREEN_DASHBOARD;
    lv_scr_load(g_dashboard_screen);

    Serial.println("StreamDeckApp::setup() - Starting BLE initialization");
    delay(500);

    init_ble();

    ArduinoOTA.onStart([]() {
        pt_enter_ota_mode();
        String type = (ArduinoOTA.getCommand() == U_FLASH) ? "sketch" : "filesystem";
        Serial.println("OTA: Start updating " + type);
    });
    ArduinoOTA.onEnd([]() {
        Serial.println("\nOTA: Update Complete");
    });
    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        (void)progress; (void)total;
    });
    ArduinoOTA.onError([](ota_error_t error) {
        Serial.printf("OTA Error[%u]: ", error);
        if (error == OTA_AUTH_ERROR) Serial.println("Auth Failed");
        else if (error == OTA_BEGIN_ERROR) Serial.println("Begin Failed");
        else if (error == OTA_CONNECT_ERROR) Serial.println("Connect Failed");
        else if (error == OTA_RECEIVE_ERROR) Serial.println("Receive Failed");
        else if (error == OTA_END_ERROR) Serial.println("End Failed");
    });
    ArduinoOTA.begin();
}

void StreamDeckApp::loop() {
    check_ble_status();
    check_wifi_status();
    check_ha_client();

    if (g_ha_state_changed) {
        g_ha_state_changed = false;
        handle_ha_state_change(g_ha_assist_state);
    }

    if (g_ha_tiles_changed) {
        g_ha_tiles_changed = false;
        refresh_dashboard_ui();
    }

    if (g_pending_ui_update) {
        g_pending_ui_update = false;
        if (g_current_screen == SCREEN_GRID) {
            lv_scr_load(g_main_screen);
            create_main_ui();
        } else {
            create_dashboard_ui();
            lv_scr_load(g_dashboard_screen);
        }
    }

    if (g_ota_screen_requested) {
        g_ota_screen_requested = false;
        pt_enter_ota_mode();
    }

    ArduinoOTA.handle();
    yield();
}

void StreamDeckApp::handle_button(uint8_t idx) {
    handle_button_action(idx);
}

void StreamDeckApp::log(const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
}
