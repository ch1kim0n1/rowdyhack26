"""Sold-listing comps, provider-agnostic. A miss asks for that exact model's
used price.

Providers (COMPS_PROVIDER): "ebayapi" — the official eBay Browse API, free
developer account (EBAY_CLIENT_ID/EBAY_CLIENT_SECRET), survives bot-walls;
"ebay" — scrapes the public sold-listings page, no key but blocked on some
networks; "serpapi" — sponsor API when SERPAPI_API_KEY exists; "off" — skip.
The lookup is capped at about 3 seconds
so a slow source can't stall the walk. A category word ("headphones") is not
a price: comps have to name the same product, so a Razer listing cannot set
the price of a Sony.
"""
from __future__ import annotations

import json
import logging
import re
import statistics
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from rig import config

log = logging.getLogger("rig.pricing")

_cache: dict = {}   # item name -> (price, provider); "quote:" prefixed keys -> float
_openai = None
# None = no runtime override yet; read SERPAPI_ENABLED lazily so .env values
# count even though this module is imported before load_env() runs.
_serpapi_enabled: bool | None = None
TIMEOUT = 3
LLM_TIMEOUT = 15


def is_serpapi_enabled() -> bool:
    if _serpapi_enabled is not None:
        return _serpapi_enabled
    return config.env_flag("SERPAPI_ENABLED", False)


def set_serpapi_enabled(enabled: bool) -> bool:
    global _serpapi_enabled
    _serpapi_enabled = bool(enabled)
    log.info("serpapi pricing is now %s", "enabled" if _serpapi_enabled else "disabled")
    return _serpapi_enabled


def toggle_serpapi() -> bool:
    return set_serpapi_enabled(not is_serpapi_enabled())
# A category is not a model. Comps for these words mix a $70 headset with a $500 one.
_GENERIC = {
    "headphones", "headphone", "headset", "earbuds", "earbud", "mouse", "keyboard",
    "chair", "cup", "book", "lamp", "watch", "camera", "phone", "laptop", "speaker",
    "controller", "bottle", "mug", "monitor", "tablet",
}
_QUOTE = (
    "Typical used resale price in US dollars for this exact product. "
    "Not MSRP and not the category average. "
    "A Razer gaming headset near $70 is not a Sony WH-1000XM6 near $500. "
    "Product: {name}\n"
    'Reply JSON {{"value_usd": <number>}}.'
)


def market_value(item_name: str) -> tuple[float | None, str]:
    """(price, comps-provider). price None = no matching sold comps."""
    key = item_name.strip().lower()
    if not key:
        return None, "none"
    cached = _cache.get(key)
    if cached is not None:
        return cached
    if len(_cache) >= 1024:
        _cache.clear()   # bounded: a long walk can't grow this forever
    price, source = _lookup(item_name.strip()[:120])
    if price is not None:
        _cache[key] = (price, source)
    return price, source


def resolve(item_name: str, llm_value) -> tuple[float, bool]:
    """(price, estimated). estimated is True when sold comps missed."""
    price, estimated, _source = resolve_detailed(item_name, llm_value)
    return price, estimated


def resolve_detailed(item_name: str, llm_value) -> tuple[float, bool, str]:
    """(price, estimated, source). source explains where the number came from."""
    market, source = market_value(item_name)
    if market is not None:
        return market, False, source
    quote = _model_quote(item_name)
    if quote is not None:
        return quote, True, "model_quote"
    try:
        return round(float(llm_value or 0), 2), True, "vision"
    except (TypeError, ValueError):
        return 0.0, True, "vision"


WHY = {
    "ebay": "priced from live eBay sold-listing comps",
    "ebayapi": "priced from live eBay listings (official Browse API)",
    "serpapi": "priced from live eBay sold-listing comps",
    "model_quote": "no sold comps; priced by model quote",
    "vision": "vision estimate only; nothing to compare against",
    "credential": "credential cloned; access, not merchandise",
}


