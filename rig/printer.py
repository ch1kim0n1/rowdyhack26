"""Optional thermal printer: a paper LOOT MANIFEST at reveal.

RIG_PRINTER=1 and a USB 58mm POS printer (python-escpos compatible) turns the
reveal into a physical receipt. Anything missing, env off, library absent,
printer unplugged, logs and moves on; the reveal never depends on paper.

    pip install python-escpos   # rover/hub side, printer attached
"""
from __future__ import annotations

import logging
import threading

from rig import config, journal

log = logging.getLogger("rig.printer")

WIDTH = 32


def enabled() -> bool:
    return config.env_flag("RIG_PRINTER", False)


def receipt(store) -> None:
    """Fire-and-forget print of the case ledger. Never blocks."""
    if not enabled():
        return
    threading.Thread(target=_print, args=(store,), daemon=True, name="printer").start()


def manifest_lines(store) -> list[str]:
    rows = store.manifest_rows()
    lines = [
        "=" * WIDTH,
        "LOOT MANIFEST".center(WIDTH),
        f"CASE NO. {store.case_no()}".center(WIDTH),
        "=" * WIDTH,
    ]
    for row in rows:
        price = f"${row['value_usd']:,.2f}" + ("*" if row.get("estimated") else "")
        name = row["item"][: WIDTH - len(price) - 1]
        lines.append(f"{name:<{WIDTH - len(price) - 1}} {price}")
        if row.get("origin") == "rover":
            lines.append("  (rover scout)")
        if row.get("why"):
            lines.append(f"  *{row['why'][:WIDTH - 4]}")
    lines += [
        "-" * WIDTH,
        f"{'TOTAL TAKE':<{WIDTH - 12}} ${store.take():>10,.2f}",
        "=" * WIDTH,
        "PROPERTY OF THE CREW.".center(WIDTH),
        "",
    ]
    return lines


def printer_ids() -> tuple[int, int]:
    """PRINTER_USB="vid:pid"; default is the common 58mm POS pair."""
    raw = config.env_str("PRINTER_USB", "0x0483:0x5740")
    try:
        vid, pid = raw.split(":")
        return int(vid, 16), int(pid, 16)
    except (ValueError, AttributeError):
        log.warning("bad PRINTER_USB %r; using 0x0483:0x5740", raw)
        return 0x0483, 0x5740


def _print(store) -> None:
    try:
        from escpos.printer import Usb
    except ImportError:
        log.warning("RIG_PRINTER set but python-escpos is not installed; skipping paper manifest")
        journal.event("printer", False, "python-escpos not installed")
        return
    try:
        p = Usb(*printer_ids())  # PRINTER_USB=vid:pid, get ids from `lsusb`
        p.set(align="left", width=1, height=1)
        for line in manifest_lines(store):
            p.text(line + "\n")
        p.cut()
        p.close()
        log.info("loot manifest printed")
        journal.event("printer", True)
    except Exception:
        log.warning("printer failed; dashboard manifest still stands", exc_info=True)
        journal.event("printer", False, "USB print failed")
