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

## The pin map — solved, from prior art

I concluded above that there was no prior art. **That was wrong.**
[Disttrack/PandaTouch_streamDeck](https://github.com/Disttrack/PandaTouch_streamDeck) is a
working PlatformIO firmware for this exact board, with a documented `docs/PINOUT.md` and
`src/pt/pt_board.h`. Everything below is from there — working code, not inference.

```
PCLK    GPIO5          DE      GPIO38
HSYNC   not routed     VSYNC   not routed        <-- DE-only panel
RESET   GPIO46         BL      GPIO21  (LEDC, 30kHz)

red   (R3..R7) [6, 7, 8, 9, 10]
green (G2..G7) [11, 12, 13, 14, 15, 16]
blue  (B3..B7) [17, 18, 48, 47, 39]

800x480 @ 14.8MHz pclk
hsync: pulse 4, back porch 16, front porch 16
vsync: pulse 4, back porch 32, front porch 32

GT911 touch on I2C0: SDA GPIO2, SCL GPIO1 @100kHz, IRQ GPIO40, RST GPIO41
I2C1 expansion header: SDA GPIO4, SCL GPIO3
```

Two details that would each have cost hours:

- **The panel is DE-only.** HSYNC and VSYNC are not routed on the FPC. ESPHome's
  `rpi_dpi_rgb` platform requires both, so it cannot drive this panel at all. Use `mipi_rgb`,
  where `hsync_pin`/`vsync_pin` are optional.
- **USB-C is not native USB.** It goes through a **CH340K** UART bridge to UART0
  (TX GPIO43 / RX GPIO44), with DTR driving BOOT and RTS driving CHIP_PU. The ESP32-S3's
  native USB OTG is on the **USB-A** port instead (D− GPIO19, D+ GPIO20). So flashing is
  ordinary serial esptool, auto-reset works, and logs come back over the same cable.

For the record, the guess this replaced was the Sunton ESP32-8048S050 reference pinout
(de 40, hsync 39, vsync 41, pclk 42, backlight 2). It is wrong in every single value. Worth
remembering before trusting a "same class of board" assumption again.

## Still unknown

- Whether BTT's Recovery Tool can restore stock firmware after an overwrite.
- Microphone interface (I2S vs analog) and pins — not needed here, the Pi keeps voice.
- Battery charge state reporting, if any is exposed to the MCU.

## Failure-mode reference

Still useful if the panel misbehaves after flashing:

| Symptom | Likely meaning |
|---|---|
| Backlight on, screen black | pclk or DE wrong; check `reset_pin` is being driven |
| Recognisable image, wrong colours | red/green/blue arrays swapped or bit order reversed |
| Image sheared or offset | porches / pulse widths wrong, pins probably right |
| Tearing / flicker | pclk too high — drop below 14.8MHz and retry |
| Nothing at all, no backlight | backlight pin or LEDC frequency wrong — rule this out first |
| I2C scan finds nothing | GT911 held in reset; check RST GPIO41 and IRQ GPIO40 |

## Procedure before the first write

1. Plug into USB-C, check for a serial device, then `esptool chip_id` and `flash_id`.
2. **Back up everything first**: `esptool read_flash 0x0 0x1000000 panda_stock_backup.bin`.
   16MB, a few minutes. Do it even though bricking is acceptable — it is the only route back to
   a printer controller, and the only artifact for any future disassembly.
3. Only then flash `panda-touch-bringup.yaml`.
