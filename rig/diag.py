"""Hardware and environment diagnostic tool for the heist loot scanner.

Run on the Pi or your laptop:
    python -m rig.diag
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

from rig import config, journal, pricing

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)


def check_camera() -> bool:
    print("\n--- 1. Camera Diagnostic ---")
    try:
        from rig import capture
        cam = capture.open_camera()
        if cam is None or not cam.isOpened():
            print("[FAIL] Could not open any camera. Check USB connection or CAM_INDEX.")
            return False

        width = cam.get(3)
        height = cam.get(4)
        print(f"[OK] Camera opened successfully. Resolution: {int(width)}x{int(height)}")

        frame = capture.grab_frame(cam)
        cam.release()

        if frame is None:
            print("[FAIL] Camera opened but returned an empty frame.")
            return False

        mean_val = float(frame.mean())
        print(f"[OK] Test frame captured. Mean brightness: {mean_val:.1f} / 255.0")
        if mean_val < 15.0:
            print("[WARN] Frame is nearly black. Ensure the lens cap is off and the room is lit.")
        return True
    except Exception as e:
        print(f"[FAIL] Camera error: {e}")
        return False


def check_i2c_oled() -> bool:
    print("\n--- 2. I2C SSD1306 OLED Diagnostic ---")
    if sys.platform != "linux":
        print("[INFO] Not running on Linux. Hardware I2C is simulated on this platform.")
        return True

    try:
        from luma.core.interface.serial import i2c
        from luma.oled.device import ssd1306
        ssd1306(i2c(port=1, address=0x3C))
        print("[OK] SSD1306 OLED detected on I2C bus 1 at address 0x3C.")
        return True
    except Exception as e:
        print(f"[WARN] SSD1306 OLED not found at 0x3C ({e}).")
        print("       Check wiring: VCC to 3.3V, GND to GND, SDA to GPIO2, SCL to GPIO3.")
        return False


def check_gpio_button() -> bool:
    print("\n--- 3. GPIO 17 Button Diagnostic ---")
    if sys.platform != "linux":
        print("[INFO] Not running on Linux. Physical GPIO is simulated on this platform.")
        return True

    try:
        from gpiozero import Button
        btn = Button(17, bounce_time=0.15)
        state = "PRESSED" if btn.is_pressed else "RELEASED"
        print(f"[OK] GPIO 17 initialized successfully. Current state: {state}")
        return True
    except Exception as e:
        print(f"[WARN] GPIO 17 could not be read ({e}).")
        print("       Check wiring: one lead to GPIO 17, other lead to GND.")
        return False


def check_vision_api() -> bool:
    print("\n--- 4. Vision & Pricing API Diagnostic ---")
    openai_key = config.env_str("OPENAI_API_KEY")
    anthropic_key = config.env_str("ANTHROPIC_API_KEY")
    serpapi_key = config.env_str("SERPAPI_API_KEY")

    if openai_key:
        masked = openai_key[:7] + "..." + openai_key[-4:]
        print(f"[OK] OPENAI_API_KEY present ({masked}).")
        vision_model = config.env_str("OPENAI_VISION_MODEL", "gpt-4.1")
        price_model = config.env_str("OPENAI_PRICE_MODEL", "gpt-4.1-mini")
        print(f"     Vision model: {vision_model}")
        print(f"     Pricing model: {price_model}")
    else:
        print("[WARN] OPENAI_API_KEY is not set.")

    if anthropic_key:
        masked = anthropic_key[:7] + "..." + anthropic_key[-4:]
        print(f"[OK] ANTHROPIC_API_KEY present ({masked}).")
    else:
        print("[INFO] ANTHROPIC_API_KEY not set.")

    provider = pricing.comps_provider()
    if serpapi_key:
        masked = serpapi_key[:7] + "..." + serpapi_key[-4:]
        print(f"[OK] SERPAPI_API_KEY present ({masked}); comps provider: {provider}.")
    elif provider == "ebay":
        print("[OK] Comps provider: ebay (scrapes sold listings; no key).")
    else:
        print(f"[INFO] Comps provider: {provider}; model pricing quotes in use.")

    if not openai_key and not anthropic_key:
        print("[FAIL] No LLM keys configured. Offline fallback will be active.")
        return False
    return True


def check_voice() -> bool:
    print("\n--- 5. Audio / Voice Diagnostic ---")
    voice_enabled = config.env_flag("RIG_VOICE", True)
    if not voice_enabled:
        print("[INFO] RIG_VOICE is disabled (RIG_VOICE=0).")
        return True

    print("[INFO] RIG_VOICE is enabled.")
    if sys.platform == "win32":
        print("[OK] Windows sound subsystem available.")
    else:
        import subprocess
        res = subprocess.run(["which", "aplay"], capture_output=True, text=True)
        if res.returncode == 0:
            print("[OK] aplay found for hardware audio playback.")
        else:
            print("[WARN] aplay not found. Install alsa-utils.")
    return True


def check_thermals() -> bool:
    """Pi-only: read vcgencmd throttling bits before a demo — a brownout-prone
    bank shows up here long before it kills the walk."""
    print("\n--- 7. Power / Thermal Diagnostic ---")
    try:
        import subprocess
        res = subprocess.run(["vcgencmd", "get_throttled"],
                             capture_output=True, text=True, timeout=5)
        flags = int(res.stdout.strip().split("=")[-1], 16)
    except Exception:
        print("[INFO] vcgencmd unavailable (not a Pi); skipping power probe.")
        return True
    if flags & 0xF:
        print(f"[WARN] active throttle/undervoltage: 0x{flags:x} — check the bank (5V/3A).")
        return False
    if flags & 0xF0000:
        print(f"[WARN] throttling recorded earlier this boot: 0x{flags:x}")
        return True
    print("[OK] clean power, no throttle flags.")
    return True


def check_motors() -> bool:
    """Rover only: probe the wheel driver. Reports console fallback off-Pi."""
    print("\n--- 6. Drive Motors Diagnostic ---")
    if "rover" not in config.env_str("RIG_ROLE").lower() and not config.env_str("DRIVE_PINS"):
        print("[INFO] not a rover run (no RIG_ROLE=rover / DRIVE_PINS); skipping motor probe.")
        return True
    try:
        from rig import drive
        drv = drive.get_driver()
    except Exception:
        print("[WARN] motor probe raised; check gpiozero + TB6612 wiring.")
        return False
    if isinstance(drv, drive.ConsoleDriver):
        print("[WARN] console driver, no motor GPIO claimed. Wheels will log, not roll.")
        return False
    print(f"[OK] motor driver live on DRIVE_PINS={','.join(map(str, drive.drive_pins()))}")
    return True


def run_all() -> None:
    journal.setup()                     # results land in the bring-up log too
    print("========================================")
    print("  Heist Loot Scanner Hardware Diag")
    print("========================================")
    cam_ok = check_camera()
    oled_ok = check_i2c_oled()
    gpio_ok = check_gpio_button()
    api_ok = check_vision_api()
    voice_ok = check_voice()
    motor_ok = check_motors()
    power_ok = check_thermals()

    for name, ok in (("camera", cam_ok), ("oled", oled_ok), ("gpio-button", gpio_ok),
                     ("vision-api", api_ok), ("voice", voice_ok),
                     ("motors", motor_ok), ("power-thermals", power_ok)):
        journal.note(f"diag.{name}", "OK" if ok else "FAIL/WARN")

    print("\n----------------------------------------")
    print(f"Summary: Cam={'OK' if cam_ok else 'FAIL'}, "
          f"OLED={'OK' if oled_ok else 'WARN'}, "
          f"GPIO={'OK' if gpio_ok else 'WARN'}, "
          f"API={'OK' if api_ok else 'WARN'}, "
          f"Voice={'OK' if voice_ok else 'WARN'}, "
          f"Motors={'OK' if motor_ok else 'WARN'}, "
          f"Power={'OK' if power_ok else 'WARN'}")
    print("----------------------------------------")


if __name__ == "__main__":
    run_all()
