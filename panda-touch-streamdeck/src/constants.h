#pragma once
#ifndef PT_CONSTANTS_H
#define PT_CONSTANTS_H

#include <stdint.h>

#define MAX_BUTTONS 20
#define MAX_HA_TILES 9
#define PANDA_VERSION "1.7.1"

enum ButtonType {
    BTN_TYPE_APP = 0,
    BTN_TYPE_MEDIA,
    BTN_TYPE_BASIC_COMBO,
    BTN_TYPE_ADV_COMBO
};

enum TargetOS {
    OS_WINDOWS = 0,
    OS_MACOS
};

enum KbLang {
    LANG_US = 0,
    LANG_ES
};

// Shared "Jarvis HUD" theme colors - dashboard/orb, and light accents on the
// StreamDeck grid's chrome (control bar/borders), not the user's own button colors.
#define THEME_BG        0x030712
#define THEME_BG_PANEL  0x0A1420
#define THEME_CYAN      0x00E5FF
#define THEME_CYAN_DIM  0x0891B2
#define THEME_AMBER     0xFFB300
#define THEME_GREEN     0x00FF9C
#define THEME_BORDER    0x0E7490
#define THEME_TEXT      0xE0F7FA

#endif
