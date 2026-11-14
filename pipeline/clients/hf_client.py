"""Hugging Face Inference Providers through the router's chat-completions API (PLAN 5.4).

The provider is fixed by the suffix of the model ID (openai/gpt-oss-120b:deepinfra), and the router names the
provider that served each reply in the x-inference-provider header. The token goes only in the Authorization header
and is never printed or written to a log. Every request to the router goes over IPv4 only, after the failure of
11 November 2026 described in common.http_client."""
from __future__ import annotations

from pipeline import keys
from pipeline.clients import common, openrouter_client
from pipeline.clients.common import ClientError

API = "hf"
URL = "https://router.huggingface.co/v1/chat/completions"
MODELS_URL = "https://router.huggingface.co/v1/models"
TIMEOUT = 300.0


def provider_requested(st: dict) -> str | None:
    model = st["model"]
    return model.rsplit(":", 1)[1] if ":" in model else None


def sync_body(rec: dict, st: dict) -> dict:
    body = {"model": st["model"], "messages": [{"role": "system", "content": rec["system"]}, *rec["messages"]],
            "max_tokens": rec["max_tokens"]}
    if st.get("reasoning_effort") is not None:
        body["reasoning_effort"] = st["reasoning_effort"]
    return body


def extract(body: dict, headers=None) -> dict:
    """As for OpenRouter (the reply is a chat completion), with the serving provider from the router's header."""
    out = openrouter_client.extract(body)
    served = (headers or {}).get("x-inference-provider")
    if served:
        out["serving_provider"], out["serving_provider_source"] = served, "header"
    return out


class HFClient:
    api = API

    def __init__(self):
        self._token = keys.key("hf")
        self._http = common.http_client(TIMEOUT, ipv4=True)

    def send_sync(self, body: dict, cid: str | None = None):
        """One chat completion: (reply JSON, kept response headers)."""
        resp = common.request("POST", URL, headers={"Authorization": f"Bearer {self._token}"}, json_body=body,
                              timeout=TIMEOUT, client=self._http)
        data = common.json_of(resp)
        err = common.body_error(data, resp.status_code)
        if err is not None:
            raise err
        return data, common.kept_headers(resp.headers)


def listing(token: str | None = None) -> tuple[str, dict]:
    """The router's model list with each provider's price per million tokens. Sent without the token, and again
    with it only if the router answers 401."""
    try:
        resp = common.request("GET", MODELS_URL, timeout=60.0, ipv4=True)
    except ClientError as e:
        if e.status != 401 or not token:
            raise
        resp = common.request("GET", MODELS_URL, headers={"Authorization": f"Bearer {token}"}, timeout=60.0,
                              ipv4=True)
    return MODELS_URL, common.json_of(resp)
