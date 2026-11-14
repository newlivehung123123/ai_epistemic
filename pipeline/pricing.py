"""Prices in US$ per million tokens for each setting and route (PLAN 5.4).

A send saves one price record per setting and route: the provider's public listing on the request date where one
exists (OpenRouter, Hugging Face), with the stated precision, and the cost model of design/cost_model.py beside it.
Anthropic publishes no listing to fetch, so its record holds the cost model, whose Anthropic prices come from
design/notes/anthropic_models_and_prices.md. A stub run or a dry run never touches the network and uses the cost
model. A listing that cannot be read leaves the cost model in place with a warning."""
from __future__ import annotations

import functools
import importlib.util
import json
import sys

from pipeline import config, keys, settings
from pipeline.clients import hf_client, openrouter_client
from pipeline.clients.common import ClientError
from pipeline.util import now_utc


@functools.lru_cache(maxsize=1)
def cost_model():
    path = config.DESIGN / "cost_model.py"
    spec = importlib.util.spec_from_file_location("cost_model", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def provider_requested(name: str, route: str) -> str | None:
    st = settings.setting(name)
    if st["api"] == "anthropic":
        return "anthropic"
    if st["api"] == "hf":
        return hf_client.provider_requested(st)
    return st.get("batch_provider") if route == "batch" else st.get("sync_provider")


def model_price(name: str, route: str) -> tuple[float, float]:
    """The cost-model price of a setting on a route: Hugging Face prices for HF, sync prices for an OpenRouter
    sync request, batch or base prices otherwise."""
    cm = cost_model()
    model = settings.COST_MODEL_NAME[name][0]
    api = settings.setting(name)["api"]
    if api == "hf":
        return tuple(cm.price(model, hf=True))
    if api == "openrouter" and route == "sync":
        return tuple(cm.price(model, sync=True))
    return tuple(cm.price(model))


def expected_out(name: str, kind: str) -> int:
    """Output tokens the cost model expects for one request, thinking included, at most the setting's cap."""
    cm = cost_model()
    model, think = settings.COST_MODEL_NAME[name]
    base = {"t1": cm.T1_OUT, "t2": cm.T2_OUT, "t2_nf": cm.T2_OUT, "probe": cm.PROBE_OUT}[kind]
    return min(base + cm.reasoning(model, think), settings.setting(name)["max_tokens"])


def _num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return -1.0


def pick_endpoint(endpoints, slug: str):
    """The listing row of a provider: the row whose tag is the slug, else a row whose tag starts with slug + "/".
    Several prefix matches give the dearest row and a note. Returns (row or None, note or None)."""
    rows = [e for e in endpoints or [] if isinstance(e, dict)]
    exact = [e for e in rows if e.get("tag") == slug]
    if exact:
        return exact[0], None
    pre = [e for e in rows if str(e.get("tag") or "").startswith(slug + "/")]
    if not pre:
        return None, f"no endpoint in the listing has the tag {slug}"
    if len(pre) == 1:
        return pre[0], f"tag {pre[0].get('tag')} matched by prefix"
    best = max(pre, key=lambda e: (_num((e.get("pricing") or {}).get("completion")),
                                   _num((e.get("pricing") or {}).get("prompt"))))
    tags = ", ".join(sorted(str(e.get("tag")) for e in pre))
    return best, f"ambiguous: tags {tags} all match {slug}; the dearest ({best.get('tag')}) is used"


def _per_million(x) -> float:
    return round(float(x) * 1e6, 6)


def _from_openrouter(rec: dict, st: dict, route: str) -> None:
    url, data = openrouter_client.listing(st["model"], batch=route == "batch")
    rec["listing_url"], rec["listing"] = url, data
    eps = ((data or {}).get("data") or {}).get("endpoints") or []
    ep, note = pick_endpoint(eps, rec["provider"])
    if ep is None:
        raise LookupError(note)
    pricing = ep.get("pricing") or {}
    rec.update(source="listing", price_in=_per_million(pricing["prompt"]),
               price_out=_per_million(pricing["completion"]), quantization=ep.get("quantization"),
               status=ep.get("status"), endpoint_tag=ep.get("tag"), note=note)


def _from_hf(rec: dict, st: dict) -> None:
    try:
        token = keys.key("hf")
    except keys.MissingKey:
        token = None
    url, data = hf_client.listing(token)
    model_id, _, slug = st["model"].partition(":")
    row = next((m for m in (data or {}).get("data") or [] if isinstance(m, dict) and m.get("id") == model_id),
               None)
    rec["listing_url"], rec["listing"] = url, row
    if row is None:
        raise LookupError(f"the router lists no model {model_id}")
    prov = next((p for p in row.get("providers") or [] if isinstance(p, dict) and p.get("provider") == slug),
                None)
    if prov is None or not prov.get("pricing"):
        raise LookupError(f"the router lists no price for {model_id} on {slug}")
    rec.update(source="listing", price_in=float(prov["pricing"]["input"]), price_out=float(prov["pricing"]["output"]),
               status=prov.get("status"), endpoint_tag=slug,
               note="the Hugging Face router states no precision; the provider's model page is checked by hand")


def price_record(name: str, route: str, offline: bool = False) -> dict:
    """The price record of one setting on one route, saved with each send."""
    st = settings.setting(name)
    cm_in, cm_out = model_price(name, route)
    rec = {"setting": name, "api": st["api"], "route": route, "model": st["model"], "fetched_at": now_utc(),
           "source": "cost_model", "provider": provider_requested(name, route), "price_in": cm_in,
           "price_out": cm_out, "quantization": None, "status": None, "listing_url": None, "listing": None,
           "endpoint_tag": None, "note": None, "cost_model_in": cm_in, "cost_model_out": cm_out}
    if st["api"] == "anthropic":
        rec["note"] = "Anthropic batch prices of design/notes/anthropic_models_and_prices.md (the cost model)"
        return rec
    if offline:
        rec["note"] = "offline (stub or dry run): the cost model"
        return rec
    try:
        if st["api"] == "openrouter":
            _from_openrouter(rec, st, route)
        else:
            _from_hf(rec, st)
    except (ClientError, LookupError, KeyError, TypeError, ValueError, AttributeError) as e:
        rec.update(source="cost_model", price_in=cm_in, price_out=cm_out,
                   note=f"listing not read ({type(e).__name__}: {str(e)[:200]}); the cost model is used")
        print(f"warning: {name} {route}: {rec['note']}", file=sys.stderr)
        return rec
    if rec["price_in"] > cm_in * 1.0001 or rec["price_out"] > cm_out * 1.0001:
        extra = (f"the listing price {rec['price_in']}/{rec['price_out']} exceeds the cost model "
                 f"{cm_in}/{cm_out}")
        rec["note"] = f"{rec['note']}; {extra}" if rec["note"] else extra
        print(f"warning: {name} {route}: {extra}", file=sys.stderr)
    return rec


def describe(rec: dict) -> str:
    return json.dumps({k: rec[k] for k in ("setting", "route", "provider", "source", "price_in", "price_out",
                                           "quantization", "endpoint_tag", "note")}, ensure_ascii=False)
