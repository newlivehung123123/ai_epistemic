"""OpenRouter through httpx (PLAN 5.3 and 5.4).

A sync request names one provider and allows no fallback. A batch names one provider for all its requests. The key
goes only in the Authorization header. The batch API is new, so its replies are read defensively: the batch object
may come wrapped in "data", and a completed batch may show results null for a while."""
from __future__ import annotations

import json

from pipeline import keys
from pipeline.clients import common
from pipeline.clients.common import ClientError, SubmitUncertain

API = "openrouter"
BASE = "https://openrouter.ai/api/v1"
TIMEOUT = 300.0
BATCH_TERMINAL = ("completed", "failed", "expired", "cancelled")
FINAL_STATUSES = (402, 404, 410)   # a batch these answer cannot be fetched again


def _messages(rec: dict) -> list[dict]:
    return [{"role": "system", "content": rec["system"]}, *rec["messages"]]


def sync_body(rec: dict, st: dict) -> dict:
    body = {"model": st["model"], "messages": _messages(rec), "max_tokens": rec["max_tokens"]}
    if st.get("reasoning") is not None:
        body["reasoning"] = st["reasoning"]
    body["provider"] = {"only": [st["sync_provider"]], "sort": "price", "allow_fallbacks": False,
                        "require_parameters": True}
    return body


def batch_payload(recs: list[dict], st: dict) -> dict:
    """One batch body. requests must be the last key (an earlier one gives HTTP 400) and the batch API rejects
    sort, so the provider object holds only the provider and the fallback rule."""
    if not st.get("batch_provider"):
        raise ValueError(f"no OpenRouter batch provider serves {st['model']}")

    def one(r):
        body = {"messages": _messages(r), "max_tokens": r["max_tokens"]}
        if st.get("reasoning") is not None:
            body["reasoning"] = st["reasoning"]
        return {"custom_id": r["custom_id"], "body": body}

    return {"endpoint": "/v1/chat/completions", "model": st["model"],
            "provider": {"only": [st["batch_provider"]], "allow_fallbacks": False},
            "completion_window": "24h", "requests": [one(r) for r in recs]}


def _unwrap(data):
    if isinstance(data, dict) and "id" not in data and isinstance(data.get("data"), dict):
        return data["data"]
    return data


class OpenRouterClient:
    api = API

    def __init__(self):
        self._key = keys.key("openrouter")
        self._http = common.http_client(TIMEOUT)

    def _request(self, method, path, body=None, params=None):
        headers = {"Authorization": f"Bearer {self._key}", "X-OpenRouter-Metadata": "enabled"}
        return common.request(method, f"{BASE}{path}", headers=headers, json_body=body, timeout=TIMEOUT,
                              params=params, client=self._http)

    def send_sync(self, body: dict, cid: str | None = None):
        """One chat completion: (reply JSON, kept response headers)."""
        resp = self._request("POST", "/chat/completions", body)
        data = common.json_of(resp)
        err = common.body_error(data, resp.status_code)
        if err is not None:
            raise err
        return data, common.kept_headers(resp.headers)

    def submit(self, payload: dict) -> dict:
        """Create one batch. A 4xx refusal means no batch was made; a timeout, a lost connection, a 5xx or a reply
        without a batch ID leaves the outcome unknown and raises SubmitUncertain."""
        try:
            resp = self._request("POST", "/batches", payload)
        except ClientError as e:
            if e.kind in ("timeout", "transport") or e.status is None or e.status >= 500 or e.status == 408:
                raise SubmitUncertain(e.message, kind=e.kind, status=e.status, body=e.body) from None
            raise
        try:
            data = _unwrap(common.json_of(resp))
        except ClientError as e:
            raise SubmitUncertain(e.message, kind="decode", status=e.status, body=e.body) from None
        if not isinstance(data, dict) or not data.get("id"):
            raise SubmitUncertain("the batch reply holds no batch ID", kind="decode", status=resp.status_code,
                                  body=json.dumps(data, ensure_ascii=False))
        return data

    def retrieve(self, batch_id: str) -> dict:
        return _unwrap(common.json_of(self._request("GET", f"/batches/{batch_id}")))

    def list_batches(self, limit: int = 20) -> list[dict]:
        data = common.json_of(self._request("GET", "/batches", params={"limit": limit}))
        return data.get("data", []) if isinstance(data, dict) else list(data or [])


def provider_name(x):
    if isinstance(x, dict):
        return x.get("name") or x.get("slug") or x.get("tag")
    return x or None


