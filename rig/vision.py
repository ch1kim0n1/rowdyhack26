"""Vision LLM: one still in, one exhibit JSON out.

No key, no call. A bad bbox is dropped and the label is kept.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import re

import cv2
import numpy as np

from rig import config
from rig.planner import clean_weight
from rig.store import clean_card, scrub_pan

log = logging.getLogger("rig.vision")

# Stronger vision than mini: logos and model lines survive. Override with OPENAI_VISION_MODEL.
OPENAI_MODEL = "gpt-4.1"
OPENAI_FALLBACK = "gpt-4.1-mini"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
PROMPT = (
    "Identify the single clearest physical object for a resale appraisal. "
    "Respond ONLY with JSON: "
    '{"item":"<brand and model>","desc":"<5 words>","category":"<broad type>",'
    '"value_usd":<number>,"weight_lb":<number>,"bbox":[x,y,w,h]}. '
    "item is the product a buyer would search, brand plus model "
    "(Sony WH-1000XM6, Razer BlackShark V2). Never answer with only the category "
    "(headphones, mouse) when a logo, colorway, or shape distinguishes it. "
    "Read logos and printed text. A gaming headset is not a flagship headphone: "
    "do not name or price a Razer near $70 as a Sony near $500, or the reverse. "
    "If the brand is visible but the model is not, stop at the brand and line you can support. "
    "Do not invent a flagship model. "
    "value_usd is the typical used US street price of that exact model, not the category average and not MSRP. "
    "weight_lb is the typical weight of that exact model in pounds, as listed in its specs; "
    "omit it if you cannot tell. "
    "bbox is normalized 0-1 around the object; omit it if unsure. "
    'If the object is a badge, keycard, school/student ID, or other ID card, set category to "badge", '
    "name it by issuer and card type (UTD Comet Card, Initech Employee Badge), "
    "value it as the access it opens, and add "
    '"card":{"name":"<cardholder>","id":"<ID number>","org":"<school or employer>",'
    '"role":"<STUDENT, FACULTY, STAFF...>","card_no":"<card number>",'
    '"issued":"<issue date>","expires":"<expiry date>"}. '
    "id is the cardholder's own ID number (student or employee number). "
    "A UT Dallas Comet Card is item \"UTD Comet Card\", org \"The University of Texas at Dallas\", "
    "from either side: the front is orange with \"The University of Texas at Dallas\" and "
    "\"COMET CARD\"; the back is white with a magnetic stripe and \"This card is your official UTD ID\". "
    "Its front prints the role (STUDENT) over the full name and \"UTD ID# <10 digits>\": "
    "those 10 digits are id. Its back prints the name and a line "
    "\"<16 digits>_<digit>_<M/D/YYYY> <time>\": the 16 digits are card_no and the date is issued. "
    "Skip the small upside-down number above the stripe, the phone numbers, and the fine print. "
    "Copy each card field exactly as printed; omit any field you cannot read on the side "
    "you see, and omit card entirely for anything that is not a badge or ID. "
    "Never guess a name or number. "
    'A credit, debit, or bank card is not loot: answer {"item": null} and transcribe nothing from it. '
    'If nothing is a clear object, {"item": null}.'
)
EXITS_PROMPT = (
    "Mark the room's escape routes for a heist crew. "
    "Respond ONLY with JSON: "
    '{"item":"<what it is, e.g. DOOR / WINDOW / FIRE EXIT>","desc":"<5 words>",'
    '"category":"exit","value_usd":0,"bbox":[x,y,w,h]}. '
    "bbox is normalized 0-1 around the exit; omit it if unsure. "
    'If no exit is visible, {"item": null}.'
)
# Multi-object pass: every object the model can actually name and price, not
# just the clearest one, so the scene streams into the Tiger ledger for analysis.
# The same per-item fields and the same badge / payment-card safeguards as the
# single prompt. `worth_filing` enforces the "named and priced" rule on the reply.
MULTI_PROMPT = (
    "Identify EVERY distinct item in this frame that you can recognize and that has "
    "resale value — not only the clearest one, and including things further back: "
    "headphones, laptops, phones, "
    "cameras, watches, jewelry, bags, tools, appliances, and the like. "
    "List an object ONLY if you can tell what it is. Leave out anything you would "
    "have to call unknown or unclear, blurry background shapes and silhouettes, "
    "people and the clothes they are wearing, and the building itself (walls, "
    "ceiling, floor, columns, windows, doors, built-in lights). "
    'Respond ONLY with JSON of the form {"objects":[ ... ]} where each element is '
    '{"item":"<brand and model>","desc":"<5 words>","category":"<broad type>",'
    '"value_usd":<number>,"weight_lb":<number>,"bbox":[x,y,w,h]}. '
    "item is the product a buyer would search, brand plus model when legible "
    "(Sony WH-1000XM6, Razer BlackShark V2); if only the brand is clear, stop at the brand; "
    "if neither, use a plain description (wooden chair, desk fan). "
    "value_usd is the typical used US street price of that exact item, not MSRP and not a category average; "
    "leave out anything worth nothing. "
    "weight_lb is the item's typical weight in pounds from its specs; omit it if you cannot tell. "
    "bbox is normalized 0-1 [x,y,w,h] around that object; omit it if unsure. "
    "List each object once, most prominent first. "
    'If an object is a badge, keycard, or school/student ID, set its category to "badge", '
    "name it by issuer and card type, value it as the access it opens, and add a "
    '"card":{"name":"<cardholder>","id":"<ID number>","org":"<school or employer>",'
    '"role":"<STUDENT, STAFF...>","card_no":"<card number>","issued":"<issue date>",'
    '"expires":"<expiry date>"} holding only the text you can actually read. '
    'A credit, debit, or bank card is NOT loot: omit it entirely and transcribe nothing from it. '
    'If you see no clear objects, respond {"objects":[]}.'
)

_openai = None
_anthropic = None
_last_call_failed = False
# A hung model call stalls every look behind it. 20s and the walk moves on.
LLM_TIMEOUT = 20

OFFLINE_CATALOG: list[dict] = [
    {
        "item": "Sony WH-1000XM6",
        "desc": "wireless noise-canceling headphones",
        "category": "headphones",
        "value_usd": 480.0,
        "weight_lb": 0.56,
        "bbox": [0.22, 0.25, 0.45, 0.50],
    },
    {
        "item": "Razer BlackShark V2",
        "desc": "esports wired gaming headset",
        "category": "headset",
        "value_usd": 70.0,
        "weight_lb": 0.58,
        "bbox": [0.30, 0.28, 0.40, 0.46],
    },
    {
        "item": "Vintage Rolex Submariner",
        "desc": "oyster perpetual steel dive watch",
        "category": "watch",
        "value_usd": 4200.0,
        "weight_lb": 0.34,
        "bbox": [0.35, 0.35, 0.28, 0.38],
    },
    {
        "item": "Leica M3 Rangefinder",
        "desc": "vintage 35mm film camera",
        "category": "camera",
        "value_usd": 1850.0,
        "weight_lb": 1.29,
        "bbox": [0.25, 0.30, 0.42, 0.38],
    },
    {
        "item": "First-Ed. Hemingway",
        "desc": "hardcover clothbound novel",
        "category": "book",
        "value_usd": 950.0,
        "weight_lb": 1.6,
        "bbox": [0.28, 0.22, 0.38, 0.52],
    },
    {
        "item": "Brass Desk Lamp",
        "desc": "adjustable vintage reading lamp",
        "category": "lamp",
        "value_usd": 180.0,
        "weight_lb": 5.5,
        "bbox": [0.20, 0.18, 0.35, 0.60],
    },
    {
        "item": "UTD Comet Card",
        "desc": "student photo ID card",
        "category": "badge",
        "value_usd": 650.0,
        "weight_lb": 0.04,
        "bbox": [0.32, 0.30, 0.30, 0.40],
        # Made-up values in the real card's format; Temoc is the UTD mascot.
        "card": {"name": "Temoc Comet", "id": "2020000001",
                 "org": "The University of Texas at Dallas", "role": "STUDENT"},
    },
]

_fallback_idx: int = 0


def frame_hash(image_b64: str) -> int | None:
    """8x8 average hash of the still, so one view always maps to one stand-in.

    Downscaled to grayscale first, so re-encoding jitter does not change the
    hash: the same shelf hashes the same even as the feed re-compresses it.
    """
    try:
        buf = base64.b64decode(image_b64)
        arr = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_GRAYSCALE)
        if arr is None:
            return None
        small = cv2.resize(arr, (8, 8)).astype(np.float32)
        bits = (small > float(small.mean())).flatten()
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)
        return value
    except Exception:
        return None


def offline_fallback(image_b64: str | None = None) -> dict:
    """A canned exhibit for when the network is gone.

    With a still, the catalog entry is picked by the frame's hash, so the
    same view keeps returning the same item and the dedup ledger stays
    honest. Without one, the catalog cycles.
    """
    global _fallback_idx
    digest = frame_hash(image_b64) if image_b64 else None
    if digest is not None:
        spec = OFFLINE_CATALOG[digest % len(OFFLINE_CATALOG)]
    else:
        spec = OFFLINE_CATALOG[_fallback_idx % len(OFFLINE_CATALOG)]
        _fallback_idx += 1
    item = dict(spec)
    item["source"] = "offline"
    if item.get("bbox"):
        item["bbox"] = list(item["bbox"])
    if item.get("card"):
        item["card"] = dict(item["card"])
    log.info("offline fallback: exhibit '%s' ($%s)", item["item"], item["value_usd"])
    return item


def reset_offline_fallback() -> None:
    global _fallback_idx
    _fallback_idx = 0


def exits_mode() -> bool:
    """RIG_MODE=exits swaps the appraisal prompt for the case-the-exits one."""
    return config.env_str("RIG_MODE").lower() in {"exits", "exit"}


def active_prompt() -> str:
    return EXITS_PROMPT if exits_mode() else PROMPT


MAX_OBJECTS_HI = 30


def max_objects() -> int:
    """How many objects one multi-object look may file. VISION_MAX_OBJECTS."""
    return config.env_int("VISION_MAX_OBJECTS", 8, lo=1, hi=MAX_OBJECTS_HI)


# Names a model falls back on when it has not actually recognized the thing.
# "Unknown brand headphones" is recognized (it's headphones); "unknown object" is not.
_UNIDENTIFIED = re.compile(
    r"\b(unknown(?!\s+(?:brand|make|model))|unidentified|unidentifiable|unclear|"
    r"unrecognized|unrecognizable|indistinct|silhouette|background|person|people)\b", re.I)


def worth_filing(obj: dict) -> bool:
    """A multi-object find earns a place on screen and in the ledger only when
    the model named it and put a price on it (estimated or not). Guesses like
    "Unknown dark headset", background silhouettes, people, and $0 items are
    dropped here even if the prompt failed to keep them out of the reply."""
    return obj["value_usd"] > 0 and not _UNIDENTIFIED.search(obj["item"])


def identify(image_b64: str) -> dict | None:
    """The single clearest object — the compatibility path for callers and tests
    that want one exhibit. The live walk uses identify_all."""
    global _last_call_failed
    if config.env_flag("RIG_OFFLINE", False):
        log.info("RIG_OFFLINE active; using offline fallback")
        return offline_fallback(image_b64)

    from rig import vultr

    providers = []
    if config.env_str("OPENAI_API_KEY"):
        providers.append(("openai", _identify_openai))
    if config.env_str("ANTHROPIC_API_KEY"):
        providers.append(("anthropic", _identify_anthropic))
    if vultr.enabled():
        # Vultr runs the CV model. VULTR_VISION_FIRST moves it ahead of the
        # others; otherwise it backs them up before the offline catalog.
        if vultr.vision_first():
            providers.insert(0, ("vultr", vultr.identify))
        else:
            providers.append(("vultr", vultr.identify))

    if not providers:
        log.warning("no vision key set; using offline fallback")
        return offline_fallback(image_b64)

    for name, call in providers:
        res = call(image_b64)
        if res is not None:
            res.setdefault("source", name)   # provenance for the Defender Report
            return res
        if not _last_call_failed:
            # The provider answered and saw no exhibit; the next one won't either.
            return None
        log.warning("%s vision call failed; trying the next provider", name)

    log.warning("all vision providers failed; using offline fallback")
    return offline_fallback(image_b64)


def identify_all(image_b64: str) -> list[dict]:
    """Every named, priced object in the frame, not just the clearest — the live
    walk's eyes.

    One model call returns a JSON array; each element is normalized exactly like
    identify() (same value, bbox, badge, and payment-card scrubbing), then kept
    only if it is `worth_filing`. Uses the single-object path for exits mode and
    the offline catalog only when offline is asked for or no provider is set up;
    a provider that fails returns an empty list, never a stand-in.
    """
    global _last_call_failed
    if config.env_flag("RIG_OFFLINE", False):
        return [offline_fallback(image_b64)]
    if exits_mode():                       # exits are few; the single prompt is plenty
        one = identify(image_b64)
        return [one] if one else []

    from rig import vultr
    providers: list[tuple[str, object]] = []
    if config.env_str("OPENAI_API_KEY"):
        providers.append(("openai", _openai_raw))
    if config.env_str("ANTHROPIC_API_KEY"):
        providers.append(("anthropic", _anthropic_raw))
    if vultr.enabled():
        entry = ("vultr", vultr.raw)
        providers.insert(0, entry) if vultr.vision_first() else providers.append(entry)

    if not providers:
        return [offline_fallback(image_b64)]

    limit = max_objects()
    for name, raw in providers:
        text = raw(image_b64, MULTI_PROMPT)
        if text is None:
            if _last_call_failed:
                log.warning("%s multi-object vision failed; trying the next provider", name)
                continue
            return []                      # provider answered and saw nothing
        try:
            # Filter before the cap, so a guess can't take a real find's slot.
            objs = [o for o in parse_many(text, MAX_OBJECTS_HI) if worth_filing(o)][:limit]
        except (json.JSONDecodeError, ValueError, IndexError, AttributeError):
            _last_call_failed = True
            log.warning("%s multi-object vision returned nothing usable: %s", name, text[:180])
            continue
        for obj in objs:
            obj.setdefault("source", name)
        return objs

    # A live provider is set up and it failed this once: file nothing. Inventing
    # a catalog item here would put a find on the ledger that the camera never saw.
    log.warning("all multi-object vision providers failed; nothing filed for this look")
    return []


def _openai_raw(image_b64: str, prompt: str) -> str | None:
    model = config.env_str("OPENAI_VISION_MODEL", OPENAI_MODEL)
    text = _openai_still(model, image_b64, prompt, max_tokens=900)
    if text is None and model != OPENAI_FALLBACK:
        text = _openai_still(OPENAI_FALLBACK, image_b64, prompt, max_tokens=900)
    return text


def _anthropic_raw(image_b64: str, prompt: str) -> str | None:
    global _last_call_failed
    try:
        resp = _anthropic_client().messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=900,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        _last_call_failed = False
        return resp.content[0].text
    except Exception:
        _last_call_failed = True
        log.exception("vision call failed")
        return None


def _identify_openai(image_b64: str) -> dict | None:
    global _last_call_failed
    model = config.env_str("OPENAI_VISION_MODEL", OPENAI_MODEL)
    prompt = active_prompt()
    text = _openai_still(model, image_b64, prompt)
    if text is None and model != OPENAI_FALLBACK:
        log.warning("vision model %s failed; retrying with %s", model, OPENAI_FALLBACK)
        text = _openai_still(OPENAI_FALLBACK, image_b64, prompt)
    if text is None:
        return None
    try:
        parsed = parse_response(text)
    except (json.JSONDecodeError, ValueError, IndexError, AttributeError):
        # The call landed but the body is junk — that's a failure, not an
        # empty frame, so the next provider still gets its shot.
        _last_call_failed = True
        log.warning("vision returned nothing usable: %s", text[:180])
        return None
    if parsed is None:
        log.info("no exhibit in this frame")
    return parsed


def _openai_still(model: str, image_b64: str, prompt: str = PROMPT,
                  max_tokens: int = 300) -> str | None:
    global _last_call_failed
    try:
        resp = _openai_client().chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}",
                        "detail": "high",
                    }},
                ],
            }],
        )
        _last_call_failed = False
        return resp.choices[0].message.content or ""
    except Exception:
        _last_call_failed = True
        log.exception("vision call failed (%s)", model)
        return None


def _identify_anthropic(image_b64: str) -> dict | None:
    global _last_call_failed
    text = ""
    try:
        resp = _anthropic_client().messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg", "data": image_b64,
                    }},
                    {"type": "text", "text": active_prompt()},
                ],
            }],
        )
        text = resp.content[0].text
        _last_call_failed = False
    except Exception:
        _last_call_failed = True
        log.exception("vision call failed")
        return None
    try:
        return parse_response(text)
    except (json.JSONDecodeError, ValueError, IndexError, AttributeError):
        _last_call_failed = True   # junk body is a failed call, not "no exhibit"
        log.warning("vision returned nothing usable: %s", text[:180])
        return None


def _openai_client():
    global _openai
    if _openai is None:
        from openai import OpenAI
        _openai = OpenAI(timeout=LLM_TIMEOUT)
    return _openai


def _anthropic_client():
    global _anthropic
    if _anthropic is None:
        from anthropic import Anthropic
        _anthropic = Anthropic(timeout=LLM_TIMEOUT)
    return _anthropic


def parse_response(text: str) -> dict | None:
    """One exhibit from a single-object model reply."""
    return _coerce_object(_load_json(text))


def _coerce_object(data) -> dict | None:
    """Normalize one model-supplied object into an exhibit dict, or None.

    The one gate every provider's output flows through — single or multi — so
    the value clamp, bbox validation, and payment-card scrubbing can never be
    skipped by a new call path."""
    if not isinstance(data, dict):
        return None
    name = data.get("item")
    if not isinstance(name, str) or not name.strip():
        return None
    try:
        value = float(data.get("value_usd") or 0)
    except (TypeError, ValueError):
        value = 0.0
    if not math.isfinite(value) or value < 0:
        value = 0.0   # inf/nan or a negative "price" must not poison the ledger
    parsed = {
        # A payment-card number is masked to its last four before anything
        # logs or files it; school/badge numbers pass through untouched.
        "item": scrub_pan(name.strip()),
        "desc": scrub_pan(data["desc"].strip()) if isinstance(data.get("desc"), str) else "",
        "category": (data.get("category") or "").strip() if isinstance(data.get("category"), str) else "",
        "value_usd": value,
        "weight_lb": clean_weight(data.get("weight_lb")),
        "bbox": valid_bbox(data.get("bbox")),
    }
    if parsed["category"].lower() == "badge":
        parsed["category"] = "badge"
        card = clean_card(data.get("card"))
        if card:
            parsed["card"] = card
    return parsed


def parse_many(text: str, limit: int) -> list[dict]:
    """Every exhibit from a multi-object reply: {"objects":[...]} or a bare array,
    tolerating a single-object reply too. Raises on a body that holds no JSON at
    all, so the caller can fall through to the next provider."""
    try:
        data = _extract_json(text)
    except json.JSONDecodeError:
        # A long list can hit the token cap mid-object. The objects that did
        # arrive whole are still good: keep them rather than lose the look.
        data = _salvage_objects(text)
        if not data:
            raise
    if isinstance(data, dict):
        arr = data.get("objects")
        if arr is None:
            one = _coerce_object(data)      # model answered with a lone object
            return [one] if one else []
    elif isinstance(data, list):
        arr = data
    else:
        return []
    if not isinstance(arr, list):
        return []
    out: list[dict] = []
    for element in arr:
        obj = _coerce_object(element)
        if obj:
            out.append(obj)
        if len(out) >= limit:
            break
    return out



def _salvage_objects(text: str) -> list:
    """The complete {...} elements at the front of a cut-off JSON array."""
    start = text.find("[")
    if start < 0:
        return []
    decoder = json.JSONDecoder()
    out, pos = [], start + 1
    while True:
        while pos < len(text) and (text[pos].isspace() or text[pos] == ","):
            pos += 1
        if pos >= len(text) or text[pos] != "{":
            return out
        try:
            obj, pos = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            return out
        out.append(obj)


def valid_bbox(raw) -> list[float] | None:
    """[x, y, w, h] in 0-1, with the box large enough to be a real object.

    Models overshoot the frame by a percent or two; clamp edges back in
    instead of dropping a good marker. A box still too small is dropped.
    """
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        x, y, w, h = (float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    x = min(max(x, 0.0), 1.0)
    y = min(max(y, 0.0), 1.0)
    w = min(max(w, 0.0), 1.0 - x)
    h = min(max(h, 0.0), 1.0 - y)
    if w < 0.05 or h < 0.05:
        return None
    return [round(x, 4), round(y, 4), round(w, 4), round(h, 4)]


def _load_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("vision JSON was not an object")
    return data


def _extract_json(text: str):
    """A dict OR a list from a model reply, tolerating fences and surrounding
    prose. Raises json.JSONDecodeError when nothing parses."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, re.S)
    if fenced:
        return json.loads(fenced.group(1))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for open_c, close_c in (("[", "]"), ("{", "}")):
            start, end = text.find(open_c), text.rfind(close_c)
            if 0 <= start < end:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    continue
        raise
