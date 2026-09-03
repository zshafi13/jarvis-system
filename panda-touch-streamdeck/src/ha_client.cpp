#include "ha_client.h"
#include "storage.h"
#include <Arduino.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <esp_task_wdt.h>

// Fixed entity this device tracks for the Jarvis waveform. See
// panda-touch-ui/panda-touch.yaml in the jarvis-system repo for where this came from.
static const char* HA_ASSIST_ENTITY_ID = "assist_satellite.jarvis_pi3_2";

volatile bool g_ha_state_changed = false;
volatile HaAssistState g_ha_assist_state = HA_ASSIST_UNKNOWN;
volatile bool g_ha_connected = false;
volatile bool g_ha_restart_requested = false;
volatile bool g_ha_tile_on[MAX_HA_TILES] = {false};
volatile bool g_ha_tiles_changed = false;

static WebSocketsClient g_ws;
static uint32_t g_next_msg_id = 1;
static bool g_ha_should_run = false;

static HaAssistState parse_state(const char* s) {
    if (!s) return HA_ASSIST_UNKNOWN;
    if (strcmp(s, "idle") == 0) return HA_ASSIST_IDLE;
    if (strcmp(s, "listening") == 0) return HA_ASSIST_LISTENING;
    if (strcmp(s, "processing") == 0) return HA_ASSIST_PROCESSING;
    if (strcmp(s, "responding") == 0) return HA_ASSIST_RESPONDING;
    return HA_ASSIST_UNKNOWN;
}

static void send_auth() {
    JsonDocument doc;
    doc["type"] = "auth";
    doc["access_token"] = g_ha_token;
    String out;
    serializeJson(doc, out);
    g_ws.sendTXT(out);
}

static void subscribe_entity(const char* entity_id) {
    if (!entity_id || entity_id[0] == '\0') return;
    JsonDocument doc;
    doc["id"] = g_next_msg_id++;
    doc["type"] = "subscribe_trigger";
    JsonObject trigger = doc["trigger"].to<JsonObject>();
    trigger["platform"] = "state";
    trigger["entity_id"] = entity_id;
    String out;
    serializeJson(doc, out);
    g_ws.sendTXT(out);
}

static void subscribe_all() {
    subscribe_entity(HA_ASSIST_ENTITY_ID);
    for (int i = 0; i < MAX_HA_TILES; i++) {
        subscribe_entity(g_ha_tiles[i].entity_id);
    }
    Serial.println("HA: subscribed to assist_satellite + configured tiles");
}

// Bounded, one-time sequence of small REST GETs right after auth - subscribe_trigger
// only reports *future* changes, so this is how tiles get their current on/off
// state at connect time. Runs on the main task; esp_task_wdt_reset()/yield()
// between requests mirror the pattern already used for long-ish blocking work
// in the OTA handler (webserver.cpp).
static void fetch_initial_tile_states() {
    for (int i = 0; i < MAX_HA_TILES; i++) {
        const char* entity_id = g_ha_tiles[i].entity_id;
        if (entity_id[0] == '\0') continue;

        HTTPClient http;
        String url = "http://" + String(g_ha_host) + ":" + String(g_ha_port) + "/api/states/" + String(entity_id);
        http.begin(url);
        http.addHeader("Authorization", "Bearer " + String(g_ha_token));
        int code = http.GET();
        if (code == 200) {
            JsonDocument doc;
            DeserializationError err = deserializeJson(doc, http.getString());
            if (!err) {
                const char* state = doc["state"] | "";
                g_ha_tile_on[i] = (strcmp(state, "on") == 0);
                g_ha_tiles_changed = true;
            }
        } else {
            Serial.printf("HA: initial state fetch for %s failed (HTTP %d)\n", entity_id, code);
        }
        http.end();

        esp_task_wdt_reset();
        yield();
    }
}

static int find_tile_index(const char* entity_id) {
    for (int i = 0; i < MAX_HA_TILES; i++) {
        if (strcmp(g_ha_tiles[i].entity_id, entity_id) == 0) return i;
    }
    return -1;
}

static void handle_text(uint8_t* payload, size_t length) {
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, payload, length);
    if (err) {
        Serial.printf("HA: JSON parse error: %s\n", err.c_str());
        return;
    }

    const char* type = doc["type"] | "";

    if (strcmp(type, "auth_required") == 0) {
        send_auth();
    } else if (strcmp(type, "auth_ok") == 0) {
        g_ha_connected = true;
        Serial.println("HA: auth_ok");
        subscribe_all();
        fetch_initial_tile_states();
    } else if (strcmp(type, "auth_invalid") == 0) {
        g_ha_connected = false;
        Serial.println("HA: auth_invalid - check the access token in the web config");
    } else if (strcmp(type, "event") == 0) {
        JsonVariant to_state = doc["event"]["variables"]["trigger"]["to_state"];
        if (to_state.isNull()) to_state = doc["event"]["to_state"];

        const char* entity_id = to_state["entity_id"] | "";
        const char* state_str = to_state["state"] | "";
        if (entity_id[0] == '\0') return;

        if (strcmp(entity_id, HA_ASSIST_ENTITY_ID) == 0) {
            HaAssistState st = parse_state(state_str);
            if (st != HA_ASSIST_UNKNOWN) {
                g_ha_assist_state = st;
                g_ha_state_changed = true;
            }
        } else {
            int idx = find_tile_index(entity_id);
            if (idx >= 0) {
                g_ha_tile_on[idx] = (strcmp(state_str, "on") == 0);
                g_ha_tiles_changed = true;
            }
        }
    }
}

static void ha_ws_event(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_CONNECTED:
            Serial.println("HA: WebSocket connected, awaiting auth_required");
            break;
        case WStype_DISCONNECTED:
            g_ha_connected = false;
            Serial.println("HA: WebSocket disconnected");
            break;
        case WStype_TEXT:
            handle_text(payload, length);
            break;
        default:
            break;
    }
}

void init_ha_client() {
    g_ws.onEvent(ha_ws_event);
    g_ws.setReconnectInterval(5000);
}

void start_ha_client() {
    if (strlen(g_ha_host) == 0 || strlen(g_ha_token) == 0) {
        Serial.println("HA: host/token not configured, skipping connect");
        g_ha_should_run = false;
        return;
    }
    g_ha_should_run = true;
    g_next_msg_id = 1;
    g_ws.begin(g_ha_host, g_ha_port, "/api/websocket");
}

void stop_ha_client() {
    g_ha_should_run = false;
    g_ha_connected = false;
    g_ws.disconnect();
}

void check_ha_client() {
    if (g_ha_restart_requested) {
        g_ha_restart_requested = false;
        stop_ha_client();
        start_ha_client();
    }
    if (!g_ha_should_run) return;
    g_ws.loop();
}

void ha_toggle_entity(const char* entity_id) {
    if (!g_ha_connected || !entity_id || entity_id[0] == '\0') return;

    JsonDocument doc;
    doc["id"] = g_next_msg_id++;
    doc["type"] = "call_service";
    doc["domain"] = "homeassistant";
    doc["service"] = "toggle";
    JsonObject data = doc["service_data"].to<JsonObject>();
    data["entity_id"] = entity_id;
    String out;
    serializeJson(doc, out);
    g_ws.sendTXT(out);
}
