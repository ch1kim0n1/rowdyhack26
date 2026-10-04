"""Grounded radio: the crew asks dispatch about the job, dispatch answers from the ledger.

A radio call is a job: typed on the desk, or keyed on the mic (GPIO27, the
dashboard's R, POST /api/radio) and transcribed. The job runs through one
bounded queue: listening -> transcribing -> thinking -> applying ->
speaking -> done, or clarify / failed / cancelled / expired, and every state
is visible on the desk, so a muted room still works.

Nothing here asks a model what to say. A small vocabulary is parsed
deterministically, and every answer is assembled from the live plan
(rig/mastermind.py) and the ledger: exhibit names, values, weights, the
plan revision, and the planner's own reason sentences. It cannot invent an
item, a price, a countdown, or a security prediction. Exhibit names are
data: they are matched against and quoted, never followed.

Reads:   what's next / why leave the lamp / how much fits / how much time
         is left / what changed / how many badges
Changes: switch to small job | big score | appraisal | mastermind,
         set the clock to 20 seconds, set the bag to 10 pounds,
         mark exhibit 2 collected, exclude the lamp, put back exhibit 4
Changes go through the same validated calls as the dashboard and the desk
(mastermind.validate + store.set_job, mastermind.set_status). An unclear
command asks for the missing piece instead of guessing, and a command that
was heard for a case that has since closed, or against a plan that changed
while it was being parsed, is cancelled visibly rather than applied late.
"""
from __future__ import annotations

import itertools
import logging
import re
import threading
import time
import uuid
from collections import deque

from rapidfuzz import fuzz

from rig import config, mastermind, narration, planner

log = logging.getLogger("rig.radio")

MAX_TEXT = 200
QUEUE_MAX = 3            # calls waiting behind the one in flight
QUEUED_TTL = 30.0        # seconds a call may wait before it is stale
KEEP_JOBS = 50
KEEP_SECONDS = 15 * 60
_JOB_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")

HELP = ("I answer: what's next, why leave an exhibit, how much fits, how much time is left, "
        "what changed, how many badges. I can set: small job or big score, appraisal or "
        "mastermind, the clock in seconds or minutes, the bag in pounds, and mark an exhibit "
        "collected, excluded, or back in play.")


def money(v: float) -> str:
    return f"${v:,.0f}"


def lb(v: float) -> str:
    return f"{float(v):g}"


# ---------- parsing ----------