def extract(body: dict, headers=None, batch_provider=None) -> dict:
    """The fields a result record keeps from one chat completion. The serving provider comes from the reply, else
    from the router metadata, else (in a batch) from the provider the batch names."""
    body = body or {}
    choice = (body.get("choices") or [{}])[0] or {}
    message = choice.get("message") or {}
    usage = body.get("usage") or None
    u = usage or {}
    details = u.get("completion_tokens_details") or {}
    meta = body.get("openrouter_metadata") or {}
    endpoints = meta.get("endpoints")
    available = endpoints.get("available", []) if isinstance(endpoints, dict) else (endpoints or [])
    selected = [provider_name(e.get("provider")) for e in available if isinstance(e, dict) and e.get("selected")]
    if body.get("provider"):
        provider, source = provider_name(body["provider"]), "reply"
    elif selected:
        provider, source = selected[0], "metadata"
    elif batch_provider:
        provider, source = provider_name(batch_provider), "batch"
    else:
        provider, source = None, None
    thinking = message.get("reasoning") or message.get("reasoning_content")
    if thinking is not None and not isinstance(thinking, str):
        thinking = json.dumps(thinking, ensure_ascii=False)
    details_list = message.get("reasoning_details") or None
    n_think = len(details_list) if isinstance(details_list, list) and details_list else (1 if thinking else 0)
    return {"text": common.text_of(message.get("content")), "thinking_text": thinking or None,
            "reasoning_details": details_list, "thinking_blocks": n_think,
            "other_blocks": [k for k in ("tool_calls", "function_call", "refusal", "audio", "images")
                             if message.get(k)],
            "model_returned": body.get("model"), "stop_reason": choice.get("finish_reason"),
            "native_stop_reason": choice.get("native_finish_reason"),
            "input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens"),
            "reasoning_tokens": details.get("reasoning_tokens"), "usage": usage, "reported_cost": u.get("cost"),
            "serving_provider": provider, "serving_provider_source": source,
            "router_attempt": meta.get("attempt"), "generation_id": body.get("id")}


def _err(kind, status, message, body, retryable) -> dict:
    return {"type": kind, "status": status, "message": str(message)[:500],
            "body": None if body is None else json.dumps(body, ensure_ascii=False, default=str)[:2000],
            "retryable": retryable}


def batch_entries(batch: dict, ids) -> tuple[dict, bool]:
    """Each requested custom_id with {"ok": True, "body"} or {"ok": False, "error"}, once the batch can say.
    Returns (entries, ready); ready is False while the batch runs or while a completed batch shows results null."""
    status = batch.get("status")
    results = batch.get("results")
    if status not in BATCH_TERMINAL or (status == "completed" and results is None):
        return {}, False
    entries = {}
    if results is None:
        err = batch.get("error")
        detail = err.get("message") if isinstance(err, dict) else err
        for cid in ids:
            entries[cid] = {"ok": False, "error": _err(f"batch_{status}", None, f"batch {status}"
                                                       + (f" ({detail})" if detail else ""), err, True)}
        return entries, True
    wanted = set(ids)
    for e in results:
        cid = e.get("custom_id") if isinstance(e, dict) else None
        if cid not in wanted or cid in entries:
            continue
        resp = e.get("response") or {}
        body = resp.get("body")
        code = resp.get("status_code")
        if e.get("error") or not resp:
            err = e.get("error") or {}
            entries[cid] = {"ok": False, "error": _err(err.get("type") or "batch_error", code,
                                                       f"batch entry error ({err.get('message')})", err, True)}
        elif code != 200 or body is None:
            detail = ((body or {}).get("error") or {}).get("message") if isinstance(body, dict) else None
            entries[cid] = {"ok": False, "error": _err("http", code, f"HTTP {code} in the batch"
                                                       + (f" ({detail})" if detail else ""), body,
                                                       code in (429, 500, 502, 503))}
        else:
            be = common.body_error(body, code)
            entries[cid] = ({"ok": False, "error": be.to_dict()} if be is not None
                            else {"ok": True, "body": body, "request_id": resp.get("request_id")})
    for cid in ids:
        if cid not in entries:
            entries[cid] = {"ok": False, "error": _err("missing", None, "missing from the batch results", None,
                                                       True)}
    return entries, True


def listing(model: str, batch: bool = False) -> tuple[str, dict]:
    """The public endpoint listing of a model (no key); the :batch listing for the batch route."""
    url = f"{BASE}/models/{model}{':batch' if batch else ''}/endpoints"
    return url, common.json_of(common.request("GET", url, timeout=60.0))
