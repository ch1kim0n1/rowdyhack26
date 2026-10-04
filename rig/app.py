"""Flask dashboard and the scan thread.

The page is the UI kit. Noir.connect polls /state.json; this process never
draws a box onto the frame.
"""
from __future__ import annotations

import hmac
import io
import json
import logging
import math
import threading
import time
from collections import deque
from datetime import date, datetime
from pathlib import Path
from urllib.request import HTTPRedirectHandler

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
)
from PIL import Image

from rig import (
    button,
    capture,
    config,
    display,
    feed,
    journal,
    listen,
    mastermind,
    narration,
    planner,
    pricing,
    printer,
    radio,
    report,
    script,
    sync,
    timescale,
    tripwire,
    vision,
    voice,
    vultr,
)
from rig.store import Store

log = logging.getLogger("rig")
KIT = Path(__file__).resolve().parent.parent / "ui-kit"
ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env", override=True)


# .env must land before Store() picks up RIG_STATE_FILE; main() is too late.
load_env()

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # biggest legit POST: an exhibit's base64 frame
store = Store()
_blank = None
_STARTED = time.monotonic()

# The change bus: every write path publishes on it, and SSE /events plus the
# wrist long-poll wake off it, so a new find reaches every device at once
# instead of on the next poll. Always on; needs no cloud.
bus = sync.ChangeBus()


def _wrist_payload() -> dict:
    """The whole case in one small object: what the ESP32 wrist renders and what
    the change bus pushes. Short strings only."""
    snap = store.snapshot()
    top = sorted(snap["items"], key=lambda it: it["value_usd"], reverse=True)[:5]
    return {
        "case_no": snap["case_no"],
        "take": snap["take"],
        "count": len(snap["items"]),
        "pending": snap["pending"],
        "revealed": snap["revealed"],
        "camera_ok": snap["camera_ok"],
        "rec_phase_ms": int(time.time() * 1000) % 2000,
        "top": [{"item": it["item"][:28], "value_usd": it["value_usd"]} for it in top],
    }


def _set_pending(flag: bool) -> None:
    """Flip the 'looking' flag; push only on a real change so a quiet walk
    doesn't spam the bus, and a busy one still publishes every transition."""
    if store.snapshot()["pending"] == flag:
        return
    store.set_pending(flag)
    _publish()


def _set_camera(ok: bool) -> None:
    """Same push-on-change rule for the camera flag the wrist renders."""
    if store.camera_ok() == ok:
        return
    store.set_camera(ok)
    _publish()


def _publish() -> None:
    """Announce a case change to every connected device. Cheap and safe to call
    after any store mutation."""
    try:
        bus.publish(_wrist_payload())
    except Exception:
        log.warning("change-bus publish failed", exc_info=True)


def money(value: float) -> str:
    return f"${value:,.2f}"


def blank_jpeg() -> bytes:
    global _blank
    if _blank is None:
        buf = io.BytesIO()
        Image.new("RGB", (16, 12), (15, 14, 12)).save(buf, "JPEG")
        _blank = buf.getvalue()
    return _blank


def manifest_url() -> str:
    return request.host_url + "manifest"


@app.get("/")
@app.get("/reveal")
def dashboard():
    # RIG_TOKEN is NOT rendered into this page: a shared secret that any LAN
    # client can scrape out of the page source protects nothing. The operator
    # enters it once; Noir.drive() keeps it in sessionStorage and sends it as
    # an X-Rig-Token header, so it never hits page source, logs, or history.
    return render_template("dashboard.html", case_no=store.case_no(),
                           case_nonce=_nonce())


@app.get("/desk")
def desk():
    """Dispatch desk: the crew's console. Same token rule as the dashboard:
    the page never carries RIG_TOKEN; a 401 prompts for it once."""
    return render_template("desk.html", case_no=store.case_no(),
                           case_nonce=_nonce())


@app.get("/manifest")
def manifest():
    rows = store.manifest_rows()
    total = round(sum(row["value_usd"] for row in rows), 2)
    plan = mastermind.current(store)
    return render_template(
        "manifest.html",
        case_no=store.case_no(),
        rows=rows,
        total=money(total),
        filed=f"Filed {date.today():%m/%d/%Y}",
        money=money,
        report_id=store.report_id(),
        report_error=store.revealed and not store.report_id() and report.STATUS["last_error"],
        plan=plan,
        bagged=set(plan["selected"]) if plan else set(),
    )


def marker_seconds() -> float | None:
    """How long a new find keeps its box on the live view. MARKER_SECONDS=0
    keeps every box up for the whole case (the old behaviour)."""
    secs = config.env_float("MARKER_SECONDS", 3.0, lo=0.0)
    return secs or None


# Read endpoints: open while the LAN demo has no token, crew-only once
# RIG_TOKEN is set — the feed, the ledger, and the mugshot crops then answer
# 401 until the console supplies the token it was prompted for. Pages stay
# open (browser navigation can't set headers), /manifest stays open (it is
# the QR-shared evidence board, and it carries no keys), /health stays open
# (the kiosk's curl readiness probe can't send headers, and it leaks none).
@app.get("/state.json")
def state():
    if not _authorized():
        abort(401)
    snap = store.snapshot(marker_ttl=marker_seconds())
    # A URL feed has no heartbeat: the rover is "on the line" while frames arrive.
    snap["rover_ok"] = _rover.target() is not None or (
        _feed_url() is not None and store.camera_ok())
    live = _live_id()
    if live and snap["camera_ok"]:
        snap["frame_id"] = live     # the console loads /frame.jpg?live-… once and it plays
    rid = store.report_id()
    # The id only, never the share key: the report itself enforces access.
    snap["report"] = {"id": rid, "url": f"/report/{rid}"} if rid else None
    snap["plan"] = mastermind.current(store, snap)
    resp = jsonify(snap)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/frame.jpg")
def frame():
    if not _authorized():
        abort(401)
    if request.query_string.startswith(b"live"):
        reader = _stream_reader()
        if reader is not None:
            return Response(_relay(reader), mimetype="multipart/x-mixed-replace; boundary=frame",
                            headers={"Cache-Control": "no-store"})
    data = store.frame_jpeg() or blank_jpeg()
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


