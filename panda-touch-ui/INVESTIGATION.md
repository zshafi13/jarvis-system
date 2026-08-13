# Panda Touch — hardware investigation

Notes from repurposing a BIGTREETECH Panda Touch (Bambu printer controller) into the Jarvis
display. None of this is documented publicly, so everything established is recorded here.

## Confirmed

From the [BTT wiki](https://global.bttwiki.com/PandaTouch.html) and product listings:

| | |
|---|---|
| MCU | ESP32-S3R8, dual-core Xtensa LX7 @ 240MHz |
| RAM / Flash | 8MB PSRAM, 16MB flash |
| Display | 5", 800x480, IPS |
| Touch | capacitive, controller **unconfirmed** |
| Audio | microphone only — no speaker/amp/jack in any documentation |
| Other | 2.4GHz WiFi, internal battery (~30 min), USB-C, I2C expansion header |

Independently confirmed by parsing the stock firmware image header
(`panda_touch-v01.00.08.00.bin`, 2.51MB, from BTT's GitHub releases):

```
magic       0xE9          valid ESP32 application image
chip id     9             ESP32-S3
flash       16MB, DIO, 80MHz
entry       0x4037926c    ESP32-S3 IRAM range
segments    5
```

The string `lvgl ui` appears in the binary, so the stock firmware is already LVGL-based.

## What the binary did NOT give up

The RGB pin map is **not** recoverable from the application image by inspection:

- **No driver name strings.** No `gt911`, `st7701`, `esp_lcd`, `rgb_panel` etc. ESP-IDF log tags
  are compiled out. The only strings are Bambu UI text and zlib/WiFi internals.
- **No statically initialised GPIO array.** A scan for 16 contiguous plausible GPIO numbers
  (u32, values 0–48, distinct) returned two candidates, both false positives on inspection:
  - `0x0c8494` — `[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15,0]`, a permutation table
    surrounded by high-entropy data (crypto message schedule).
  - `0x0c8640` — `[0,3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51]`, zlib's inflate length
    base table, immediately preceded by its `0,0,0,0,1,1,1,1,2,2,2,2…` extra-bits table.
- **No timings struct.** `800` appears as a u32 at only 3 offsets and never adjacent to `480`,
  so `esp_lcd_rgb_timing_t` is not in `.rodata`.

This is the expected outcome: ESP-IDF builds `esp_lcd_rgb_panel_config_t` on the stack from
immediate values, so the pin numbers exist only as Xtensa `movi` operands inside compiled code.
Recovering them means disassembling Xtensa LX7 — possible, but a large effort for 20 integers.

## Working hypothesis: it is a Sunton/CYD-class reference design

Rather than disassemble or probe blind, start by assuming the panel follows the common
ESP32-S3 5" 800x480 reference design (Sunton ESP32-8048S050 / "CYD"), which uses an **ST7262**
RGB-565 panel and a **GT911** touch controller at I2C `0x5D`/`0x14`. That pin map is published
and is the starting point in `panda-touch-bringup.yaml`:

```
de 40   hsync 39   vsync 41   pclk 42   backlight 2 (LEDC)
red   [45, 48, 47, 21, 14]
green [5, 6, 7, 15, 16, 4]
blue  [8, 3, 46, 9, 1]
```

Source: [clowrey/esphome-esp32-8048s050-lvgl](https://github.com/clowrey/esphome-esp32-8048s050-lvgl).

**This is a guess, not a finding.** It costs one flash to test and the failure modes are
legible, which is why it beats probing first:

| Symptom | Likely meaning |
|---|---|
| Backlight on, screen black | pclk/de/vsync/hsync wrong, or backlight pin right but panel pins wrong |
| Recognisable image, wrong colours | red/green/blue arrays swapped or misordered |
| Image sheared or offset | timings (porches/pulse width) wrong, pins probably right |
| Tearing / flicker | pclk too high — drop `pclk_frequency` and retry |
| Nothing at all, no backlight | backlight pin wrong; try before assuming the panel is wrong |

## Still unknown

- Whether USB-C enumerates as a serial device for flashing. The ESP32-S3's native USB reaches
  the port (the stock firmware reads firmware from a USB drive, i.e. it acts as USB *host*), so
  the lines are connected; device-mode enumeration is untested.
- Touch controller part number and its I2C/interrupt/reset pins.
- Whether BTT's Recovery Tool can restore stock firmware after an overwrite.
- Microphone interface (I2S vs analog) and pins — not needed for this build, the Pi keeps voice.

## Procedure before the first write

1. Plug into USB-C, check for a serial device, then `esptool chip_id` and `flash_id`.
2. **Back up everything first**: `esptool read_flash 0x0 0x1000000 panda_stock_backup.bin`.
   16MB, a few minutes. Do it even though bricking is acceptable — it is the only route back to
   a printer controller, and the only artifact for any future disassembly.
3. Only then flash `panda-touch-bringup.yaml`.
