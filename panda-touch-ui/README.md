# Panda Touch → Jarvis Visual Interface

Repurposing a BIGTREETECH Panda Touch (5" ESP32-S3 touchscreen, originally a Bambu Lab printer
controller) into the display for the Jarvis voice assistant.

**Status: incomplete.** Everything below the wifi layer works and is verified on hardware. No
configuration with wifi enabled has been confirmed working. See
[INVESTIGATION.md](INVESTIGATION.md) for the full hardware notes.

---

## Objective

Display only — voice input and output stay on the Raspberry Pi satellite. The screen shows an
animated waveform whenever Jarvis is listening, thinking or speaking, and an ambient dashboard
the rest of the time.

The mechanism needs no custom protocol: Home Assistant's `assist_satellite` entity already
exposes exactly four states, so an ESPHome `text_sensor` bound to it drives everything.

```
Pi satellite (unchanged)        Home Assistant                  Panda Touch
────────────────────────        ──────────────────              ──────────────────
wake word, mic, speaker  ────►  assist_satellite.jarvis_pi3_2 ──►  ESPHome + LVGL
                                idle / listening /                 waveform + dashboard
                                processing / responding
```

| State | Screen |
|---|---|
| `idle` | clock, weather, printer status |
| `listening` | waveform, cyan |
| `processing` | waveform, amber |
| `responding` | waveform, green |

---

## What works — verified on hardware

| Item | Evidence |
|---|---|
| Hardware identified | ESP32-S3 rev v0.2, 8MB octal PSRAM, 16MB flash (GigaDevice c8/4018) |
| Stock firmware backup | 16,777,216 bytes, SHA256 `0E82D282…`, verified genuine, restorable |
| Flashing | USB-C → CH340K → UART0, DTR/RTS auto-reset. **Max 460800 baud** |
| Pin map | Verified by driving the panel (see INVESTIGATION.md) |
| Panel | Colour bars, corner markers, border — correct colours and geometry |
| GT911 touch | Responds at `0x5D`, hardware interrupt attaches |
| Full LVGL UI | 2 pages, 9 waveform bars, montserrat fonts — compiles and boots |

Two details that would each cost hours, both from
[Disttrack/PandaTouch_streamDeck](https://github.com/Disttrack/PandaTouch_streamDeck):

- **The panel is DE-only.** HSYNC/VSYNC are not routed on the FPC. ESPHome's `rpi_dpi_rgb`
  requires both, so they are pointed at GPIO42/45 where they drive nothing.
- **USB-C is not native USB.** It is a CH340K UART bridge to UART0. The ESP32-S3's native USB
  OTG is on the USB-A port instead.

---

## What fails

**Anything with wifi enabled.** The bisect:

| Configuration | Result |
|---|---|
| display alone | colour bars on screen |
| + LVGL | boots |
| + GT911 touch | boots, `0x5D`, IRQ attached |
| + full UI | boots |
| + wifi, **without** I2C | reached `wifi: Starting…` — never confirmed joining |
| + wifi, **with** I2C | hangs |

### It is a deadlock, not a crash

The single most useful fact, and it invalidates the obvious theories:

- One boot per capture window, reset reason `POWERON` — not a reboot loop
- No panic, no backtrace, no brownout message — execution simply stops
- Generated `sdkconfig` has `PANIC_PRINT_REBOOT=y` (a crash *would* print) and
  `TASK_WDT_EN=y` + `TASK_WDT_PANIC=y` (a spin *would* trip the watchdog)

Neither fires, so the task is blocked in a call that **yields** — the idle task keeps feeding
the watchdog. Not memory exhaustion, not stack overflow.

---

## Everything tried

| # | Attempt | Rationale | Outcome |
|---|---|---|---|
| 1 | Remove `on_boot: lvgl.page.show` | priority 600 runs before LVGL exists | **Real bug, fixed** — not this one |
| 2 | `buffer_size` 25% → 10% | LVGL buffer starving internal RAM | no change |
| 3 | `SPIRAM_TRY_ALLOCATE_WIFI_LWIP` | move wifi buffers out of internal RAM | one boot further, then same |
| 4 | `scan: false` | 128-address probe blocking | hang **moved later**, not cured |
| 5 | Drop `interrupt_pin` | ISR wedging when wifi disables flash cache | no change |
| 6 | `MAIN_TASK_STACK_SIZE=16384` | streamdeck uses a 16KB loop stack | applied, no change |
| 7 | `FLASHMODE_QIO` | eFuse says quad; was running DIO | applied, no change |
| 8 | `timeout: 10ms` on I2C | bound a stalled transaction | no change |
| 9 | Arduino framework | streamdeck is Arduino + `TAMC_GT911` | **premise wrong** — ESPHome uses `i2c.idf` either way |
| 10 | BTT's official sdkconfig | vendor reference for this board | applied and verified, no change |
| 11 | 120MHz octal PSRAM | BTT's key setting | **blocked**, see below |

### Why 120MHz PSRAM could not be tested

BTT's [PandaTouch_IDF](https://github.com/bigtreetech/PandaTouch_IDF) runs 120MHz octal PSRAM.
ESPHome allows it behind `cpu_frequency: 240MHZ` + `enable_idf_experimental_features: true` —
both set — after which the build fails inside ESP-IDF:

```
static assertion failed: "FLASH and PSRAM Mode configuration are not supported"
mspi_timing_tuning_configs.h:179-181: error
```

It fails against both 120MHz and 80MHz flash. BTT build against **ESP-IDF 5.3.1**; ESPHome
2026.6.5 ships **5.5.4** with stricter timing tables. Not closable from YAML.

This matters because it is the most plausible remaining cause. An 800x480 RGB panel streams its
framebuffer out of PSRAM *continuously*; when wifi contends for the same bus at 80MHz the LCD
DMA can starve, and a starved LCD peripheral stalls. BTT evidently considered 120MHz necessary.
**The hypothesis is untested, not disproven.**

---

## Where to pick this up

1. **ESPHome built on ESP-IDF 5.3.x**, then set 120MHz octal PSRAM as BTT do. Most promising,
   needs no code.
2. **Build on `PandaTouch_IDF` directly** and talk to Home Assistant over its REST or websocket
   API instead of the native API. Starts from a codebase already proven on this exact board.
3. **Custom ESPHome external component** wrapping BTT's display/touch init, bypassing
   `i2c.idf`. Most work, least certain.

---

## Files

| File | Purpose |
|---|---|
| `panda-touch-bringup.yaml` | Test pattern only. Flash first — a wrong pin map is legible on colour bars and baffling on a dashboard. |
| `panda-touch.yaml` | The real interface. Currently display-only; does not boot with wifi. |
| `panda-touch-min.yaml` | Scratch config used for the bisect. Kept as a worked example of isolating a fault. |
| `INVESTIGATION.md` | Full hardware notes: pin map, flashing procedure, backup verification, failure analysis. |

### Restoring the printer controller

```
esptool --port COM3 --baud 460800 write-flash 0x0 panda_stock_backup.bin
```

The device is not damaged at any point in this process — the bootloader stays intact and
esptool connects reliably.