def finalize_exhibit(parsed: dict, exits: bool = False) -> dict:
    """The last step before the ledger, shared by the hub's scan loop and the
    rover's so the two paths can't drift. Exits are never for sale; everything
    else rides the pricing ladder."""
    if exits or parsed.get("category") == "exit":
        # Escape routes aren't for sale: skip the pricing ladder entirely.
        parsed["value_usd"] = 0.0
        parsed["estimated"] = False
        parsed["price_source"] = "exit"
        parsed["why"] = ("offline catalog; exits mode" if parsed.get("source") == "offline"
                         else "exit scouted; not for sale")
        return parsed
    if parsed.get("category") == "badge":
        # A badge has no resale comps: its value is the access, the model's call.
        parsed["estimated"] = True
        parsed["price_source"] = "credential"
        why = WHY["credential"]
        parsed["why"] = ("offline catalog; " + why) if parsed.get("source") == "offline" else why
        return parsed
    price, estimated, source = resolve_detailed(parsed["item"], parsed["value_usd"])
    parsed["value_usd"] = price
    parsed["estimated"] = estimated
    parsed["price_source"] = source
    why = WHY.get(source, "")
    if parsed.get("source") == "offline":
        why = ("offline catalog; " + why) if why else "offline catalog"
    parsed["why"] = why
    return parsed


def comps(item_name: str, rows: list) -> float | None:
    """Median sold price of listings that name this product, not the category."""
    needed = _needed(item_name)
    if not needed:
        return None
    prices = []
    for row in rows:
        price = _extracted(row)
        if price is None or price <= 0:
            continue
        title = str(row.get("title") or "").lower()
        if all(token in title for token in needed):
            prices.append(price)
    if not prices:
        return None
    return round(statistics.median(prices), 2)


def _needed(item_name: str) -> list[str]:
    tokens = _tokens(item_name)
    specific = [t for t in tokens if t not in _GENERIC and len(t) >= 3]
    models = [t for t in specific if any(c.isdigit() for c in t) and len(t) >= 4]
    if models:
        words = [t for t in specific if t not in models and len(t) >= 4]
        return (words[:1] + models[:1]) if words else models[:1]
    return [t for t in specific if len(t) >= 5][:2]


