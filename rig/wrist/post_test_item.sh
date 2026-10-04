#!/usr/bin/env bash
# Post a labeled test exhibit to the backend so the wrist's live-parity
# check has something to show. Anyone with RIG_TOKEN can run it:
#
#   HUB_URL=https://heist-production-75b7.up.railway.app \
#   RIG_TOKEN=<token> bash rig/wrist/post_test_item.sh
#
# Expected: {"added": true, "hot": true, ...} and the wrist's top-5
# picks up TEST ITEM on its next long-poll (tens of ms).
set -euo pipefail

HUB_URL="${HUB_URL:-https://heist-production-75b7.up.railway.app}"
: "${RIG_TOKEN:?set RIG_TOKEN (Railway env, or ~/rowdy/hub.env on the wrist)}"

curl -fsS -m 15 -X POST "$HUB_URL/api/exhibit" \
  -H 'Content-Type: application/json' \
  -H "X-Rig-Token: $RIG_TOKEN" \
  -d '{"item":"TEST ITEM","desc":"wrist integration check","category":"prop","value_usd":25,"estimated":true,"why":"manual wrist test"}'
echo
curl -fsS -m 15 -H "X-Rig-Token: $RIG_TOKEN" "$HUB_URL/wrist.json?peek"
echo