_UNITS = {"zero": 0, "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}


def normalize(text: str) -> str:
    """Lowercase, plain apostrophes, spoken numbers to digits, punctuation out."""
    t = text.lower().replace("’", "'").replace("#", " number ")
    t = re.sub(r"[^a-z0-9.'\s-]", " ", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)
    words, out = t.replace("-", " ").split(), []
    i = 0
    while i < len(words):
        w = words[i]
        if w in _TENS:
            n = _TENS[w]
            if i + 1 < len(words) and words[i + 1] in _UNITS and _UNITS[words[i + 1]] < 10:
                n += _UNITS[words[i + 1]]
                i += 1
            out.append(str(n))
        elif w in _UNITS and w not in {"a", "an"}:
            out.append(str(_UNITS[w]))
        elif w in {"a", "an"} and i + 1 < len(words) and words[i + 1] in {"minute", "pound"}:
            out.append("1")
        elif w == "half" and i + 2 < len(words) and words[i + 1] == "a" and words[i + 2] == "minute":
            out.extend(["30", "seconds"])
            i += 2
        else:
            out.append(w)
        i += 1
    return " ".join(out)


class Intent:
    def __init__(self, name: str, **args):
        self.name, self.args = name, args

    def as_dict(self) -> dict:
        return {"name": self.name, "args": self.args}

    @property
    def mutates(self) -> bool:
        return self.name in {"set_level", "set_mode", "set_time", "set_bag", "set_status"}


_STATUS_WORDS = {"collected": "collected", "taken": "collected", "bagged": "collected", "grabbed": "collected",
                 "in the bag": "collected", "excluded": "excluded", "out": "excluded", "skipped": "excluded",
                 "available": "available", "back": "available", "back in play": "available"}
_LEVELS = {"ghost": "small", "quiet": "small", "small": "small", "stealth": "small", "small job": "small",
           "big": "big", "loud": "big", "greedy": "big", "large": "big", "big score": "big"}


def parse(text: str) -> Intent:
    """One utterance to one intent. Order matters: questions before commands,
    so 'why leave the lamp' is never read as 'leave the lamp'."""
    t = normalize(text)
    if not t:
        return Intent("unsupported")
    if re.fullmatch(r"(help|commands?|options|what can (you|i) (do|say|ask)( you)?)", t):
        return Intent("help")

    m = re.search(r"\bwhy\b.*?\b(?:leave|leaving|left|skip|skipping|not take|not taking|not bag|not bagging|"
                  r"drop|dropping|dropped|exclude|excluding|pass on)\b\s+(?:the\s+)?(?P<ref>.+)$", t)
    if m:
        return Intent("why", ref=m.group("ref"))
    m = re.search(r"\bwhy\b\s+(?:is|isn't|is not|are|aren't)\s+(?:the\s+)?(?P<ref>.+?)\s+"
                  r"(?:left|left behind|not in the bag|out|excluded|being left|in the bag|bagged)\b", t)
    if m:
        return Intent("why", ref=m.group("ref"))
    m = re.search(r"\bwhy\b.*?\b(?:take|taking|bag|bagging|grab|grabbing)\b\s+(?:the\s+)?(?P<ref>.+)$", t)
    if m:
        return Intent("why", ref=m.group("ref"))

    m = re.search(r"\b(?:mark|set|flag)\s+(?P<ref>.+?)\s+(?:as\s+)?(?P<st>collected|taken|bagged|grabbed|"
                  r"in the bag|excluded|out|skipped|available|back in play|back)$", t)
    if m and not re.search(r"\b(clock|time|timer|bag to|bag at|budget)\b", m.group("ref")):
        return Intent("set_status", ref=m.group("ref"), status=_STATUS_WORDS[m.group("st")])
    m = re.match(r"(?:exclude|skip|forget|leave)\s+(?:the\s+)?(?P<ref>.+)$", t)
    if m:
        return Intent("set_status", ref=m.group("ref"), status="excluded")
    m = re.match(r"(?:unmark|restore|put back|reset)\s+(?:the\s+)?(?P<ref>.+?)(?:\s+in play)?$", t)
    if m:
        return Intent("set_status", ref=m.group("ref"), status="available")

    m = re.search(r"\b(?P<mode>appraisal|mastermind)\b", t)
    if m and re.search(r"\b(switch|go|change|set|use|start|back to)\b|mode$|^(appraisal|mastermind)$", t):
        return Intent("set_mode", mode=m.group("mode"))
    m = re.search(r"\b(?P<lvl>small job|big score|ghost|quiet|stealth|small|big|loud|greedy|large)\b", t)
    if m and re.search(r"\b(switch|go|change|set|make it|make this|run|plan)\b|^(ghost|quiet|small job|big score)$", t):
        return Intent("set_level", level=_LEVELS[m.group("lvl")])

    if re.search(r"\b(carry units?|units?)\b.*\bleft\b|\bleft\b.*\bunits?\b", t):
        return Intent("clarify", message="The bag is set in pounds, as a total. "
                                         "Say 'set the bag to 10 pounds'.")
    m = re.search(r"\b(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>pounds?|lbs?|lb)\b", t)
    if m and re.search(r"\bbag\b|\bcarry\b|\bhold", t):
        if re.search(r"\bleft\b|\bremaining\b|\bmore\b", t):
            return Intent("clarify", message="Is that the whole bag, or what's left after what's collected? "
                                             "Say 'set the bag to N pounds' for the whole bag.")
        return Intent("set_bag", bag_lb=float(m.group("num")))
    if re.search(r"\bbag\b", t) and re.search(r"\b(set|make|change)\b", t):
        return Intent("clarify", message="How heavy? Say 'set the bag to 10 pounds'.")

    if re.search(r"\b(clock|time|timer|budget|seconds?|minutes?)\b", t) and re.search(
            r"\b(set|make|change|give|we have|we've got|got)\b|\bleft$", t):
        m = re.search(r"\b(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>seconds?|secs?|s|minutes?|mins?|m)\b", t)
        if m and not re.search(r"\b(left|remaining)\b", t) and not re.search(r"\bwe (have|ve got)\b", t):
            secs = float(m.group("num")) * (60 if m.group("unit").startswith("m") else 1)
            return Intent("set_time", time_s=secs)
        if m:
            return Intent("clarify", message="Is that the whole job's clock, or what's left of it? "
                                             "Say 'set the clock to N seconds' for the whole job.")
        if re.search(r"\b\d+(?:\.\d+)?\b", t):
            return Intent("clarify", message="Seconds or minutes? Say 'set the clock to 20 seconds'.")

    if re.search(r"\bnext\b|what (?:should|do|can) (?:i|we) (?:take|grab|get)", t):
        return Intent("next")
    if re.search(r"\b(badges?|keycards?|key cards?|credentials?|ids?)\b", t) and re.search(r"how many|count|any", t):
        return Intent("badges")
    if re.search(r"how much (?:value |money )?(?:fits|is in the bag|in the bag|are we carrying|is it worth)|"
                 r"what'?s in the bag|\bhaul\b|how much (?:is|are) (?:we|it) worth|what fits", t):
        return Intent("value")
    if re.search(r"how much time|time (?:is )?left|how long|time remaining|\bclock\b", t):
        return Intent("time")
    if re.search(r"what(?:'s| has| is)? changed|last (?:plan|change|revision)|what'?s different|what's new", t):
        return Intent("changes")
    return Intent("unsupported")


def resolve(ref: str, items: list[dict]) -> tuple[dict | None, str | None]:
    """An exhibit for a spoken reference: a number, or one clear name match.
    (item, None) or (None, the question to ask back)."""
    ref = re.sub(r"^(?:the|a|an)\s+", "", ref.strip())
    m = re.fullmatch(r"(?:exhibit|number|item|no|num)?\s*(\d{1,3})", ref)
    if m:
        n = int(m.group(1))
        hit = next((it for it in items if it["n"] == n), None)
        return (hit, None) if hit else (None, f"There's no exhibit {n:02d} in this case.")
    if not ref:
        return None, "Which exhibit? Say its number."
    scored = sorted(((max(fuzz.partial_ratio(ref, it["item"].lower()),
                          fuzz.token_set_ratio(ref, it["item"].lower())), it) for it in items),
                    key=lambda s: (-s[0], s[1]["n"]))
    good = [s for s in scored if s[0] >= 75]
    if not good:
        return None, f"No exhibit sounds like '{ref}'. Say its number."
    if len(good) > 1 and good[1][0] >= good[0][0] - 10:
        names = " or ".join(f"{it['n']:02d} {it['item']}" for _, it in good[:4])
        return None, f"Which one: {names}? Say the exhibit number."
    return good[0][1], None


# ---------- answering ----------

def _view(store) -> tuple[dict, dict | None]:
    snap = store.snapshot()
    return snap, mastermind.current(store, snap)


def answer(intent: Intent, snap: dict, plan: dict | None) -> str:
    """A read, from one labeled snapshot. Never mutates anything."""
    items = snap["items"]
    loot = [it for it in items if (it.get("category") or "").lower() != "exit"]
    by_n = {it["n"]: it for it in items}
    name = intent.name
    if name == "help":
        return HELP
    if name == "badges":
        badges = [it for it in items if it.get("category") == "badge"]
        if not badges:
            return "No badges or IDs cloned this case."
        return (f"{len(badges)} credential{'s' if len(badges) != 1 else ''} cloned: "
                + ", ".join(it["item"] for it in badges) + ".")
    if plan is None:
        top = max(loot, key=lambda it: (it["value_usd"], -it["n"]), default=None)
        return {
            "next": (f"Appraisal job: no plan, so no next. Best find so far: {top['item']}, {money(top['value_usd'])}."
                     if top else "Appraisal job, and nothing filed yet."),
            "why": "Appraisal job: nothing gets left behind. Switch to Mastermind for a plan.",
            "value": f"Appraisal job: {money(snap['take'])} across {len(loot)} exhibit{'s' if len(loot) != 1 else ''}. No bag, no limit.",
            "time": "Appraisal job: there's no clock. Switch to Mastermind to set one.",
            "changes": "Appraisal job: there's no plan to change.",
        }.get(name, HELP)
    rev, totals, c = plan["revision"], plan["totals"], plan["constraints"]
    if name == "next":
        if plan["next"]:
            nxt = plan["next"]
            return (f"Next: {nxt['item']}, {money(nxt['value_usd'])}. The plan has {len(plan['selected'])} "
                    f"in the bag for {money(totals['value_usd'])}, revision {rev}.")
        if plan["selected"]:
            return f"Everything in the plan is collected. {money(totals['value_usd'])} in the bag."
        return ("Nothing fits this job. Give it more time or a bigger bag." if loot
                else "Nothing filed yet. Walk the room.")
    if name == "value":
        return (f"In the bag: {money(totals['value_usd'])} of {money(snap['take'])} seen. "
                f"{lb(totals['weight_lb'])} of {lb(c['bag_lb'])} pounds, {totals['grab_seconds']} of "
                f"{c['time_s']} seconds. Revision {rev}.")
    if name == "time":
        spare = c["time_s"] - totals["grab_seconds"]
        return (f"The clock is {c['time_s']} seconds. The plan needs {totals['grab_seconds']} of it, "
                f"{max(spare, 0)} to spare. That's planned grab time, not a countdown.")
    if name == "changes":
        ch = plan.get("change")
        if not ch:
            return f"Revision {rev}. Nothing has moved since the last plan."
        if ch["settings_changed"]:
            s = plan["settings"]
            return (f"Revision {rev}: new settings, {lb(s['bag_lb'])} pounds, {s['time_s']} seconds, "
                    f"{plan['level']['label'].lower()}. {money(totals['value_usd'])} in the bag.")
        bits = []
        if ch["added"]:
            bits.append("in: " + ", ".join(a["item"] for a in ch["added"]))
        if ch["dropped"]:
            bits.append("out: " + ", ".join(d["item"] for d in ch["dropped"]))
        delta = ch["delta_usd"]
        sign = "up" if delta >= 0 else "down"
        return f"Revision {rev}: {'; '.join(bits) or 'same exhibits'}. Value {sign} {money(abs(delta))}."
    if name == "why":
        item, question = resolve(intent.args["ref"], items)
        if question:
            return question
        n = item["n"]
        if (item.get("category") or "").lower() == "exit":
            return f"{item['item']} is an exit. Information, not loot."
        if n in plan.get("collected", []):
            return f"{item['item']} is already collected."
        if n in plan["selected"]:
            row = mastermind.exhibits_from([by_n[n]])[0]
            return (f"{item['item']} is in the bag: {lb(row['weight_lb'])} pounds, "
                    f"{row['grab_seconds']} seconds, {money(item['value_usd'])}.")
        left = next((x for x in plan["left"] if x["n"] == n), None)
        if left:
            return f"Leaving {item['item']}: {left['text']}."
        return f"{item['item']} isn't in the plan."
    return HELP


def _summary(store) -> str:
    snap, plan = _view(store)
    if plan is None:
        return "Appraisal job: no limits, every find counts."
    return (f"Revision {plan['revision']}: {money(plan['totals']['value_usd'])} in the bag, "
            f"{lb(plan['totals']['weight_lb'])} of {lb(plan['constraints']['bag_lb'])} pounds, "
            f"{plan['totals']['grab_seconds']} of {plan['constraints']['time_s']} seconds.")


def _sentence(text: str) -> str:
    return text[0].upper() + text[1:] + ("" if text.endswith((".", "?", "!")) else ".")


def apply(intent: Intent, store) -> tuple[str, str]:
    """A change, through the same validated calls the dashboard and desk use.
    Returns (outcome, reply): done, clarify (asked for what's missing), or
    failed (refused by validation; nothing changed)."""
    snap = store.snapshot()
    if snap["revealed"]:
        return "failed", "The lineup is up. That waits for the next case."
    if intent.name == "set_status":
        item, question = resolve(intent.args["ref"], snap["items"])
        if question:
            return "clarify", question
        ok, _code, message = mastermind.set_status(store, item["n"], intent.args["status"], snap["case_no"])
        return ("done", f"Done. {_sentence(message)} " + _summary(store)) if ok else ("failed", _sentence(message))
    if intent.name == "set_mode":
        body = {"mode": intent.args["mode"], **mastermind.settings_for(store)}
    else:
        if snap["mode"] != "mastermind":
            return "clarify", "That's a Mastermind setting. Say 'switch to Mastermind' first."
        body = {"mode": "mastermind", **mastermind.settings_for(store)}
        if intent.name == "set_level":
            body["level"] = intent.args["level"]
        elif intent.name == "set_time":
            body["time_s"] = intent.args["time_s"]
        elif intent.name == "set_bag":
            body["bag_lb"] = intent.args["bag_lb"]
    try:
        mode, settings = mastermind.validate(body)
    except ValueError as exc:
        return "failed", f"Can't do that: {exc}. Nothing changed."
    if not store.set_job(mode, settings):
        return "failed", "The lineup is up. That waits for the next case."
    if mode == "appraisal":
        return "done", "Done. Appraisal job: no limits, every find counts."
    level = planner.LEVELS[settings["level"]]["label"].lower()
    return "done", (f"Done. Mastermind, {level}, {lb(settings['bag_lb'])} pounds, {settings['time_s']} seconds. "
                    + _summary(store))


# ---------- the job queue ----------

_TERMINAL = {"done", "clarify", "failed", "cancelled", "expired", "unsupported"}


class Radio:
    """One radio, one call at a time, a short line behind it."""

    def __init__(self, store_fn, clock=time.time, recorder=None, transcriber=None,
                 speak: bool = True, autostart: bool = True):
        self._store_fn = store_fn
        self._clock = clock
        self._recorder = recorder
        self._transcriber = transcriber
        self._speak = speak
        self._jobs: dict[str, dict] = {}
        self._order: deque[str] = deque()
        self._queue: deque[str] = deque()
        self._lock = threading.Condition()
        self._active: str | None = None
        self._seq = itertools.count(1)
        self._before_apply = None          # test hook: a reset or edit landing mid-call
        if autostart:
            threading.Thread(target=self._loop, name="radio", daemon=True).start()

    # ---------- submitting ----------

    def submit(self, source: str, text: str = "", job_id: str | None = None) -> tuple[dict, str]:
        """(job, outcome): outcome is new, duplicate, busy, or invalid."""
        if job_id is not None and not (isinstance(job_id, str) and _JOB_ID.fullmatch(job_id)):
            return {"error": "job_id must be 8-64 letters, digits, - or _"}, "invalid"
        if source == "text":
            text = (text or "").strip() if isinstance(text, str) else ""
            if not text:
                return {"error": "say something: the text is empty"}, "invalid"
            if len(text) > MAX_TEXT:
                return {"error": f"keep it under {MAX_TEXT} characters"}, "invalid"
        with self._lock:
            self._prune()
            if job_id and job_id in self._jobs:
                return dict(self._jobs[job_id]), "duplicate"
            mic_busy = source == "mic" and any(
                self._jobs[j]["source"] == "mic" and self._jobs[j]["state"] not in _TERMINAL
                for j in list(self._queue) + ([self._active] if self._active else []))
            if len(self._queue) >= QUEUE_MAX or mic_busy:
                narration.emit("radio_busy")
                return {"error": "dispatch is busy; one call at a time", "busy": True}, "busy"
            store = self._store_fn()
            now = self._clock()
            job = {
                "job_id": job_id or uuid.uuid4().hex[:16], "seq": next(self._seq), "source": source,
                "state": "queued", "transcript": text if source == "text" else "",
                "intent": None, "case_no": store.case_no(), "revision": None, "revision_after": None,
                "reply": "", "error": None, "clarification": None, "applied": False, "spoken": None,
                "created_at": now, "updated_at": now, "timings": {},
            }
            self._jobs[job["job_id"]] = job
            self._order.append(job["job_id"])
            self._queue.append(job["job_id"])
            self._lock.notify()
            return dict(job), "new"

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            self._prune()
            return [dict(self._jobs[j]) for j in reversed(self._order)][:limit]

    def status(self) -> dict:
        with self._lock:
            return {"active": self._active, "queued": len(self._queue), "queue_max": QUEUE_MAX}

    def _prune(self) -> None:
        now = self._clock()
        while self._order and (len(self._order) > KEEP_JOBS
                               or now - self._jobs[self._order[0]]["created_at"] > KEEP_SECONDS):
            old = self._order[0]
            if self._jobs[old]["state"] not in _TERMINAL:
                break
            self._order.popleft()
            self._jobs.pop(old, None)

    # ---------- running ----------

    def _set(self, job: dict, **fields) -> None:
        with self._lock:
            job.update(fields, updated_at=self._clock())

    def drain(self) -> int:
        """Run every queued call on this thread (tests, scripted demos)."""
        done = 0
        while True:
            with self._lock:
                if not self._queue:
                    return done
                job_id = self._queue.popleft()
                self._active = job_id
            self._run(self._jobs[job_id])
            done += 1

    def _loop(self) -> None:
        while True:
            with self._lock:
                while not self._queue:
                    self._lock.wait()
                job_id = self._queue.popleft()
                self._active = job_id
            self._run(self._jobs[job_id])

    def _run(self, job: dict) -> None:
        try:
            if self._clock() - job["created_at"] > QUEUED_TTL:
                self._set(job, state="expired", error="waited too long in line; call again")
                return
            if job["source"] == "mic" and not self._hear(job):
                return
            self._dispatch(job)
        except Exception as exc:
            log.exception("radio call failed")
            self._set(job, state="failed", error=f"dispatch error: {type(exc).__name__}")
        finally:
            with self._lock:
                if self._active == job["job_id"]:
                    self._active = None

    def _hear(self, job: dict) -> bool:
        """Mic calls: record, then transcribe. False (and a visible failure) if either fails."""
        from rig import listen
        if not config.env_str("OPENAI_API_KEY") and self._transcriber is None:
            self._set(job, state="failed", error="no OPENAI_API_KEY: the radio can't transcribe")
            narration.emit("radio_unavailable", tag="no_key")
            return False
        self._set(job, state="listening")
        start = self._clock()
        path = (self._recorder or listen.record_wav)(listen.listen_secs())
        job["timings"]["listen_s"] = round(self._clock() - start, 2)
        if not path:
            self._set(job, state="failed", error="mic unavailable or silent")
            narration.emit("radio_unavailable", tag="mic_dead")
            return False
        self._set(job, state="transcribing")
        start = self._clock()
        try:
            text = (self._transcriber or listen.transcribe)(path)
        finally:
            listen.discard(path)          # recordings are never kept
        job["timings"]["transcribe_s"] = round(self._clock() - start, 2)
        text = (text or "").strip()[:MAX_TEXT]
        if not text:
            self._set(job, state="failed", error="transcription came back empty")
            narration.emit("radio_unavailable", tag="static")
            return False
        self._set(job, transcript=text)
        return True

    def _dispatch(self, job: dict) -> None:
        store = self._store_fn()
        self._set(job, state="thinking")
        if store.case_no() != job["case_no"]:
            self._set(job, state="cancelled",
                      error=f"case {job['case_no']} closed while dispatch was listening; ask again")
            return
        intent = parse(job["transcript"])
        snap, plan = _view(store)
        self._set(job, intent=intent.as_dict(), revision=plan["revision"] if plan else None)
        if intent.name == "clarify":
            self._finish(job, "clarify", intent.args["message"], clarification=intent.args["message"])
            return
        if intent.name == "unsupported":
            self._finish(job, "unsupported", "Didn't catch a command. " + HELP)
            return
        if not intent.mutates:
            self._finish(job, "done", answer(intent, snap, plan))
            return
        self._set(job, state="applying")
        if self._before_apply:
            self._before_apply(job)
        snap_now, plan_now = _view(store)
        if snap_now["case_no"] != job["case_no"]:
            self._set(job, state="cancelled", error=f"case {job['case_no']} closed before the change landed")
            return
        if (plan_now and plan_now["revision"]) != job["revision"]:
            self._set(job, state="cancelled",
                      error=f"the plan moved (revision {job['revision']} to {plan_now and plan_now['revision']}) "
                            "while dispatch was working; say it again")
            return
        outcome, reply = apply(intent, store)
        after = mastermind.current(store)
        self._set(job, applied=outcome == "done", revision_after=after["revision"] if after else None)
        narration.observe(store)
        self._finish(job, outcome, reply,
                     error=reply if outcome == "failed" else None,
                     clarification=reply if outcome == "clarify" else None)

    def _finish(self, job: dict, state: str, reply: str, **extra) -> None:
        self._set(job, reply=reply, **extra)
        if not self._speak:
            self._set(job, state=state, spoken="off")
            return
        self._set(job, state="speaking" if state == "done" else state, spoken="queued")

        def spoken(result, job=job, final=state):
            self._set(job, spoken=result, **({"state": final} if job["state"] == "speaking" else {}))

        if not narration.emit("radio_reply", case_no=job["case_no"], dynamic=reply, on_done=spoken):
            self._set(job, spoken="dropped", **({"state": state} if job["state"] == "speaking" else {}))


_radio: Radio | None = None
_radio_lock = threading.Lock()


def radio(store_fn=None) -> Radio:
    global _radio
    with _radio_lock:
        if _radio is None:
            if store_fn is None:
                raise RuntimeError("radio not started")
            _radio = Radio(store_fn)
        return _radio


def set_radio(r: Radio | None) -> None:
    global _radio
    with _radio_lock:
        _radio = r