def _tokens(item_name: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", item_name.lower())


def _extracted(row: dict) -> float | None:
    extracted = (row.get("price") or {}).get("extracted")
    try:
        return float(extracted) if extracted is not None else None
    except (TypeError, ValueError):
        return None


def comps_provider() -> str:
    """COMPS_PROVIDER: ebayapi | ebay | serpapi | off. Default: serpapi when
    its key is configured, else the official eBay Browse API when
    EBAY_CLIENT_ID/EBAY_CLIENT_SECRET are set (free dev account, 5k calls/day),
    else eBay's public sold-listings page — free but blocked on some networks."""
    provider = config.env_str("COMPS_PROVIDER").lower()
    if provider in ("ebayapi", "ebay", "serpapi"):
        return provider
    if provider in ("off", "none"):
        return "off"
    if config.env_str("SERPAPI_API_KEY"):
        return "serpapi"
    if config.env_str("EBAY_CLIENT_ID") and config.env_str("EBAY_CLIENT_SECRET"):
        return "ebayapi"
    return "ebay"


def _lookup(item_name: str) -> tuple[float | None, str]:
    if not is_serpapi_enabled():   # the comps switch, whichever provider serves
        log.info("comps pricing is disabled; pricing %s from its model", item_name)
        return None, "none"
    provider = comps_provider()
    rows = None
    if provider == "serpapi":
        rows = _serpapi_rows(item_name)
    elif provider == "ebayapi":
        rows = _ebayapi_rows(item_name)
    elif provider == "ebay":
        rows = _ebay_rows(item_name)
    if rows is None:
        return None, provider
    price = comps(item_name, rows)
    if price is None:
        log.info("no sold comps matched %s", item_name)
    return price, provider


def _serpapi_rows(item_name: str) -> list | None:
    api_key = config.env_str("SERPAPI_API_KEY")
    if not api_key:
        log.info("SERPAPI_API_KEY is unset; pricing %s from its model", item_name)
        return None
    query = urlencode({
        "engine": "ebay",
        "_nkw": item_name,
        "LH_Sold": "1",
        "api_key": api_key,
    })
    try:
        with urlopen("https://serpapi.com/search.json?" + query, timeout=TIMEOUT) as resp:
            data = json.load(resp)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        log.warning("serpapi lookup failed for %s", item_name, exc_info=True)
        return None
    return data.get("organic_results") or []


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _ebay_rows(item_name: str) -> list | None:
    """No-key comps: eBay's public sold-listings search page, scraped into the
    same {title, price.extracted} shape SerpAPI returns."""
    query = urlencode({"_nkw": item_name, "LH_Sold": "1", "LH_Complete": "1"})
    req = Request("https://www.ebay.com/sch/i.html?" + query,
                  headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            html = resp.read(2 * 1024 * 1024).decode("utf-8", "replace")
    except (URLError, TimeoutError, OSError):
        log.warning("ebay comps fetch failed for %s", item_name, exc_info=True)
        return None
    titles = re.findall(r'class="s-item__title[^"]*"[^>]*>(.*?)</', html, re.S)
    prices = re.findall(r'class="s-item__price[^"]*"[^>]*>(.*?)</span>', html, re.S)
    rows = []
    for title, price_html in zip(titles, prices, strict=False):
        match = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)", price_html)
        if not match:
            continue
        rows.append({"title": re.sub(r"<[^>]+>", "", title),
                     "price": {"extracted": float(match.group(1).replace(",", ""))}})
    return rows


_ebay_tok: tuple[str, float] | None = None   # (token, epoch expiry)


def _ebay_token() -> str | None:
    """Client-credentials token for the official Browse API. Cached until a
    minute before expiry; minted once per boot in the common case."""
    global _ebay_tok
    if _ebay_tok is not None and _ebay_tok[1] - 60 > time.time():
        return _ebay_tok[0]
    client_id = config.env_str("EBAY_CLIENT_ID")
    secret = config.env_str("EBAY_CLIENT_SECRET")
    if not client_id or not secret:
        return None
    import base64
    body = urlencode({
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }).encode()
    req = Request(
        "https://api.ebay.com/identity/v1/oauth2/token",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "Basic " + base64.b64encode(
                f"{client_id}:{secret}".encode()).decode(),
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            data = json.load(resp)
        _ebay_tok = (data["access_token"],
                     time.time() + float(data.get("expires_in", 7200)))
        return _ebay_tok[0]
    except (URLError, TimeoutError, json.JSONDecodeError, KeyError, OSError):
        log.warning("ebay oauth token failed", exc_info=True)
        return None


def _ebayapi_rows(item_name: str) -> list | None:
    """Official eBay Browse API: live used/refurbished listings for the named
    product. Free developer account; not sold-only history, but real market
    prices that survive bot-walls the public page hits."""
    token = _ebay_token()
    if not token:
        return None
    query = urlencode({
        "q": item_name,
        "limit": "10",
        # 3000 used, 2750 open box, 2000 refurb — the resale market, not retail
        "filter": "condition_ids:{3000|2750|2000}",
    })
    req = Request(
        "https://api.ebay.com/buy/browse/v1/item_summary/search?" + query,
        headers={"Authorization": "Bearer " + token,
                 "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            data = json.load(resp)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        log.warning("ebayapi lookup failed for %s", item_name, exc_info=True)
        return None
    rows = []
    for item in data.get("itemSummaries") or []:
        value = (item.get("price") or {}).get("value")
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        rows.append({"title": item.get("title"),
                     "price": {"extracted": value}})
    return rows


def _openai_client():
    global _openai
    if _openai is None:
        from openai import OpenAI
        _openai = OpenAI(timeout=LLM_TIMEOUT)
    return _openai


def _model_quote(item_name: str) -> float | None:
    """Used street price for the named product. Cached. Skipped with no OpenAI key."""
    name = item_name.strip()
    if not name or not config.env_str("OPENAI_API_KEY"):
        return None
    key = "quote:" + name.lower()
    if key in _cache:
        return _cache[key]
    if len(_cache) >= 1024:
        _cache.clear()
    try:
        resp = _openai_client().chat.completions.create(
            model=config.env_str("OPENAI_PRICE_MODEL", "gpt-4.1-mini"),
            max_tokens=40,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": _QUOTE.format(name=name)}],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        value = round(float(data["value_usd"]), 2)
    except Exception:
        log.warning("model price failed for %s", name, exc_info=True)
        return None
    if value <= 0:
        return None
    _cache[key] = value
    log.info("model price for %s is $%s", name, value)
    return value
