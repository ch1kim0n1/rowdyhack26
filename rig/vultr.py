"""Vultr Serverless Inference: the CV model that recognizes items, and the
analysis brain that reads the ledger back.

Vultr's inference API is OpenAI-compatible
(https://api.vultrinference.com/v1, `Authorization: Bearer <key>`), and its
catalog carries multimodal models that take a base64 JPEG. So we reuse the
`openai` SDK that is already a dependency, just pointed at Vultr's base URL —
no new package for vision.

Nothing here imports or calls out unless `VULTR_API_KEY` is set, so the
offline demo and the test suite are untouched.
"""
from __future__ import annotations

import json
import logging

from rig import config

log = logging.getLogger("rig.vultr")

BASE_URL = "https://api.vultrinference.com/v1"
# Cheap, image-capable, and good at structured JSON. Override per deployment.
DEFAULT_VISION_MODEL = "deepseek-v4-flash-0731"
DEFAULT_TEXT_MODEL = "deepseek-v4.1-flash"
TIMEOUT = 20
# The default text model reasons before it answers, and those reasoning tokens
# count against max_tokens: at 220 the whole budget went to thinking and the
# reply came back empty. The prompts still ask for 2-3 sentences.
TEXT_MAX_TOKENS = 1200
# A busy frame lists many objects; at 900 the JSON was cut off mid-object.
VISION_MAX_TOKENS = 1500

_client = None


def _max_tokens(default: int) -> int:
    """VULTR_MAX_TOKENS overrides both caps: a model that thinks hard before it
    answers (GLM 5.3) needs far more room than the defaults give it."""
    return config.env_int("VULTR_MAX_TOKENS", default, lo=64, hi=200_000)


def _effort() -> dict:
    """VULTR_REASONING_EFFORT=low|medium|high is passed to models that reason.
    Unset sends nothing, so models that don't take the option are unaffected."""
    effort = config.env_str("VULTR_REASONING_EFFORT").lower()
    return {"reasoning_effort": effort} if effort in {"low", "medium", "high"} else {}


def enabled() -> bool:
    return bool(config.env_str("VULTR_API_KEY"))


def vision_first() -> bool:
    """VULTR_VISION_FIRST=1 makes Vultr the primary CV engine, ahead of
    OpenAI and Anthropic — the 'Vultr runs the vision model' setup."""
    return config.env_flag("VULTR_VISION_FIRST", False)


def _vultr_client():
    """An OpenAI SDK client pointed at Vultr. Lazy: no key, no import, no call."""
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(
            api_key=config.env_str("VULTR_API_KEY"),
            base_url=config.env_str("VULTR_BASE_URL", BASE_URL),
            # A long think can outlast the default; VULTR_TIMEOUT raises it.
            timeout=config.env_float("VULTR_TIMEOUT", TIMEOUT, lo=5.0),
        )
    return _client


def raw(image_b64: str, prompt: str) -> str | None:
    """One still + prompt in, the model's raw reply text out (or None on a failed
    call). Shared by the single- and multi-object paths; flags
    `vision._last_call_failed` so vision.py can fall through to the next provider."""
    from rig import vision  # imported here to avoid a circular import at load
    model = config.env_str("VULTR_VISION_MODEL", DEFAULT_VISION_MODEL)
    try:
        resp = _vultr_client().chat.completions.create(
            model=model,
            max_tokens=_max_tokens(VISION_MAX_TOKENS),
            **_effort(),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}",
                    }},
                ],
            }],
        )
        vision._last_call_failed = False
        return resp.choices[0].message.content or ""
    except Exception:
        vision._last_call_failed = True
        log.exception("vultr vision call failed (%s)", model)
        return None


def identify(image_b64: str) -> dict | None:
    """One still in, one exhibit dict out — the same contract as the OpenAI and
    Anthropic providers. Returns None on a clean 'no exhibit', raises nothing:
    a failed call is reported through `last_call_failed` so vision.py can fall
    through to the next provider exactly as it does for the others.
    """
    from rig import vision  # imported here to avoid a circular import at load
    text = raw(image_b64, vision.active_prompt())
    if text is None:
        return None
    try:
        return vision.parse_response(text)
    except (json.JSONDecodeError, ValueError, IndexError, AttributeError):
        vision._last_call_failed = True   # junk body is a failed call, not "no exhibit"
        log.warning("vultr vision returned nothing usable: %s", text[:180])
        return None


_ANALYSIS_PROMPT = (
    "You are a dispatch analyst for an authorized asset-appraisal walkthrough. "
    "Below is the filed evidence ledger as JSON. Write 2-3 short sentences for "
    "the assessment team: the highest-value cluster, how much of the total is a "
    "firm comp versus an estimate, and how many access credentials were seen. "
    "Use only what is in the ledger; invent nothing, recommend nothing to take. "
    "Ledger:\n{ledger}"
)


def analyze(rows: list[dict], take: float) -> str | None:
    """A short, grounded debrief of the ledger, from a Vultr text model.

    Returns None when disabled or on any failure, so the caller can simply
    skip the insight line rather than handle an error.
    """
    if not enabled() or not rows:
        return None
    model = config.env_str("VULTR_TEXT_MODEL", DEFAULT_TEXT_MODEL)
    slim = [{
        "item": r.get("item"), "category": r.get("category"),
        "value_usd": r.get("value_usd"), "estimated": r.get("estimated"),
        "price_source": r.get("price_source"),
    } for r in rows[:60]]
    ledger = json.dumps({"total_take": round(take, 2), "exhibits": slim})
    try:
        resp = _vultr_client().chat.completions.create(
            model=model,
            max_tokens=_max_tokens(TEXT_MAX_TOKENS),
            **_effort(),
            messages=[{"role": "user", "content": _ANALYSIS_PROMPT.format(ledger=ledger)}],
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        log.warning("vultr analysis failed", exc_info=True)
        return None


_ANALYTICS_PROMPT = (
    "You are a dispatch analyst for an authorized asset-appraisal walkthrough. "
    "Below are precomputed analytics from the live event database (a TimescaleDB "
    "hypertable): the top items by value this case, the take bucketed over time, "
    "and the most valuable items seen across every past walk. In 2-3 short "
    "sentences give the team the headline — what is driving the value right now "
    "and any trend over time. Use only these numbers; invent nothing, recommend "
    "nothing to take.\nAnalytics:\n{stats}"
)


def analyze_analytics(stats: dict) -> str | None:
    """Vultr's reasoning on top of the fast TimescaleDB analytics. The hypertable
    does the aggregation; Vultr turns the numbers into a one-line read. None when
    disabled or on failure, so the caller still returns the raw stats."""
    if not enabled() or not stats:
        return None
    model = config.env_str("VULTR_TEXT_MODEL", DEFAULT_TEXT_MODEL)
    try:
        resp = _vultr_client().chat.completions.create(
            model=model,
            max_tokens=_max_tokens(TEXT_MAX_TOKENS),
            **_effort(),
            messages=[{"role": "user",
                       "content": _ANALYTICS_PROMPT.format(stats=json.dumps(stats, default=str))}],
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        log.warning("vultr analytics failed", exc_info=True)
        return None
