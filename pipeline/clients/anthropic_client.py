"""Anthropic Message Batches through the official SDK (PLAN 5.2 and 5.7).

Every Anthropic request goes in a batch, with no temperature, no prefill and no prompt caching. The settings that
leave thinking out (Haiku 5.5 medium, Sonnet 5.5 high) send no thinking field. Thinking text is stored with the
record and is never parsed or replayed. The SDK version is fixed by settings.ANTHROPIC_SDK, and a client refuses to
start under another version."""
from __future__ import annotations

import json

from pipeline import keys, settings
from pipeline.clients import common
from pipeline.clients.common import ClientError, SubmitUncertain

API = "anthropic"
THINKING_TYPES = ("thinking", "redacted_thinking")
RETRYABLE_ERRORS = ("api_error", "overloaded_error", "rate_limit_error", "timeout_error")


def params(rec: dict, st: dict) -> dict:
    """The Messages API parameters of one request."""
    p = {"model": st["model"], "max_tokens": rec["max_tokens"], "system": rec["system"],
         "messages": rec["messages"]}
    if st.get("thinking") is not None:
        p["thinking"] = st["thinking"]
    return p


def batch_payload(recs: list[dict], st: dict) -> list[dict]:
    """The requests list of one Message Batch."""
    return [{"custom_id": r["custom_id"], "params": params(r, st)} for r in recs]


def extract(msg: dict) -> dict:
    """The fields a result record keeps from one Message (a plain dict). Anthropic counts thinking inside
    output_tokens and gives no separate reasoning count."""
    blocks = [b for b in (msg.get("content") or []) if isinstance(b, dict)]
    texts = [b.get("text") or "" for b in blocks if b.get("type") == "text"]
    thoughts = [b.get("thinking") or "" for b in blocks if b.get("type") == "thinking"]
    usage = msg.get("usage") or None
    u = usage or {}
    return {"text": "".join(texts) if texts else None,
            "thinking_text": "\n\n".join(thoughts) if thoughts else None,
            "thinking_blocks": sum(b.get("type") in THINKING_TYPES for b in blocks),
            "other_blocks": [b.get("type") for b in blocks if b.get("type") not in ("text", *THINKING_TYPES)],
            "model_returned": msg.get("model"), "stop_reason": msg.get("stop_reason"),
            "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
            "reasoning_tokens": None, "usage": usage, "reported_cost": None,
            "serving_provider": None, "serving_provider_source": None, "generation_id": msg.get("id")}


def result_entry(entry: dict) -> dict:
    """One line of a batch's results as {custom_id, ok: True, reply} or {custom_id, ok: False, error}."""
    cid = entry.get("custom_id")
    res = entry.get("result") or {}
    kind = res.get("type") or "unknown"
    if kind == "succeeded":
        return {"custom_id": cid, "ok": True, "reply": extract(res.get("message") or {})}
    err = res.get("error") or {}
    inner = err.get("error") if isinstance(err.get("error"), dict) else err
    detail = inner.get("message") if isinstance(inner, dict) else None
    inner_type = inner.get("type") if isinstance(inner, dict) else None
    message = f"batch result {kind}" + (f" ({inner_type}) {detail}" if detail else "")
    return {"custom_id": cid, "ok": False,
            "error": {"type": kind, "status": None, "message": message[:500],
                      "body": json.dumps(err, ensure_ascii=False)[:2000] if err else None,
                      "retryable": kind in ("canceled", "expired") or inner_type in RETRYABLE_ERRORS}}


class AnthropicClient:
    """Message Batches with the key from keys.py. The SDK never retries create or cancel, so a create that times
    out cannot make a second batch; retrieve, results and list are retried up to three times."""
    api = API

    def __init__(self):
        try:
            import anthropic
        except ImportError:
            raise ClientError("the anthropic package is not installed", kind="setup") from None
        if anthropic.__version__ != settings.ANTHROPIC_SDK:
            raise ClientError(f"anthropic {anthropic.__version__} is installed and the plan fixes "
                              f"{settings.ANTHROPIC_SDK}; install that version first", kind="setup")
        self._sdk = anthropic
        self._c = anthropic.Anthropic(api_key=keys.key("anthropic"), max_retries=0)
        self._r = self._c.with_options(max_retries=3)

    def _error(self, e, what: str) -> ClientError:
        a = self._sdk
        if isinstance(e, a.APIStatusError):
            body = None if e.body is None else json.dumps(e.body, ensure_ascii=False, default=str)
            headers = getattr(getattr(e, "response", None), "headers", None)
            return ClientError(f"HTTP {e.status_code} on {what}", kind="http", status=e.status_code, body=body,
                               retryable=e.status_code in common.RETRYABLE,
                               retry_after=common.retry_after_seconds(headers))
        if isinstance(e, a.APITimeoutError):
            return ClientError(f"timeout on {what}", kind="timeout")
        if isinstance(e, a.APIConnectionError):
            return ClientError(f"connection failed on {what}", kind="transport")
        return ClientError(f"{type(e).__name__} on {what}: {e}", kind="other")

    def _call(self, what, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except self._sdk.AnthropicError as e:
            raise self._error(e, what) from None

    def submit(self, requests: list[dict]) -> dict:
        """Create one batch. A refusal (4xx) means no batch was made; a timeout, a lost connection or a 5xx
        leaves the outcome unknown and raises SubmitUncertain."""
        a = self._sdk
        try:
            batch = self._c.messages.batches.create(requests=requests)
        except a.AnthropicError as e:
            err = self._error(e, "batch create")
            unknown = isinstance(e, a.APIConnectionError) or (
                isinstance(e, a.APIStatusError) and (e.status_code >= 500 or e.status_code == 408))
            if unknown:
                raise SubmitUncertain(err.message, kind=err.kind, status=err.status, body=err.body) from None
            raise err from None
        return batch.to_dict(mode="json")

    def retrieve(self, batch_id: str) -> dict:
        return self._call("batch retrieve", self._r.messages.batches.retrieve, batch_id).to_dict(mode="json")

    def results(self, batch_id: str) -> list[dict]:
        def fetch():
            return [r.to_dict(mode="json") for r in self._r.messages.batches.results(batch_id)]
        return self._call("batch results", fetch)

    def cancel(self, batch_id: str) -> dict:
        return self._call("batch cancel", self._c.messages.batches.cancel, batch_id).to_dict(mode="json")

    def list_batches(self, limit: int = 20) -> list[dict]:
        page = self._call("batch list", self._r.messages.batches.list, limit=limit)
        return [b.to_dict(mode="json") for b in page.data]

    def api_version(self) -> str | None:
        return self._c.default_headers.get("anthropic-version")

    def sdk_version(self) -> str:
        return self._sdk.__version__