def _relay(reader: feed.StreamReader):
    """The rover's frames to one console as MJPEG, untouched: no decode, no
    re-encode, newest frame only. A quiet second re-sends the last frame, which
    is also how a closed tab gets noticed and its thread freed."""
    seq = -1
    while True:
        seq, jpeg = reader.wait(seq, 1.0)
        jpeg = jpeg or store.frame_jpeg() or blank_jpeg()
        yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
               + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")


@app.get("/crop/<int:n>.jpg")
def crop(n: int):
    if not _authorized():
        abort(401)
    frame_arr, bbox = store.item_frame(n)
    if frame_arr is None:
        abort(404)
    return Response(capture.crop_jpeg(frame_arr, bbox), mimetype="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.get("/qr.png")
def qr_png():
    import qrcode
    img = qrcode.make(manifest_url())
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


# ---------- Mastermind mode ----------

@app.get("/plan.json")
def plan_json():
    """The job and the live plan: settings, what's in the bag, what stays and why."""
    resp = jsonify({
        "mode": store.mode(),
        "settings": mastermind.settings_for(store),
        "plan": mastermind.current(store),
        "levels": {k: {"label": v["label"], "blurb": v["blurb"]} for k, v in planner.LEVELS.items()},
        "limits": {k: list(v) for k, v in mastermind.LIMITS.items()},
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _mutation_ok() -> bool:
    """The token, or the page's case nonce (an off-site page can't read it)."""
    token = _rig_token()
    has_token = bool(token) and request.headers.get("X-Rig-Token") == token
    return has_token or request.headers.get("X-Case-Nonce") == _nonce()


@app.post("/api/exhibit_status")
def api_exhibit_status():
    """Mark an exhibit {"n": 2, "status": "collected" | "excluded" | "available"}.
    The desk's buttons and the radio both land in mastermind.set_status."""
    if not _rate_ok("plan", 60):
        abort(429)
    if not _mutation_ok():
        abort(401 if _rig_token() else 403)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "send a JSON object"}), 400
    ok, code, message = mastermind.set_status(store, body.get("n"), body.get("status"), body.get("case_no"))
    if ok:
        narration.observe(store)
        _publish()
    return jsonify({"ok": ok, "message": message, "plan": mastermind.current(store)}), code


@app.post("/api/plan")
def api_plan():
    """Pick the job: {"mode": "appraisal"} or {"mode": "mastermind", "bag_lb",
    "time_s", "level"}. Same guard as the Stop button: the token, or the
    dashboard's case nonce (an off-site page can't read it)."""
    if not _rate_ok("plan", 30):
        abort(429)
    token = _rig_token()
    has_token = bool(token) and request.headers.get("X-Rig-Token") == token
    if not (has_token or request.headers.get("X-Case-Nonce") == _nonce()):
        abort(401 if token else 403)
    try:
        mode, settings = mastermind.validate(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not store.set_job(mode, settings):
        return jsonify({"error": "the lineup is up; the next case can change the job"}), 409
    log.info("job: %s %s", mode, settings or "")
    narration.emit("case_started", case_no=store.case_no())
    narration.observe(store)
    _publish()
    return jsonify({"mode": store.mode(), "settings": mastermind.settings_for(store),
                    "plan": mastermind.current(store)})


# ---------- Defender Report ----------
# Access: the operator (RIG_TOKEN header, or anyone in open-LAN mode), or a
# holder of the report's own read-only share key (?k=, carried by its QR).
# RIG_TOKEN itself never goes into a URL or a QR.

def _reports_root() -> Path:
    return report.root_for(store)


def _report_or_404(rid: str) -> dict:
    doc = report.load(_reports_root(), rid)
    if doc is None:
        abort(404)
    return doc


def _report_access(doc: dict) -> bool:
    if _authorized():
        return True
    key, share = request.args.get("k", ""), doc.get("share_key") or ""
    return bool(key and share) and hmac.compare_digest(key, share)


def _when(epoch) -> str:
    return datetime.fromtimestamp(epoch).strftime("%m/%d/%Y %H:%M") if epoch else "unknown"


def _report_page(doc: dict, mode: str, status: int, **extra):
    resp = Response(render_template(
        "report.html", mode=mode, doc=doc, money=money, when=_when,
        source_label=report.source_label, price_label=report.price_label, **extra), status=status)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _whatif(doc: dict) -> tuple[set[int], set[int]]:
    known = {it["n"] for it in doc["items"]}
    try:
        return (report.parse_whatif(request.args.getlist("secure"), known),
                report.parse_whatif(request.args.getlist("move"), known))
    except ValueError as exc:
        abort(400, description=str(exc))


@app.get("/report/<rid>")
def report_page(rid: str):
    if not _rate_ok("report", 240):
        abort(429)
    doc = _report_or_404(rid)
    if not _report_access(doc):
        return _report_page({"report_id": rid}, "locked", 401)
    if doc["state"] != "final":
        return _report_page(doc, "expired", 410)
    secured, moved = _whatif(doc)
    # Carry the share key into links and image URLs only if it is the real one.
    key = request.args.get("k", "")
    key = key if key and hmac.compare_digest(key, doc["share_key"]) else ""
    return _report_page(doc, "final", 200, v=report.view(doc, secured, moved), k=key,
                        q=f"?k={key}" if key else "", by_n={it["n"]: it for it in doc["items"]})


@app.post("/report/<rid>/unlock")
def report_unlock(rid: str):
    """Token mode: the operator types RIG_TOKEN into a form (a POST body, never
    a URL) and lands on the report's share-key link."""
    if not _rate_ok("report-unlock", 10):
        abort(429)
    doc = _report_or_404(rid)
    token = _rig_token()
    given = request.form.get("token", "")
    if not token or not hmac.compare_digest(given, token):
        return _report_page({"report_id": rid}, "locked", 401, wrong=bool(given))
    return redirect(f"/report/{rid}?k={doc['share_key']}", code=303)


@app.get("/report/<rid>.json")
def report_json(rid: str):
    if not _rate_ok("report", 240):
        abort(429)
    doc = _report_or_404(rid)
    if not _report_access(doc):
        abort(401)
    public = {k: v for k, v in doc.items() if k != "share_key"}
    if doc["state"] != "final":
        resp = jsonify(public)
        resp.status_code = 410
    else:
        secured, moved = _whatif(doc)
        resp = jsonify({**public, **report.view(doc, secured, moved)})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/report/<rid>/evidence/<int:n>.jpg")
def report_evidence(rid: str, n: int):
    if not _rate_ok("report", 240):
        abort(429)
    doc = _report_or_404(rid)
    if not _report_access(doc):
        abort(401)
    if doc["state"] != "final":
        abort(410)
    path = report.evidence_path(_reports_root(), rid, n)
    if path is None:
        abort(404)
    resp = send_file(path, mimetype="image/jpeg", max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@app.get("/report/<rid>/qr.png")
def report_qr(rid: str):
    """The report's own QR: its share-key link, for a phone. The manifest QR
    keeps pointing at /manifest."""
    doc = _report_or_404(rid)
    if not _report_access(doc) or doc["state"] != "final":
        abort(401 if doc["state"] == "final" else 410)
    import qrcode
    buf = io.BytesIO()
    qrcode.make(f"{request.host_url}report/{rid}?k={doc['share_key']}").save(buf, "PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/reports")
def api_reports():
    """Operator listing with each report's share link."""
    if not _authorized():
        abort(401)
    rows = []
    for doc in report.listing(_reports_root()):
        row = {k: doc.get(k) for k in ("report_id", "case_no", "state", "finalized_at", "expired_at", "take")}
        if doc.get("state") == "final":
            row["url"] = f"/report/{doc['report_id']}?k={doc['share_key']}"
        rows.append(row)
    resp = jsonify({"reports": rows, "last_error": report.STATUS["last_error"]})
    resp.headers["Cache-Control"] = "no-store"
    return resp


_auto_token: str | None = None


def _rig_token() -> str:
    """RIG_TOKEN=auto mints a per-boot secret — secure-by-default without a
    password file; it's logged once at startup for the crew to type in."""
    global _auto_token
    token = config.env_str("RIG_TOKEN")
    if token.lower() == "auto":
        if _auto_token is None:
            import secrets
            _auto_token = secrets.token_hex(8)
            log.warning("RIG_TOKEN=auto — this boot's token is %s", _auto_token)
        return _auto_token
    return token


def _authorized() -> bool:
    """RIG_TOKEN unset means open LAN demo. Set it when a rover joins the net."""
    token = _rig_token()
    if not token:
        return True
    # Header only: a query-string token lands in access logs and history.
    return request.headers.get("X-Rig-Token") == token


class _RateLimiter:
    """Per-IP sliding-window limiter: open-LAN mode still shouldn't let one
    client flood the ledger or pin the teleop hop. WASD resends ~200/min on a
    held key; exhibit posts arrive at most a few per second during a hot scan."""

    def __init__(self, max_keys: int = 4096):
        self._hits: dict[str, list[float]] = {}
        self._max = max_keys
        self._lock = threading.Lock()

    def ok(self, bucket: str, per_min: int, addr: str | None) -> bool:
        key = f"{bucket}:{addr}"
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > self._max:
                self._hits.clear()   # one row per ip+bucket, but bound the table anyway
            hits = [t for t in self._hits.get(key, []) if now - t < 60]
            if len(hits) >= per_min:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits[-per_min * 2:]
            return True

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


_rate = _RateLimiter()


def _rate_ok(bucket: str, per_min: int) -> bool:
    return _rate.ok(bucket, per_min, request.remote_addr)


# Confirm-page nonce: a cross-origin page can auto-submit the form but can't
# read this value (SOP), so it can't file the case by CSRF.
_CONFIRM_NONCE = None


def _nonce() -> str:
    global _CONFIRM_NONCE
    if _CONFIRM_NONCE is None:
        import secrets
        _CONFIRM_NONCE = secrets.token_hex(8)
    return _CONFIRM_NONCE


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


_wrist_seen = 0.0   # monotonic time of the wrist's last poll, for the dispatch desk


@app.get("/wrist.json")
def wrist():
    """ESP32 wrist unit: the whole case in one small JSON. Short strings only.

    Long-poll: ?since=<v>&wait=<secs> blocks until the case changes past <v>, so
    an update reaches the wrist in tens of milliseconds instead of on its next
    fixed poll. A plain GET (no args) returns at once, so every existing client
    and test is unchanged. The body carries "v": the version to pass back.
    """
    global _wrist_seen
    if not _authorized():
        abort(401)
    if "peek" not in request.args:   # the dispatch desk's preview must not count as the wrist
        _wrist_seen = time.monotonic()
    since = request.args.get("since", type=int)
    wait = request.args.get("wait", type=float)
    if since is not None and wait is not None:
        version, _ = bus.wait(since, min(max(wait, 0.0), 30.0))
    else:
        version = bus.version()
    if "peek" not in request.args:   # refresh liveness when a long block returns
        _wrist_seen = time.monotonic()
    body = _wrist_payload()
    body["v"] = version
    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/events")
def events():
    """Server-Sent Events: the compact case state, pushed the instant it
    changes, for the dashboard and the dispatch desk. Heartbeats keep the
    connection (and any proxy) alive during quiet stretches."""
    if not _authorized():
        abort(401)

    def gen():
        for version, payload in bus.stream(timeout=15.0):
            if payload is None:
                yield ": keep-alive\n\n"
            else:
                yield f"id: {version}\ndata: {json.dumps(payload)}\n\n"

    resp = Response(gen(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Accel-Buffering"] = "no"   # don't let a proxy buffer the stream
    return resp


@app.get("/api/insights")
def api_insights():
    """Instant analytics: TimescaleDB's hypertable does the fast aggregation,
    then Vultr turns the numbers into a one-line read. With Tiger on, the `stats`
    come straight from the hypertable/continuous aggregate; with it off, we fall
    back to the in-memory ledger. `insight` is empty until VULTR_API_KEY is set,
    but the Tiger `stats` are returned either way."""
    if not _authorized():
        abort(401)
    body = {"enabled": vultr.enabled()}
    if timescale.enabled():
        try:
            stats = timescale.case_analytics(store.case_no())
            body["source"] = "tiger"
            body["stats"] = stats
            body["insight"] = vultr.analyze_analytics(stats)
        except Exception:
            log.warning("tiger analytics failed; falling back to the ledger", exc_info=True)
            body["source"] = "ledger"
            body["insight"] = vultr.analyze(store.manifest_rows(), store.take())
    else:
        body["source"] = "ledger"
        body["insight"] = vultr.analyze(store.manifest_rows(), store.take())
    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    return resp


class NoRedirect(HTTPRedirectHandler):
    """Teleop hop must not follow redirects, a 302 would carry headers off."""
    def redirect_request(self, *args, **kwargs):
        return None


class _RoverRegistry:
    """Where teleop forwards. Only /api/rover_ping may write it (an exhibit
    POST can't hijack the wheels), and the entry expires without heartbeats."""

    def __init__(self, ttl: float):
        self.addr: str | None = None
        self.seen = 0.0
        self.ttl = ttl
        self.poll = False   # rover is pull-only (behind NAT): it drains /api/drive/pending
        self._lock = threading.Lock()

    def note(self, addr: str | None, poll: bool = False) -> None:
        if not addr:
            return
        with self._lock:
            self.addr = addr
            self.seen = time.monotonic()
            self.poll = poll

    def touch(self) -> None:
        """A drive-poll heartbeat: keeps the registration warm between pings."""
        with self._lock:
            if self.addr is not None:
                self.seen = time.monotonic()

    def target(self) -> str | None:
        """Live rover address or None, expired registrations don't forward."""
        with self._lock:
            if self.addr is None or time.monotonic() - self.seen > self.ttl:
                return None
            return self.addr

    def wants_poll(self) -> bool:
        """Registered rover asked for pull-mode teleop and hasn't expired."""
        with self._lock:
            fresh = self.addr is not None and time.monotonic() - self.seen <= self.ttl
            return fresh and self.poll

    def seen_ago(self) -> float | None:
        return _seen_ago(self.seen)


ROVER_TTL = 30  # seconds without a heartbeat before teleop forgets it
_rover = _RoverRegistry(ROVER_TTL)

# Pull-mode teleop + rover cam push, for a rover the hub can't reach inbound
# (hosted backend, rover behind venue NAT). /api/drive enqueues, the rover
# long-polls /api/drive/pending; /api/cam/frame accepts pushed JPEGs.
_DRIVE_QUEUE_MAX = 60
_drive_queue: deque[bytes] = deque(maxlen=_DRIVE_QUEUE_MAX)
_drive_cond = threading.Condition()
_pushed_frame: tuple[bytes, float] | None = None


def cam_source() -> str:
    """CAM_SOURCE: empty = the hub's own webcam; "rover" = the registered
    rover's frames; an http(s) URL = a JPEG snapshot URL polled per frame (a
    SunFounder vilib stream is http://<pi>:9000/mjpg.jpg)."""
    return config.env_str("CAM_SOURCE")


def rover_feed() -> bool:
    """True when the hub's picture and its looks come from the rover's camera
    instead of a local webcam. With CAM_SOURCE=rover, run the rover with
    ROVER_VISION=0 so the same find isn't filed from both ends."""
    return _feed_url() is not None or cam_source().lower() == "rover"


def _feed_url() -> str | None:
    source = cam_source()
    return source if source.lower().startswith(("http://", "https://")) else None


class _RoverCamera:
    """The rover's camera in the shape scan_loop expects from cv2.VideoCapture
    (isOpened / read / release), fed by GET <rover>:5001/frame.jpg. "Open"
    means a rover is registered; a missed frame reads as a lost camera, so the
    loop shows CAMERA LOST and retries exactly as it does for a pulled webcam."""

    PORT = 5001                     # the rover's drive_server
    FRAME_TIMEOUT = 2
    FRAME_MAX = 8 * 1024 * 1024

    PUSHED_FRESH_S = 3.0

    def _pushed(self) -> bytes | None:
        """A frame the rover POSTed itself (CAM_PUSH); fresher than a pull."""
        if _pushed_frame is None:
            return None
        data, at = _pushed_frame
        return data if time.monotonic() - at < self.PUSHED_FRESH_S else None

    def _request(self):
        from urllib.request import Request
        addr = _rover.target()
        if addr is None:
            return None
        token = _rig_token()
        host = f"[{addr}]" if ":" in addr else addr
        return Request(f"http://{host}:{self.PORT}/frame.jpg",
                       headers={"X-Rig-Token": token} if token else {})

    def isOpened(self) -> bool:
        return self._pushed() is not None or self._request() is not None

    def read(self):
        from urllib.request import build_opener
        data = self._pushed()
        if data is not None:
            frame = capture.decode_jpeg(data)
            return frame is not None, frame
        req = self._request()
        if req is None:
            return False, None
        try:
            with build_opener(NoRedirect()).open(req, timeout=self.FRAME_TIMEOUT) as resp:
                frame = capture.decode_jpeg(resp.read(self.FRAME_MAX))
        except (OSError, ValueError):
            return False, None
        return frame is not None, frame

    def release(self) -> None:
        pass


class _UrlCamera(_RoverCamera):
    """A camera someone else is already serving: CAM_SOURCE is a URL that
    returns one JPEG per GET. No rover registration and no rig token; the
    token is ours, and this host may not be."""

    def _request(self):
        from urllib.request import Request
        url = _feed_url()
        return Request(url) if url else None

    def read(self):
        reader = _stream_reader()
        if reader is None:
            return super().read()           # a still-image URL: one GET per frame
        _, jpeg = reader.latest()
        frame = capture.decode_jpeg(jpeg) if jpeg else None
        return frame is not None, frame


_BOOT = int(time.time())
_reader: feed.StreamReader | None = None
_reader_lock = threading.Lock()


def _stream_reader() -> feed.StreamReader | None:
    """The reader for a CAM_SOURCE that is an MJPEG stream, started on first
    use. None for a still-image URL, the rover's own frames, or a local webcam."""
    global _reader
    url = _feed_url()
    if not feed.is_stream_url(url):
        return None
    with _reader_lock:
        if _reader is None or _reader.url != url:
            if _reader is not None:
                _reader.stop()
            _reader = feed.StreamReader(url).start()
        return _reader


def _live_id() -> str | None:
    """A frame_id that stays put while the picture is relayed as a stream, so a
    console loads /frame.jpg once and its <img> plays the MJPEG at the camera's
    own frame rate. Not in token mode (an authed console fetches a blob, and a
    stream never finishes) and not while our own rover program has the camera."""
    if _rig_token() or _rover.target() is not None:
        return None
    return f"live-{_BOOT}" if _stream_reader() is not None else None


def _remote_camera():
    """Our own rover program wins while it is pinging; otherwise the URL feed
    (if one is set). So the Pi can run either program without a hub restart."""
    if _rover.target() is not None or not _feed_url():
        return _RoverCamera()
    return _UrlCamera()


@app.post("/api/rover_ping")
def rover_ping():
    """Rover heartbeat: registers the address teleop should forward to.

    {"poll": true} marks the rover pull-only (behind NAT, hosted hub): the
    hub queues /api/drive commands and the rover drains them by long-polling
    /api/drive/pending instead of taking a POST on its :5001."""
    if not _authorized():
        abort(401)
    body = request.get_json(silent=True) or {}
    poll = isinstance(body, dict) and body.get("poll") is True
    _rover.note(request.remote_addr, poll=poll)
    return jsonify({"ok": True})


@app.post("/api/exhibit")
def exhibit():
    """The rover files its finds here. Same dedup ledger as the hat.

    Does NOT register teleop: only /api/rover_ping may claim the wheels, so a
    stray exhibit POST from another LAN device can't redirect /api/drive."""
    if not _rate_ok("exhibit", 120):
        abort(429)
    if not _authorized():
        abort(401)
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        data = {}
    try:
        data["value_usd"] = float(data.get("value_usd") or 0)
    except (TypeError, ValueError):
        data["value_usd"] = 0.0
    if not math.isfinite(data["value_usd"]):
        data["value_usd"] = 0.0   # NaN would poison every JSON response
    if data.get("item") is not None and not isinstance(data["item"], str):
        data["item"] = str(data["item"])
    if data.get("category") is not None and not isinstance(data["category"], str):
        data["category"] = str(data["category"])
    frame = None
    if data.get("frame_b64"):
        try:
            import base64
            frame = base64.b64decode(data.pop("frame_b64"), validate=True)
        except Exception:
            log.warning("exhibit POST had an unreadable frame", exc_info=True)
    added, hot = store.add_item({**data, "origin": "rover"}, frame)
    # Every object the rover sends is logged to the Tiger stream, dedup or not.
    timescale.record_detection(store, data, device="rover", hot=hot)
    if added:
        display.show_take(store.take(), store.count(), store.case_no())
        log.info("rover exhibit %s $%s", data.get("item"), data.get("value_usd"))
        narration.observe(store)    # first find, top five, milestones; exits are never called out
        _publish()                  # push the new find to the wrist and consoles at once
    return jsonify({"added": added, "hot": hot, "take": store.take()}), 201 if added else 200


def _drive_forward(addr: str, body: bytes) -> tuple[int, bytes]:
    """One hop: laptop -> hub -> rover:5001. Five seconds, then give up.

    A rover-side rejection (bad token, bad path) surfaces as its own status,
    not a misleading "unreachable"."""
    from urllib.error import HTTPError
    from urllib.request import Request, build_opener
    token = _rig_token()
    host = f"[{addr}]" if ":" in addr else addr  # IPv6 remote_addr needs brackets
    req = Request(
        f"http://{host}:5001/drive",
        data=body or b"{}",
        headers={"Content-Type": "application/json",
                 **({"X-Rig-Token": token} if token else {})},
        method="POST",
    )
    # No redirects: a 302 from whatever answers on :5001 must not pull our
    # token header toward a host we didn't intend.
    opener = build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=5) as resp:
            return resp.status, resp.read(64 * 1024)
    except HTTPError as exc:
        return exc.code, exc.read(64 * 1024) or b'{"ok":false,"error":"rover rejected"}'


@app.post("/api/drive")
def drive():
    """Laptop teleop. The hub only knows the rover once it has pinged."""
    if not _rate_ok("drive", 600):
        abort(429)
    if not _authorized():
        abort(401)
    if _rover.wants_poll():
        body = request.stream.read(64 * 1024 + 1)
        if len(body) > 64 * 1024:
            return jsonify({"ok": False, "error": "drive body too large"}), 413
        with _drive_cond:
            _drive_queue.append(body)   # full queue drops the oldest move
            _drive_cond.notify()
        return jsonify({"ok": True, "queued": True}), 202
    addr = _rover.target()
    if addr is None:
        return jsonify({"ok": False, "error": "no rover registered"}), 503
    if (request.content_length or 0) > 64 * 1024:
        return jsonify({"ok": False, "error": "drive body too large"}), 413
    try:
        status, body = _drive_forward(addr, request.stream.read(64 * 1024 + 1)[:64 * 1024])
    except OSError:
        return jsonify({"ok": False, "error": "rover unreachable"}), 502
    return Response(body, status=status, mimetype="application/json")


@app.get("/api/drive/pending")
def drive_pending():
    """The rover's pull channel when it's behind NAT (DRIVE_POLL=1 on the
    rover). Long-polls like /wrist.json: ?wait=N holds the request open until
    a queued /api/drive command lands. Every poll also refreshes the rover's
    registration, so teleop survives a missed heartbeat."""
    if not _authorized():
        abort(401)
    _rover.touch()
    try:
        wait = float(request.args.get("wait") or 0)
    except (TypeError, ValueError):
        wait = 0.0
    wait = min(max(wait, 0.0), 15.0)
    deadline = time.monotonic() + wait
    with _drive_cond:
        while not _drive_queue:
            left = deadline - time.monotonic()
            if left <= 0 or not _drive_cond.wait(left):
                return "", 204
        body = _drive_queue.popleft()
    try:
        cmd = json.loads(body or b"{}")
    except ValueError:
        cmd = {}
    if not isinstance(cmd, dict):
        cmd = {}
    return jsonify({"cmd": cmd})


@app.post("/api/cam/frame")
def cam_frame():
    """Rover pushes its latest JPEG here when the hub can't pull it
    (CAM_PUSH=1 on a rover behind NAT). _RoverCamera prefers a fresh pushed
    frame over GETting rover:5001/frame.jpg."""
    global _pushed_frame
    if not _rate_ok("camframe", 600):
        abort(429)
    if not _authorized():
        abort(401)
    body = request.stream.read(8 * 1024 * 1024 + 1)
    if len(body) > 8 * 1024 * 1024:
        return jsonify({"ok": False, "error": "frame too large"}), 413
    if not body:
        return jsonify({"ok": False, "error": "empty frame"}), 400
    _pushed_frame = (body, time.monotonic())
    return jsonify({"ok": True})


def _radio() -> radio.Radio:
    return radio.radio(lambda: store)


def _radio_reply(job: dict, outcome: str):
    if outcome == "invalid":
        return jsonify({"error": job["error"]}), 400
    if outcome == "busy":
        return jsonify(job), 429
    return jsonify({**job, "ok": True, "duplicate": outcome == "duplicate"}), 200 if outcome == "duplicate" else 202


@app.post("/api/radio")
def api_radio():
    """Key the mic: the dashboard's R, the desk's mic button, GPIO27. Starts a
    radio call and returns it at once; poll /api/radio/jobs/<id> to follow it."""
    if not _rate_ok("radio", 30):
        abort(429)
    if not _authorized():
        abort(401)
    body = request.get_json(silent=True) or {}
    return _radio_reply(*_radio().submit("mic", job_id=body.get("job_id") if isinstance(body, dict) else None))


@app.post("/api/radio/text")
def api_radio_text():
    """A typed radio call: {"text": "why leave the lamp", "job_id": optional idempotency key}."""
    if not _rate_ok("radio", 30):
        abort(429)
    if not _mutation_ok():
        abort(401 if _rig_token() else 403)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "send a JSON object with text"}), 400
    return _radio_reply(*_radio().submit("text", body.get("text"), body.get("job_id")))


@app.get("/api/radio/jobs")
def api_radio_jobs():
    if not _authorized():
        abort(401)
    resp = jsonify({"jobs": _radio().recent(), **_radio().status()})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/radio/jobs/<job_id>")
def api_radio_job(job_id: str):
    if not _authorized():
        abort(401)
    job = _radio().get(job_id)
    if job is None:
        abort(404)
    resp = jsonify(job)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/narrator.json")
def narrator_json():
    """What the narrator said, is saying, and dropped: the desk's transcript."""
    if not _authorized():
        abort(401)
    sp = voice.speaker()
    resp = jsonify({"enabled": voice.enabled(), "volume": voice.volume(), "queued": sp.depth(),
                    "lines": list(sp.transcript)[:20]})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/trigger_reveal", methods=["GET", "POST"])
def trigger_reveal():
    if request.method == "GET":
        # Never mutate on GET: an <img> on any page would trip it. Serve a
        # confirm page instead; one tap still works from a phone on the LAN.
        return Response(
            "<!doctype html><meta name=viewport content='width=device-width'>"
            "<body style='background:#111;color:#eee;font-family:monospace;"
            "display:grid;place-items:center;height:100vh;margin:0'>"
            "<form method=post>"
            f"<input type=hidden name=nonce value={_nonce()}>"
            "<button style='font-size:2em;padding:1em 2em;"
            "background:#8b0000;color:#fff;border:0'>FILE THE CASE</button>"
            "</form></body>", mimetype="text/html")
    # CSRF: an off-site page can POST here, but can't learn the nonce (SOP).
    # The nonce OR the token files the case — the phone confirm page posts a
    # form with no way to set a header, so it works in token mode too.
    token = _rig_token()
    has_token = bool(token) and request.headers.get("X-Rig-Token") == token
    has_nonce = (request.form.get("nonce") == _nonce()
                 or request.headers.get("X-Case-Nonce") == _nonce())
    if not (has_nonce or has_token):
        abort(401 if token else 403)
    on_button()
    return jsonify(store.snapshot())


@app.route("/api/serpapi", methods=["GET", "POST"])
@app.route("/toggle_serpapi", methods=["GET", "POST"])
def toggle_serpapi():
    # GET is read-only: status for anyone; mutation needs POST + token.
    if request.method == "POST":
        if not _authorized():
            abort(401)
        data = request.get_json(silent=True) or {}
        if "enabled" in data:
            pricing.set_serpapi_enabled(data["enabled"])
        else:
            pricing.toggle_serpapi()
    provider = pricing.comps_provider()
    has_key = bool(config.env_str("SERPAPI_API_KEY"))
    enabled = pricing.is_serpapi_enabled()
    ready = provider in ("ebay", "ebayapi") or (provider == "serpapi" and has_key)
    return jsonify({
        "enabled": enabled,
        "provider": provider,
        "has_key": has_key,
        "source": provider if enabled and ready else "model_quote",
    })


@app.get("/health")
def health():
    """One glance before the walk: every subsystem, no secrets."""
    snap = store.snapshot()
    if config.env_flag("RIG_OFFLINE", False):
        vision_provider = "offline-catalog"
    elif vultr.enabled() and vultr.vision_first():
        vision_provider = "vultr"
    elif config.env_str("OPENAI_API_KEY"):
        vision_provider = "openai"
    elif config.env_str("ANTHROPIC_API_KEY"):
        vision_provider = "anthropic"
    elif vultr.enabled():
        vision_provider = "vultr"
    else:
        vision_provider = "offline-catalog"
    saved = store.last_saved()
    return jsonify({
        "ok": True,
        "uptime_s": round(time.monotonic() - _STARTED, 1),
        "camera_ok": snap["camera_ok"],
        "pending": snap["pending"],
        "revealed": snap["revealed"],
        "case_no": snap["case_no"],
        "items": len(snap["items"]),
        "take": snap["take"],
        "vision_provider": vision_provider,
        "offline_mode": vision_provider == "offline-catalog",
        "serpapi": {
            "enabled": pricing.is_serpapi_enabled(),
            "provider": pricing.comps_provider(),
            "has_key": bool(config.env_str("SERPAPI_API_KEY")),
        },
        "voice": config.env_flag("RIG_VOICE", True),
        "oled_mode": display._state.get("mode"),
        "persistence": {
            "path": str(store.state_path()),
            "last_saved_epoch": saved,
        },
        "narrator": {
            "enabled": voice.enabled(),
            "volume": voice.volume(),
            "queued": voice.speaker().depth(),
            "last": (list(voice.speaker().transcript)[:1] or [None])[0],
        },
        "radio": _radio().status(),
        "reports": {
            "enabled": report.enabled(),
            "current": store.report_id(),
            "last_error": report.STATUS["last_error"],
            "keep": report.keep_count(),
            "days": report.keep_days(),
        },
        # Last-seen ages only: never the rover's address.
        "rover": {"registered": _rover.target() is not None, "seen_s_ago": _rover.seen_ago()},
        "feed": {"stream": _reader is not None, "fps": _reader.fps() if _reader else None},
        "wrist": {"seen_s_ago": _seen_ago(_wrist_seen)},
        "tiger": timescale.status(),
        "vultr": {"enabled": vultr.enabled(), "vision_first": vultr.vision_first()},
        "sync": {"version": bus.version()},
    })


def _seen_ago(stamp: float) -> float | None:
    return round(time.monotonic() - stamp, 1) if stamp else None


@app.get("/kit")
@app.get("/kit.html")
def kit_page():
    return send_from_directory(KIT, "kit.html")


@app.get("/demo.html")
def demo_page():
    return send_from_directory(KIT, "demo.html")


@app.get("/board.html")
def board_page():
    return send_from_directory(KIT, "board.html")


@app.get("/noir.css")
def noir_css():
    return send_from_directory(KIT, "noir.css")


@app.get("/noir.js")
def noir_js():
    return send_from_directory(KIT, "noir.js")


@app.get("/anime.min.js")
def anime_js():
    return send_from_directory(KIT, "anime.min.js")


@app.get("/fonts/<path:filename>")
def fonts(filename):
    return send_from_directory(KIT / "fonts", filename)


@app.get("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(KIT / "assets", filename)


@app.get("/premiere")
@app.get("/premiere.html")
def premiere_page():
    return send_from_directory(KIT, "premiere.html")


@app.get("/report.css")
@app.get("/premiere.css")
@app.get("/premiere.js")
@app.get("/premiere-scroll.js")
@app.get("/premiere-scroll.css")
@app.get("/premiere-sequence.js")
@app.get("/premiere-portal.css")
@app.get("/premiere-portal.js")
@app.get("/premiere-title-particles.css")
@app.get("/premiere-title-particles.js")
@app.get("/premiere-diamond-type.js")
@app.get("/scroll-cinema.js")
@app.get("/motion-presets.js")
@app.get("/webgl-scenes.js")
@app.get("/premiere-flock.js")
@app.get("/premiere-props.js")
@app.get("/cinematic-motion.css")
@app.get("/intro.js")
@app.get("/desk.css")
@app.get("/desk.js")
@app.get("/wrist-oled.js")
@app.get("/motion.js")
@app.get("/motion.css")
@app.get("/motion.html")
@app.get("/motion-lab.js")
@app.get("/vault.css")
@app.get("/vault.js")
@app.get("/operations.css")
def kit_file():
    return send_from_directory(KIT, request.path.lstrip("/"))


@app.get("/<any(media, shots, brand):folder>/<path:filename>")
def kit_media(folder, filename):
    # send_from_directory refuses paths that climb out of the folder, and
    # answers Range requests, which the premiere's film needs to seek.
    return send_from_directory(KIT / folder, filename)


def _file_report() -> bool:
    """Preserve the revealed case as a Defender Report. False only on a failed
    write; the error shows on /health and the manifest, and the next press retries."""
    try:
        report.finalize(store)
        return True
    except report.ReportError:
        return False


def on_button() -> None:
    if store.mark_revealed():
        display.show_reveal(store.case_no())
        narration.observe(store)        # "Scan complete. Here's the take." or the empty-ledger line
        printer.receipt(store)
        log.info("reveal")
        _file_report()
        _publish()                      # the wrist flips to FLED, the consoles roll the lineup
        return
    if store.revealed and not _file_report():
        # Clearing now would delete the only copy of this case's evidence.
        log.error("case NOT reset: its Defender Report could not be filed (see /health); "
                  "press again to retry, or set RIG_REPORTS=0 to skip reports")
        return
    if store.reset_case():
        capture.reset_gate()
        display.show_take(0, 0, store.case_no())
        narration.observe(store)        # drops the old case's queued lines; "Case closed."
        log.info("case reset")
        _publish()                      # every device resets to the fresh case at once


def _release(cam) -> None:
    if cam is None:
        return
    try:
        cam.release()
    except Exception:
        log.warning("camera release failed", exc_info=True)


# The picture updates like a recording. The model still looks only when the
# scene changed, and at most once every few seconds, so a moving feed does not
# reprice the same object on every frame.
FRAME_EVERY = 1 / 12


def look_every() -> float:
    """Min seconds between model calls. LOOK_EVERY tunes it on site."""
    return config.env_float("LOOK_EVERY", 2.5, lo=0.5)


def scan_loop(opener=None, identify=None, sleep=time.sleep, ticks=None) -> None:
    """Grab, gate, price. ticks stops the loop so a test can run it once."""
    opener = opener or (_remote_camera if rover_feed() else capture.open_camera)
    identify = identify or vision.identify_all
    live = sleep is time.sleep
    frame_every = FRAME_EVERY if live else 0
    look_gap = look_every() if live else 0
    cam = None
    seen = 0
    dirty = False
    last_look = 0.0
    worker = None
    while ticks is None or seen < ticks:
        seen += 1
        if store.revealed:
            sleep(0.2)
            continue
        if cam is None or not cam.isOpened():
            _release(cam)
            cam = opener()
            if cam is None or not cam.isOpened():
                _release(cam)
                cam = None
                _set_camera(False)
                display.show_lost(True)
                narration.observe(store)    # debounced: speaks only once the loss has held
                sleep(2)
                continue
        frame = capture.grab_frame(cam)
        if frame is None:
            _set_camera(False)
            display.show_lost(True)
            narration.observe(store)
            _release(cam)
            cam = None
            sleep(1)
            continue
        was_lost = not store.camera_ok()
        _set_camera(True)
        display.show_lost(False)
        if was_lost:
            narration.observe(store)
        store.set_frame(capture.frame_jpeg(frame))
        if capture.scene_changed(frame):
            dirty = True
        busy = worker is not None and worker.is_alive()
        if dirty and not busy and (time.monotonic() - last_look) >= look_gap:
            dirty = False
            last_look = time.monotonic()
            _set_pending(True)
            shot = frame.copy()

            def run(shot=shot) -> None:
                try:
                    _examine(shot, identify)
                except Exception:
                    log.exception("look failed; the walk continues")
                finally:
                    _set_pending(False)

            if frame_every <= 0:
                run()
            else:
                worker = threading.Thread(target=run, name="rig-look", daemon=True)
                worker.start()
        if frame_every:
            sleep(frame_every)
    if worker is not None:
        worker.join(timeout=30)


def _examine(frame, identify=None) -> None:
    """Look at one frame and file every object in it.

    `identify` may return one object, a list, or None — an injected single-object
    function (the tests, the offline path) is normalized to a list, so the hat
    now files the whole scene, not just the clearest item. EVERY object vision
    returns (it keeps only named, priced ones) is streamed to the Tiger ledger
    (dedup or not — the raw event history wants the repeats); the deduped case
    ledger still drives the live UI.
    """
    identify = identify or vision.identify_all
    result = identify(capture.frame_b64(frame))
    objects = result if isinstance(result, list) else ([] if not result else [result])
    any_added = False
    device = "rover" if rover_feed() else "hat"   # whose camera took the frame
    for parsed in objects:
        pricing.finalize_exhibit(parsed, vision.exits_mode())
        added, hot = store.add_item({**parsed, "origin": device}, frame)
        timescale.record_detection(store, parsed, device=device, hot=hot)
        if added:
            any_added = True
            display.show_take(store.take(), store.count(), store.case_no())
            log.info("exhibit %s $%s%s", parsed["item"], parsed["value_usd"],
                     " est." if parsed["estimated"] else "")
            narration.observe(store)    # first find, top five, milestones, plan revisions
    if any_added:
        _publish()                      # push the new finds to the wrist and consoles at once


def _hw_watch(period: float = 5.0, ticks=None) -> None:
    """Bring-up + heartbeat trail for every wired component. Logs one line per
    state change (first poll counts), so the journal reads as an ordered
    bring-up checklist at boot and a flap detector afterwards."""
    while ticks is None or next(ticks):
        journal.event("camera", store.camera_ok())
        journal.event("rover", _rover.target() is not None,
                      f"seen {_rover.seen_ago():.0f}s ago" if _rover.seen_ago() is not None
                      else "never heard a ping")
        wrist_ago = _seen_ago(_wrist_seen)
        journal.event("wrist", wrist_ago is not None and wrist_ago < 10,
                      f"seen {wrist_ago:.0f}s ago" if wrist_ago is not None else "never polled")
        if timescale.enabled():
            st = timescale.status()
            journal.event("tiger-ledger", st["last_error"] is None,
                          st["last_error"] or f"queued={st['queued']}")
        if vultr.enabled():
            journal.event("vultr-inference", True,
                          "vision-first" if vultr.vision_first() else "backup provider")
        time.sleep(period)


def main() -> None:
    journal.setup()                     # console + rotating file in rig/state/logs/
    load_env()
    timescale.ensure_schema_async()     # a working TIGER_DB_URL is all it takes; no CLI step
    threading.Thread(target=_hw_watch, daemon=True, name="hw-watch").start()
    display.start()
    narration.narrator().prime(store)   # a restart mid-case re-announces nothing
    button.start(on_button, on_mic=lambda: listen.ask_evac(store))
    tripwire.start(on_button)   # LDR beam-break / KY-040 dial, if pinned
    scripted = config.env_flag("RIG_SCRIPT", False)
    if scripted:
        threading.Thread(target=script.run, args=(store,), daemon=True, name="script").start()
        log.info("scripted walk (no camera, no keys)")
    else:
        threading.Thread(target=scan_loop, daemon=True, name="scan").start()
        log.info("live scan")
    host = config.env_str("RIG_BIND") or config.env_str("HOST", "0.0.0.0")
    port = config.env_int("PORT", 5000)
    log.info("dashboard on http://127.0.0.1:%s/ (bound to %s)", port, host)
    serve(host, port)


def serve(host: str, port: int) -> None:
    """Waitress is the runner; Flask's dev server is only the fallback for a
    box that never got the full requirements installed."""
    try:
        from waitress import serve as waitress_serve
    except ImportError:
        log.warning("waitress not installed; falling back to the Flask dev server")
        app.run(host=host, port=port, threaded=True, use_reloader=False)
        return
    waitress_serve(app, host=host, port=port, threads=8)


if __name__ == "__main__":
    main()
