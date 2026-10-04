# Heist Crew Parts List

Shopping + bring list for all three devices, hat hub, wrist unit, rover.
Single-rig details in `BUILD-GUIDE.md` §3.

## Device 2: wrist unit (buy)

| Part | Spec to get | ~Price | Gotcha |
|---|---|---|---|
| ESP32 dev board | ESP32-WROOM-32, USB-C or micro | $8-15 | Needs Wi-Fi; all ESP32s have it |
| SSD1306 OLED | Second unit, same 0.96" I2C 4-pin | $7 | This one lives on the wrist, wired to the ESP32 |
| LiPo or USB power bank | Smallest that fits a wrist strap | $10-20 | ESP32+OLED sips power; a 500mAh cell runs all day |
| Wrist strap / velcro | | $3 | |

## Device 3: rover (buy)

| Part | Spec to get | ~Price | Gotcha |
|---|---|---|---|
| Raspberry Pi 4 | **2GB**: identify runs over the network, RAM is fine | $45-60 | |
| MicroSD | 32GB, Pi OS Lite 64-bit | $8 | |
| Camera | USB webcam or Pi Camera Module | $25 | Pi Cam needs `CAM_BACKEND=v4l2` (default on Linux already) |
| Chassis + 2x TT motors + wheels | Any 2WD robot car kit | $15-25 | Kit bundles chassis/motors/wheels/casters |
| Motor driver | TB6612FNG or L298N breakout | $5-8 | TB6612 is smaller and doesn't eat 1.4V |
| Battery bank | Second bank, 5V/3A | $25-35 | Same brown-out rule as the hub |
| Buck converter | If motors run off the same pack | $5 | Don't feed motors off the Pi's 5V rail |

## Device 1: hat hub additions (buy)

| Part | Spec to get | ~Price | Gotcha |
|---|---|---|---|
| USB mic | Any USB dongle mic, or use the webcam's built-in mic | $10-15 | Pi Camera has NO mic: webcam covers it |
| Second push button | Same momentary tactile as the reveal button | $2-5 | Goes on LISTEN_PIN (GPIO27) |

## Device 1: hat hub core electronics (buy)

| Part | Spec to get | ~Price | Gotcha |
|---|---|---|---|
| Raspberry Pi 4 | **4GB**, the hub: no local inference needed | $55-75 | |
| MicroSD card | 32GB+, flash Pi OS Lite 64-bit before arriving | $8 | Flash + test-boot at home, not at the venue |
| USB webcam | Any UVC cam; Logitech C270 is the safe cheap pick | $25 | 720p is plenty |
| Battery bank | USB-C output, 5V/3A sustained | $25-35 | The #1 hardware failure mode. Cheap banks sag and brown-out the Pi mid-demo. Test under load at home |
| Pi wall brick | Official 5V/3A USB-C | $8 | Bench-only, keeps the battery reserved for demo |
| Push button | Arcade button or any momentary tactile | $2-5 | Two leads, no resistor needed (GPIO pull-up) |
| SSD1306 OLED | 0.96" 128x64, I2C, 4 pins only (VCC/GND/SCL/SDA) | $7 | Do NOT buy the 7-pin SPI version |
| Jumper wires | Dupont female-to-female pack | $3 | 4 needed for the OLED |
| Speaker | Small powered, 3.5mm or USB | $10-15 | USB draws from the Pi's power budget; 3.5mm powered needs its own battery |

Core total: ~$160-190 depending on what you already own.

## Wear/mount (buy or scrounge)

- Stiff structured baseball cap: not floppy; the brim holds the camera ($10-15)
- Pouch or fanny pack for Pi + battery at the waist
- Zip ties, velcro strips, gaffer tape, small hot glue gun

## Bring from home

- Laptop: dev work, flashing the SD card, dashboard display
- Ethernet cable: backup SSH path if venue wifi is hostile
- Phone with hotspot: backup internet for the LLM/SerpAPI calls

## Optional adds (post-MVP, only if a phase finishes early)

| Part | Use | ~Price | Note |
|---|---|---|---|
| USB 58mm POS thermal printer | Prints the LOOT MANIFEST at reveal | ~$35 | Must be `python-escpos` compatible; avoid BLE toy printers (Peripage/Paperang) |
| LDR + laser module | Tripwire to arm scanning (`gpiozero.LightSensor`) | ~$5 | Arming only, never on the required path |
| KY-040 rotary encoder | Rotary "safe dial" reveal trigger | ~$3 | GPIO button stays primary |

## Pre-event check

Bench-test the battery bank tonight: Pi 4 + webcam streaming + an active network call is max load. If it browns out at home, it browns out on stage.
