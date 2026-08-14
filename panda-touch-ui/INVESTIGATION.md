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

## VERIFIED ON HARDWARE

The bring-up config was flashed and the panel came up correctly on the first attempt: four
colour bars in the right order, corner markers, and the full-extent border. Colours, geometry
and bit ordering all confirmed. The pin map above is therefore **verified, not inferred**.

Boot log confirms:

```
ESP-IDF 5.5.4 · chip revision v0.2 · SPI Flash 16MB
I2C bus scan: Found device at address 0x5D      <- GT911, exactly as documented
RPI_DPI_RGB LCD: Height 480, DE GPIO38, Reset GPIO46, 16 data pins bound
PSRAM: Available YES
setup() finished successfully
```

Two things worth knowing:

- **`rpi_dpi_rgb`, not `mipi_rgb`.** `mipi_rgb` looked right because its sync pins are optional,
  but it registers as an SPIDevice and requires `model` + `init_sequence` - it is for panels
  whose controller is configured over SPI. This panel is a raw RGB parallel bus with no SPI
  lines, so `rpi_dpi_rgb` is correct despite needing the sync-pin workaround below.
- **HSYNC/VSYNC are pointed at GPIO42 and GPIO45**, which go nowhere. `rpi_dpi_rgb` requires
  both, the ESP32-S3 LCD peripheral generates them regardless, and they are not routed on this
  board's FPC. Those are the only two usable free GPIOs: everything else is taken by the
  display bus, both I2C buses, UART0, native USB, SPI flash, or the octal PSRAM (GPIO33-37).
  GPIO45 is a strapping pin (VDD_SPI) but is fine as a post-boot output - the board already
  does the same with GPIO46 for LCD reset.

The test pattern visibly repaints once a second. That is `update_interval: 1s` redrawing the
whole frame into a single buffer, not a fault; the LVGL config uses `update_interval: never`.

## Flashing — confirmed working

The chip, read over COM3 on the Windows box:

```
Chip type:  ESP32-S3 (QFN56) revision v0.2
Features:   Wi-Fi, BT 5 (LE), Dual Core + LP Core, 240MHz, Embedded PSRAM 8MB
Crystal:    40MHz            MAC: 80:65:99:a0:c5:4c
Flash:      16MB (GigaDevice c8/4018), quad @3.3V
```

DTR/RTS auto-reset works — no button press needed to enter the bootloader.

**Use 460800 baud or lower.** This CH340K reliably handles 115200 / 230400 / 460800 and fails
every time at 921600. A whole 16MB backup failed 32/32 chunks purely because of this; the
tell was that the failure was total rather than scattered.

Separately, something on that machine opens COM3 periodically — roughly 5 attempts in 20 over
40s fail with "Access is denied" even though the device stays enumerated throughout. Never
identified (an SSH session cannot see the interactive desktop's processes). Retrying is enough
to work around it; a slicer scanning serial ports for printers is the likely culprit.

## Stock firmware backup

`panda_stock_backup.bin`, 16,777,216 bytes, SHA256 `0E82D282770D695EF3C8223785F0CD65C390E93317665B00311F814555E25F63`.
Read in 1MB chunks at 460800 and reassembled. Verified to be genuine rather than an empty read:

```
bootloader @0x0   magic 0xE9, chip_id 9 (ESP32-S3)
partition table   nvs 20KB | otadata 8KB | app0 4608KB @0x010000
                  app1 4608KB @0x490000 | spiffs 7040KB @0x910000 | coredump 64KB
app0              valid 0xE9 image
strings           Panda x30, BIGTREETECH x1, Bambu x8, lvgl x1
60.2% of the first 4MB is non-blank
```

The large spiffs partition is where the per-language `.img` assets live. Restore with:

```
esptool --port COM3 --baud 460800 write-flash 0x0 panda_stock_backup.bin
```

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
