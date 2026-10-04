"""Tiger Cloud (TimescaleDB) event ledger.

Every recognition from either device is appended to the `detections`
hypertable, which is what makes "value over time", lifetime leaderboards, and
cross-walk analytics fast and durable — the JSON case file only knows about the
case open right now.

Design rules that keep this from ever hurting the walk:

* **Opt-in.** No `TIGER_DB_URL`, no behaviour change: `record_detection` is a
  no-op and `psycopg` is never imported. Tests and offline demos are untouched.
* **Never blocks the scan loop.** `record_detection` only enqueues; a daemon
  worker drains to the cloud over one persistent connection and reconnects on
  failure. A slow RTT stalls the worker, never the camera. A full queue drops
  its oldest row rather than grow without bound (same spirit as the rover's
  bounded offline queue).

Schema lives in `timescale_schema.sql`; bootstrap it once with
`python -m rig.timescale bootstrap` against a writable service.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path

from rig import config

log = logging.getLogger("rig.timescale")

QUEUE_MAX = 1000
SCHEMA_FILE = Path(__file__).resolve().parent / "timescale_schema.sql"

_lock = threading.Lock()
_queue: deque[tuple] = deque(maxlen=QUEUE_MAX)
_wake = threading.Condition()
_worker: threading.Thread | None = None
_dropped = 0
_last_error: str | None = None
_last_write: float | None = None


def dsn() -> str:
    return config.env_str("TIGER_DB_URL")


def enabled() -> bool:
    return bool(dsn())


def _connect():
    """One psycopg connection, autocommit. Lazy import so the package is only
    needed when Tiger is actually configured."""
    import psycopg
    return psycopg.connect(dsn(), autocommit=True, connect_timeout=10)


def record_detection(store, parsed: dict, device: str = "hat", hot: bool = False) -> None:
    """Enqueue one recognition for the Tiger ledger. Returns immediately.

    `store` supplies the case number and mode without the caller threading them
    through. Does nothing (and imports nothing) when Tiger is not configured.
    """
    if not enabled():
        return
    row = (
        int(store.case_no()),
        str(device),
        parsed.get("n"),
        str(parsed.get("item") or "")[:200],
        str(parsed.get("category") or "")[:60],
        _num(parsed.get("value_usd")),
        _bool(parsed.get("estimated", True), default=True),
        str(parsed.get("source") or "unknown")[:24],
        str(parsed.get("price_source") or "unknown")[:24],
        _num(parsed.get("weight_lb"), allow_none=True),
        str(store.mode())[:24],
        bool(hot),
    )
    global _dropped
    with _wake:
        if len(_queue) == _queue.maxlen:
            _dropped += 1
        _queue.append(row)
        _wake.notify()
    _ensure_worker()


def _num(raw, allow_none: bool = False):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None if allow_none else 0.0


def _bool(raw, default: bool = False) -> bool:
    """Coerce a model/JSON-supplied flag; the string "false" must not come out True."""
    if isinstance(raw, str):
        return raw.strip().lower() not in ("", "0", "false", "no")
    return default if raw is None else bool(raw)


_INSERT = (
    "INSERT INTO detections "
    "(case_no, device, n, item, category, value_usd, estimated, source, "
    " price_source, weight_lb, mode, hot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)


def _ensure_worker() -> None:
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_drain, name="tiger-writer", daemon=True)
            _worker.start()


def _drain() -> None:
    """Pull rows off the queue and write them. One connection, reopened on
    error; a dead cloud retries on a backoff without ever touching the walk."""
    global _last_error, _last_write, _dropped
    conn = None
    while True:
        with _wake:
            while not _queue:
                _wake.wait(5)
            row = _queue.popleft()
        try:
            if conn is None:
                conn = _connect()
            conn.execute(_INSERT, row)
            _last_write = time.time()
            _last_error = None
        except Exception as exc:                      # noqa: BLE001 - logged, retried
            # Class name only: a psycopg message can embed the host, and
            # /health serves this field to any LAN client.
            _last_error = type(exc).__name__
            log.warning("tiger write failed; will retry", exc_info=True)
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
            conn = None
            with _wake:
                if len(_queue) < _queue.maxlen:
                    _queue.appendleft(row)            # put it back and back off
                else:
                    _dropped += 1                     # a full queue drops the oldest row
            time.sleep(3)


# ---------- analytics reads (the "fast analytics" the track is about) ----------

def _query(sql: str, params: tuple = (), conn=None) -> list[tuple]:
    """Run one read. `conn` lets a caller bundle several queries on a single
    connection instead of paying a connect/TLS round-trip per query."""
    own = conn is None
    conn = conn or _connect()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall()
    finally:
        if own:
            conn.close()


def top_values(case_no: int, limit: int = 5, conn=None) -> list[dict]:
    """Highest-value recognitions for one case, straight from the hypertable."""
    rows = _query(
        "SELECT item, category, max(value_usd) AS value_usd, bool_and(estimated) "
        "FROM detections WHERE case_no = %s GROUP BY item, category "
        "ORDER BY value_usd DESC LIMIT %s",
        (int(case_no), int(limit)),
        conn,
    )
    return [{"item": r[0], "category": r[1], "value_usd": r[2], "estimated": r[3]} for r in rows]


def take_series(case_no: int, conn=None) -> list[dict]:
    """Take over time for one case, from the continuous aggregate."""
    rows = _query(
        "SELECT bucket, sum(finds) AS finds, sum(take) AS take "
        "FROM detections_5m WHERE case_no = %s GROUP BY bucket ORDER BY bucket",
        (int(case_no),),
        conn,
    )
    return [{"bucket": r[0].isoformat(), "finds": int(r[1] or 0), "take": float(r[2] or 0)} for r in rows]


def lifetime_top(limit: int = 10, conn=None) -> list[dict]:
    """The most valuable things the crew has ever seen, across every walk —
    the query the single JSON ledger simply cannot answer."""
    rows = _query(
        "SELECT item, max(value_usd) AS value_usd, count(*) AS seen, max(ts) AS last_seen "
        "FROM detections GROUP BY item ORDER BY value_usd DESC LIMIT %s",
        (int(limit),),
        conn,
    )
    return [{"item": r[0], "value_usd": r[1], "seen": int(r[2]), "last_seen": r[3].isoformat()} for r in rows]


def case_analytics(case_no: int) -> dict:
    """One bundle of fast hypertable/continuous-aggregate reads for the insights
    endpoint: this case's leaderboard and take-over-time, plus the all-time top.
    All three reads share one connection — one handshake per request, not three."""
    conn = _connect()
    try:
        return {
            "case_no": int(case_no),
            "top_values": top_values(case_no, 5, conn),
            "take_series": take_series(case_no, conn=conn),
            "lifetime_top": lifetime_top(10, conn),
        }
    finally:
        conn.close()


def status() -> dict:
    """For /health: configured, queue depth, last write, last error — no DSN."""
    with _wake:
        depth = len(_queue)
    return {
        "enabled": enabled(),
        "queued": depth,
        "dropped": _dropped,
        "last_write_epoch": _last_write,
        "last_error": _last_error,
    }


# ---------- schema bootstrap ----------

_schema_lock = threading.Lock()
_schema_done = False


def _split_sql(sql: str) -> list[str]:
    """Split a script into statements on top-level semicolons, respecting
    `$$`-dollar-quoted function bodies (so the NOTIFY function isn't cut in
    half) and line comments. TimescaleDB's continuous-aggregate and policy
    statements must each run on their own in autocommit, so we can't hand the
    whole script to one execute()."""
    buf, i, dollar = [], 0, False
    for line in sql.splitlines():
        if line.lstrip().startswith("--"):
            continue
        buf.append(line)
    text = "\n".join(buf)
    out: list[str] = []
    current: list[str] = []
    while i < len(text):
        if text[i:i + 2] == "$$":
            dollar = not dollar
            current.append("$$")
            i += 2
            continue
        ch = text[i]
        if ch == ";" and not dollar:
            stmt = "".join(current).strip()
            if stmt:
                out.append(stmt)
            current = []
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        out.append(tail)
    return out


def bootstrap() -> None:
    """Create the hypertable, continuous aggregate, compression policy, and
    NOTIFY trigger. Idempotent: every statement guards with IF NOT EXISTS, and a
    statement that still errors is logged and skipped so a re-run finishes."""
    conn = _connect()
    try:
        for stmt in _split_sql(SCHEMA_FILE.read_text()):
            try:
                conn.execute(stmt)
            except Exception as exc:                 # noqa: BLE001 - idempotent re-runs log and continue
                log.warning("tiger schema step skipped: %s (%s)", stmt.split("\n", 1)[0][:60], exc)
        log.info("tiger schema bootstrapped")
    finally:
        conn.close()


def ensure_schema_async() -> None:
    """Fire-and-forget bootstrap at startup so a working TIGER_DB_URL is all the
    operator needs — no manual CLI step. Runs once, in the background, and never
    crashes the hub if the database is unreachable or read-only."""
    global _schema_done
    if not enabled():
        return
    with _schema_lock:
        if _schema_done:
            return
        _schema_done = True

    def run():
        delay = 5
        for _ in range(10):
            try:
                bootstrap()
                return
            except Exception:
                log.warning("tiger schema bootstrap failed; retrying in %ss", delay, exc_info=True)
                time.sleep(delay)
                delay = min(delay * 2, 60)
        log.error("tiger schema bootstrap gave up; run `python -m rig.timescale bootstrap` "
                  "once the service is reachable")

    threading.Thread(target=run, name="tiger-bootstrap", daemon=True).start()


# ---------- CLI: bootstrap and check ----------


def check() -> None:
    if not enabled():
        print("TIGER_DB_URL is not set; Tiger ledger disabled.")
        return
    rows = _query("SELECT count(*), coalesce(max(ts)::text, 'never') FROM detections")
    print(f"detections rows: {rows[0][0]}, last: {rows[0][1]}")


def main() -> None:
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
    except ImportError:
        pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if not enabled():
        print("TIGER_DB_URL is not set. Add it to .env to enable the Tiger ledger.")
        return
    if cmd == "bootstrap":
        bootstrap()
        print("Schema bootstrapped.")
    else:
        check()


if __name__ == "__main__":
    main()
