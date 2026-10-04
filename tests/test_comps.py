"""Provider-agnostic comps: ebay scrape parse, provider selection, and the
_lookup ladder. The network is faked — pricing.urlopen is patched."""
from __future__ import annotations

import json
import os
import unittest

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SERPAPI_API_KEY",
            "COMPS_PROVIDER", "SERPAPI_ENABLED"):
    os.environ.pop(var, None)

from rig import pricing

EBAY_HTML = """
<li class="s-item">
  <div class="s-item__title">Sony WH-1000XM6 Wireless Headphones - Black</div>
  <span class="s-item__price">$479.99</span>
</li>
<li class="s-item">
  <div class="s-item__title"><span>Sony WH-1000XM6</span> Headphones Silver</div>
  <span class="s-item__price">$480.00 to $510.00</span>
</li>
<li class="s-item">
  <div class="s-item__title">headphone replacement cable</div>
  <span class="s-item__price">$8.00</span>
</li>
"""


class _Resp:
    def __init__(self, body: str):
        self.body = body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, *a):
        return self.body


class ProviderPick(unittest.TestCase):
    def tearDown(self):
        for var in ("SERPAPI_API_KEY", "COMPS_PROVIDER"):
            os.environ.pop(var, None)

    def test_default_is_ebay_without_a_key(self):
        self.assertEqual(pricing.comps_provider(), "ebay")

    def test_key_flips_default_to_serpapi(self):
        os.environ["SERPAPI_API_KEY"] = "k"
        self.assertEqual(pricing.comps_provider(), "serpapi")

    def test_explicit_overrides_and_off(self):
        os.environ["SERPAPI_API_KEY"] = "k"
        os.environ["COMPS_PROVIDER"] = "ebay"
        self.assertEqual(pricing.comps_provider(), "ebay")
        os.environ["COMPS_PROVIDER"] = "off"
        self.assertEqual(pricing.comps_provider(), "off")

    def test_ebay_creds_pick_ebayapi(self):
        os.environ["EBAY_CLIENT_ID"] = "id"
        os.environ["EBAY_CLIENT_SECRET"] = "secret"
        try:
            self.assertEqual(pricing.comps_provider(), "ebayapi")
        finally:
            os.environ.pop("EBAY_CLIENT_ID", None)
            os.environ.pop("EBAY_CLIENT_SECRET", None)


class EbayApiRows(unittest.TestCase):
    def setUp(self):
        self.saved = pricing.urlopen
        pricing._ebay_tok = None
        os.environ["EBAY_CLIENT_ID"] = "id"
        os.environ["EBAY_CLIENT_SECRET"] = "secret"
        calls = []
        search = _Resp(json.dumps({"itemSummaries": [
            {"title": "Sony WH-1000XM5 Wireless", "price": {"value": "300.00"}},
            {"title": "Sony WH-1000XM5 Headphones Black",
             "price": {"value": "320.00"}},
            {"title": "broken listing"},
        ]}))

        def fake(req, *a, **k):
            calls.append(req.full_url)
            if "oauth2/token" in req.full_url:
                return _Resp(json.dumps({"access_token": "tok", "expires_in": 7200}))
            return _Resp(search.body.decode())

        self.calls = calls
        pricing.urlopen = fake

    def tearDown(self):
        pricing.urlopen = self.saved
        pricing._ebay_tok = None
        for var in ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"):
            os.environ.pop(var, None)

    def test_oauth_then_search_and_row_shape(self):
        rows = pricing._ebayapi_rows("sony wh-1000xm5")
        self.assertIn("oauth2/token", self.calls[0])
        self.assertIn("browse/v1/item_summary/search", self.calls[1])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["price"]["extracted"], 300.0)
        self.assertEqual(pricing.comps("Sony WH-1000XM5", rows), 310.0)

    def test_token_is_cached(self):
        pricing._ebayapi_rows("a")
        pricing._ebayapi_rows("b")   # second call must reuse the token
        self.assertEqual(
            sum("oauth2/token" in c for c in self.calls), 1)


class EbayRows(unittest.TestCase):
    def setUp(self):
        self.saved = pricing.urlopen
        pricing.urlopen = lambda *a, **k: _Resp(EBAY_HTML)
        pricing._cache.clear()

    def tearDown(self):
        pricing.urlopen = self.saved
        pricing._cache.clear()
        os.environ.pop("SERPAPI_ENABLED", None)
        os.environ.pop("COMPS_PROVIDER", None)

    def test_scrape_parses_titles_and_prices(self):
        rows = pricing._ebay_rows("sony wh-1000xm6")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["price"]["extracted"], 479.99)
        self.assertEqual(rows[1]["price"]["extracted"], 480.0)   # range -> low end
        self.assertIn("WH-1000XM6", rows[1]["title"])

    def test_lookup_ebay_end_to_end(self):
        os.environ["SERPAPI_ENABLED"] = "1"   # the comps switch on, provider ebay
        os.environ["COMPS_PROVIDER"] = "ebay"
        pricing._serpapi_enabled = None
        try:
            price, source = pricing._lookup("Sony WH-1000XM6")
            self.assertEqual(price, 480.0)
            self.assertEqual(source, "ebay")
        finally:
            pricing._serpapi_enabled = None

    def test_off_provider_never_fetches(self):
        os.environ["SERPAPI_ENABLED"] = "1"
        os.environ["COMPS_PROVIDER"] = "off"
        pricing._serpapi_enabled = None
        called = []
        pricing.urlopen = lambda *a, **k: called.append(a)
        try:
            self.assertEqual(pricing._lookup("ROLEX"), (None, "off"))
            self.assertFalse(called)
        finally:
            pricing._serpapi_enabled = None


if __name__ == "__main__":
    unittest.main()
