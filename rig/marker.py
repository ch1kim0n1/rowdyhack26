"""Print the home beacon the rover steers to on return.

    python -m rig.marker           # writes home-marker.png next to the repo
    python -m rig.marker 3         # marker id 3 instead of HOME_MARKER_ID's 0

Tape it where the rover gets dropped. During return_home the rover
dead-reckons the breadcrumb trail; if the beacon enters the frame it stops
reckoning and drives straight at it — the printed square fixes wheel slip.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from rig import config

OUT = Path(__file__).resolve().parent.parent / "home-marker.png"


def marker_id() -> int:
    return config.env_int("HOME_MARKER_ID", 0)


def main() -> None:
    import cv2
    mid = marker_id()
    img = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), mid, 400)
    # Detection needs a quiet zone: ship the PNG with a white border.
    img = cv2.copyMakeBorder(img, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=255)
    cv2.imwrite(str(OUT), img)
    print(f"wrote {OUT} — marker id {mid} (DICT_4X4_50). Print it ~10cm square.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        os.environ["HOME_MARKER_ID"] = sys.argv[1]
    main()
