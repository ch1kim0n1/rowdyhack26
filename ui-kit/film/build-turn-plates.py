"""The turntable plates for the rover, the wrist unit and the hat, cut from the
photographs in film/rover/, film/wrist/ and film/cap/.

The photographs were taken walking round each thing by hand, so it is a different
size and in a different place in every one. Each plate is one square crop of one
photograph, placed so the thing stands the same in all of them. Nothing is drawn,
blended or invented: a plate is a crop and a resize. Run from the repo root:

    python ui-kit/film/build-turn-plates.py
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
MEDIA = HERE.parent / "media"

# ---- the rover: nine photographs. Its box in each: left, top, right, bottom,
# wires to tyres, nose to tail. It stands 60% of the plate's height, its middle 52% down.
ROVER = {
    1: (391, 206, 797, 527),    # right side, from ahead
    2: (348, 224, 758, 557),
    3: (444, 204, 808, 565),
    4: (253, 140, 592, 528),    # head on
    5: (221, 169, 630, 533),
    6: (109, 131, 587, 483),    # left front quarter
    7: (111, 131, 600, 454),
    8: (113, 135, 610, 466),    # left side
    9: (74, 144, 545, 497),     # left rear quarter
}

# ---- the wrist unit: fourteen photographs. Where its middle is, and how long its
# mount is from the forearm end to the hand end, in each. The first photographs were
# taken from further off, so the plates start wider and close in over the first five:
# the unit's length is 56% of the plate at first and 74% from the sixth on.
WRIST = {
    1: (229, 218, 222),         # side on, the hand open
    2: (160, 222, 205),
    3: (190, 232, 216),         # from the forearm
    4: (170, 255, 283),
    5: (210, 325, 361),         # over the forearm
    6: (237, 290, 379),
    7: (288, 298, 399),         # from above
    8: (270, 278, 370),
    9: (277, 322, 332),         # over the hand
    10: (222, 370, 400),        # square on
    11: (262, 378, 392),
    12: (250, 385, 387),        # the right edge coming round
    13: (265, 340, 386),
    14: (270, 345, 415),        # edge on
}
WIDE, CLOSE, BY = 0.56, 0.74, 5
# Which of the fourteen are on the page, in order: every other one, and both ends.
# All fourteen are measured above, so this line is all that needs changing to use more.
WRIST_TURN = (1, 3, 5, 7, 9, 12, 14)

# ---- the hat, by itself on a desk: five photographs, in the order of the turn. It
# nearly fills every photograph, so it nearly fills every plate: its brim is 94% of
# the plate's width (a little more where the photograph is too small to allow that).
CAP = {
    1: (263, 228, 490),         # right side
    2: (303, 274, 564),
    3: (220, 241, 383),         # head on
    4: (258, 224, 425),
    5: (304, 266, 520),         # left side
}


def cut(photo: Image.Image, cx: float, cy: float, side: float, out: Path, px: int) -> str:
    """One square of the photograph, as near to centred on (cx, cy) as its edges allow."""
    side = min(round(side), *photo.size)
    x = min(max(round(cx - side / 2), 0), photo.width - side)
    y = min(max(round(cy - side / 2), 0), photo.height - side)
    photo.crop((x, y, x + side, y + side)).resize((px, px), Image.LANCZOS).save(out, quality=84, method=6)
    return f"{out.name}  crop {side}px at ({x}, {y})"


def source(folder: str, n: int) -> Image.Image:
    return Image.open(next((HERE / folder).glob(f"view-{n:02d}.*"))).convert("RGB")


def main() -> None:
    out = MEDIA / "rover-turn"
    out.mkdir(parents=True, exist_ok=True)
    for n, (left, top, right, bottom) in ROVER.items():
        side = (bottom - top) / 0.60
        print(cut(source("rover", n), (left + right) / 2, (top + bottom) / 2 - side * 0.02, side, out / f"plate-{n - 1}.webp", 800))

    out = MEDIA / "wrist-turn"
    out.mkdir(parents=True, exist_ok=True)
    for plate, n in enumerate(WRIST_TURN):
        cx, cy, length = WRIST[n]
        t = min((n - 1) / BY, 1.0)
        fills = WIDE + (CLOSE - WIDE) * t * t * (3 - 2 * t)
        print(cut(source("wrist", n), cx, cy, length / fills, out / f"plate-{plate}.webp", 720))

    # The print in the crew's file for the wrist: the eighth photograph, close on the unit
    # with the desk and the arm behind it (the print is black and white, and the unit is
    # black), cut to the print's 16:10 window and turned the way its wearer reads the screen.
    photo = source("wrist", 8)
    height = round(photo.width * 10 / 16)
    top = round(WRIST[8][1] - height / 2)
    photo.crop((0, top, photo.width, top + height)).rotate(180).resize((800, 500), Image.LANCZOS).save(
        MEDIA / "file-wrist.webp", quality=86, method=6)
    print(f"file-wrist.webp  crop {photo.width}x{height} at (0, {top}), turned")

    # The hat's middle is 45% of the way down its plate.
    out = MEDIA / "cap-turn"
    out.mkdir(parents=True, exist_ok=True)
    for n, (cx, cy, width) in CAP.items():
        photo = source("cap", n)
        side = min(width / 0.94, *photo.size)
        print(cut(photo, cx, cy + side * 0.05, side, out / f"plate-{n - 1}.webp", 720))


if __name__ == "__main__":
    main()
