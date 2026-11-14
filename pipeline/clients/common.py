"""What the three API clients share: an httpx client, error types that never hold a key or a request header, and
the response headers worth keeping (PLAN 5.4 and 5.7)."""
from __future__ import annotations

import email.utils
import json
import time

import httpx

from pipeline import config

TRANSPORT = None   # None for the network; the tests set an httpx.MockTransport
KEEP_HEADERS = ("x-inference-provider", "x-request-id", "x-generation-id", "retry-after", "date")
RETRYABLE = (429, 503)   # the only statuses a sync request is sent again for (PLAN 5.3)


class ClientError(RuntimeError):
    """A failed request: a message, its kind (http, timeout, transport, decode or setup), the HTTP status, the
    start of the reply body, whether sending it again may help, and the wait the server asked for."""

    def __init__(self, message, kind="http", status=None, body=None, retryable=False, retry_after=None):
        super().__init__(message)
        self.message = str(message)
        self.kind = kind
        self.status = status
        self.body = None if body is None else str(body)[:2000]
        self.retryable = retryable
        self.retry_after = retry_after

    def to_dict(self) -> dict:
        return {"type": self.kind, "status": self.status, "message": self.message[:500], "body": self.body,
                "retryable": self.retryable}


class SubmitUncertain(ClientError):
    """A batch submit whose outcome is unknown: the batch may exist and be billed. Its requests stay in flight
    until run.py adopt ties the submit to a batch that run.py batches lists, or run.py release gives it up."""


def http_client(timeout: float = 60.0, ipv4: bool = False) -> httpx.Client:
    """An httpx client. With ipv4 the client connects over IPv4 only. On 11 November 2026 the network of the
    pilot gave NAT64 IPv6 addresses for router.huggingface.co ahead of the IPv4 addresses, the TLS handshake over
    those IPv6 addresses timed out, and every Hugging Face request failed before reaching the router. A test
    transport is used whenever one is set."""
    transport = TRANSPORT
    if transport is None and ipv4:
        transport = httpx.HTTPTransport(local_address="0.0.0.0")
    return httpx.Client(transport=transport, timeout=timeout)


def kept_headers(headers) -> dict:
    if not headers:
        return {}
    return {k: headers[k] for k in KEEP_HEADERS if k in headers}


def retry_after_seconds(headers):
    """The Retry-After header in seconds (a number or an HTTP date), or None."""
    value = (headers or {}).get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time())


def request(method, url, headers=None, json_body=None, timeout=60.0, params=None, client=None, ipv4=False):
    """One HTTP request. A body goes as UTF-8 JSON with its key order kept. Raises ClientError on a timeout, a
    transport failure or a status of 400 or more; the error names the exception type and the URL, never a
    header. ipv4 applies only when no client is given (see http_client)."""
    h = {"User-Agent": config.USER_AGENT, **(headers or {})}
    content = None
    if json_body is not None:
        h["Content-Type"] = "application/json"
        content = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    own = client is None
    c = http_client(timeout, ipv4) if own else client
    try:
        resp = c.request(method, url, headers=h, content=content, params=params, timeout=timeout)
    except httpx.TimeoutException as e:
        raise ClientError(f"{type(e).__name__} on {method} {url}", kind="timeout") from None
    except httpx.RequestError as e:
        raise ClientError(f"{type(e).__name__} on {method} {url}", kind="transport") from None
    finally:
        if own:
            c.close()
    if resp.status_code >= 400:
        raise ClientError(f"HTTP {resp.status_code} on {method} {url}", kind="http", status=resp.status_code,
                          body=resp.text, retryable=resp.status_code in RETRYABLE,
                          retry_after=retry_after_seconds(resp.headers))
    return resp


def json_of(resp):
    try:
        return resp.json()
    except ValueError:
        raise ClientError(f"the reply is not JSON (HTTP {resp.status_code})", kind="decode",
                          status=resp.status_code, body=resp.text) from None


def text_of(content):
    """The text of a chat-completion message: a string, or the text parts of a list of parts joined."""
    if content is None or isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p.get("text") or "" for p in content
                 if isinstance(p, dict) and p.get("type") in ("text", "output_text")]
        return "".join(parts) if parts else None
    return str(content)


def body_error(data, status):
    """A ClientError for a 200 reply that holds an error object and no choices, else None."""
    if not isinstance(data, dict) or not data.get("error") or data.get("choices"):
        return None
    err = data["error"] if isinstance(data["error"], dict) else {"message": str(data["error"])}
    code = err.get("code") if isinstance(err.get("code"), int) else status
    return ClientError(f"error in the reply: {err.get('message')}", kind="http", status=code,
                       body=json.dumps(data, ensure_ascii=False), retryable=code in RETRYABLE)
