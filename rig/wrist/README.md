# Whisplay MQTT wrist display

Tested on Raspberry Pi Zero W with a PiSugar Whisplay HAT.

## Current behavior

- Rover Pi 4 hosts the MQTT broker.
- Hat publishes to rowdy/hat/result.
- Rover publishes to rowdy/rover/result.
- Wrist displays the latest received source, item, and price.
- Automatic startup after reboot has been verified.
- Hub mode (wrist_hub.py, below) polls /wrist.json instead of MQTT; the
  rover broker is not needed in that mode.

The rover must remain powered on for MQTT messaging.

## Dependencies

Install the PiSugar Whisplay driver and example requirements:
https://github.com/PiSugar/Whisplay

Also install:

    sudo apt install mosquitto-clients fonts-dejavu-core

Verify the vendor display test works first.
This setup uses no optional Whisplay daemon.

## Installation

The supplied service assumes username pizerow and the vendor
repository installed at /home/pizerow/Whisplay.

From this project's root on the wrist Pi:

    mkdir -p ~/rowdy
    cp rig/wrist/wrist_mqtt.py ~/Whisplay/example/
    cp rig/wrist/wrist.env.example ~/rowdy/wrist.env
    chmod 600 ~/rowdy/wrist.env
    nano ~/rowdy/wrist.env

Set MQTT_HOST to the rover broker's current IP.
Set MQTT_PASSWORD to the broker password.
The receiver currently uses MQTT username rowdy.

Then install the startup service:

    sudo cp rig/wrist/wrist-display.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now wrist-display.service

Adjust service paths if using a different username or directory.
Do not overwrite an existing wrist.env without preserving its settings.

## Message format

Publish JSON to either supported topic:

    {"item":"Desk lamp","price":24.99,"currency":"USD","price_type":"estimate"}

The source label comes from the topic.
The latest message replaces the previous display.

## Troubleshooting

    systemctl status wrist-display.service --no-pager -l
    journalctl -u wrist-display.service -n 40 --no-pager

If the broker IP changes, edit ~/rowdy/wrist.env and restart:

    sudo systemctl restart wrist-display.service

Stop the service before manually running another display program:

    sudo systemctl stop wrist-display.service

Restart it afterward:

    sudo systemctl start wrist-display.service

## Verified on hardware

- Hat and rover topic messages appeared on the Whisplay.
- Messages published by the hat reached the wrist through the rover broker.
- The receiver started automatically after a wrist reboot.

## Hub display mode

wrist_hub.py reads /wrist.json directly over HTTPS using X-Rig-Token.
It displays the case number, total take, exhibit count, and top five items.
It retries connection errors automatically and redraws only when visible
content changes. This mode does not require the rover MQTT broker.

The MQTT instructions above describe the original fallback mode.

### Install hub mode

After the base Whisplay setup, run from the repository root on the wrist:

    cp rig/wrist/wrist_hub.py ~/Whisplay/example/
    cp rig/wrist/hub.env.example ~/rowdy/hub.env
    chmod 600 ~/rowdy/hub.env
    nano ~/rowdy/hub.env

Fill in the real token locally. Do not commit hub.env.
Preserve an existing configuration instead of overwriting it.

Stop any manually running display program, then:

    sudo systemctl stop wrist-display.service
    sudo mkdir -p /etc/systemd/system/wrist-display.service.d
    sudo cp rig/wrist/hub.conf /etc/systemd/system/wrist-display.service.d/
    sudo systemctl daemon-reload
    sudo systemctl enable wrist-display.service
    sudo systemctl restart wrist-display.service

This override requires the base wrist-display.service to be installed.
Its paths assume username pizerow.

### Restore MQTT mode

    sudo systemctl stop wrist-display.service
    sudo rm /etc/systemd/system/wrist-display.service.d/hub.conf
    sudo systemctl daemon-reload
    sudo systemctl start wrist-display.service

### Handoff status (updated 2026-10-04)

Verified:
- MQTT display of hat and rover messages.
- MQTT receiver automatic startup after reboot.
- Hat camera capture (Pi Zero 2 W + IMX477) via the Picamera2 adapter.
- Rover camera capture (PiCar-X OV5647) via the same adapter.
- Authenticated HTTPS access to the hub.
- Hub case data rendered on the Whisplay (HTTP mode).
- Live recognition and appraisal from the hat feed on the website.

Still to verify or finish:
- Wrist showing the same live results as the dashboard (live parity).
- Hub-mode startup after reboot.
- Reliable automatic time synchronization for HTTPS.
- Rover motor driver compatibility and remote-control networking.
- Full camera-to-wrist workflow end to end.

The wrist clock was manually corrected after a certificate-date error.
Check date and timedatectl status if HTTPS fails.

Camera preparation commands used on the Pis:

    sudo apt install -y python3-picamera2 python3-opencv --no-install-recommends
    rpicam-hello --list-cameras
    mkdir -p ~/rowdy/captures
    rpicam-still --nopreview --timeout 2000 --width 1280 --height 960 --output ~/rowdy/captures/test.jpg

`rig/capture.py` now ships a Picamera2 adapter (`CAM_BACKEND=picamera2`,
selected automatically as a fallback when V4L2 yields no frames) that
supplies frames to OpenCV — verified on both the IMX477 and OV5647.
The requirements-pi.txt NumPy pin needs checking against installed apt packages.
