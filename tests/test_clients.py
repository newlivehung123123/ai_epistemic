"""The three API clients and the price records without the network (PLAN 5.2 to 5.4 and 5.7): request bodies and
headers, the key kept out of every error, the mapping of failures, the reading of batch results and replies, the
.env reader, and the price of each setting read from the listings saved on 6 and 7 November 2026. Every HTTP request
goes to an httpx.MockTransport, and no real key is read."""
import json
import urllib.parse

import httpx
import pytest

from pipeline import build, config, keys, pricing, settings
from pipeline.clients import anthropic_client, common, hf_client, openrouter_client
from pipeline.clients.common import ClientError, SubmitUncertain
from test_build import PILOT

FAKE = "sk-test-not-a-real-key-123"
RAW = config.DESIGN / "notes" / "raw_sources"


def clear_env(monkeypatch, *names):
    """Remove variables for one test. setenv comes first, so teardown also removes a value set during the test."""
    for name in names:
        monkeypatch.setenv(name, "x")
        monkeypatch.delenv(name)


@pytest.fixture
def no_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(keys, "ENV_FILE", tmp_path / "no.env")
    clear_env(monkeypatch, *keys.KEY_NAMES.values())
    return tmp_path


def transport(monkeypatch, handler):
    """Send every request of this test to handler. Set before a client is made: a client keeps its transport."""
    monkeypatch.setattr(common, "TRANSPORT", httpx.MockTransport(handler))


def rec_of(name, run="pilot"):
    return build.round1(run, name, PILOT)[0]


def completion(**extra):
    body = {"id": "gen-1", "model": "x/y", "choices": [{"message": {"role": "assistant", "content": "{}"},
                                                        "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    body.update(extra)
    return body


# ------------------------------------------------------------------------------------------------ Anthropic

@pytest.mark.parametrize("name,has_thinking", [("haiku_off", True), ("sonnet_off", True),
                                               ("haiku_medium", False), ("sonnet_high", False)])
def test_anthropic_params_send_thinking_only_where_the_setting_names_it(name, has_thinking):
    st = settings.setting(name)
    p = anthropic_client.params(rec_of(name), st)
    assert list(p)[:4] == ["model", "max_tokens", "system", "messages"]
    assert ("thinking" in p) is has_thinking
    if has_thinking:
        assert p["thinking"] == st["thinking"]
    assert "temperature" not in p
    batch = anthropic_client.batch_payload([rec_of(name)], st)
    assert list(batch[0]) == ["custom_id", "params"]


def test_anthropic_extract_counts_thinking_blocks_and_never_mixes_them_into_the_text():
    msg = {"id": "msg_1", "model": "claude-haiku-5-5", "stop_reason": "end_turn",
           "content": [{"type": "thinking", "thinking": "first"}, {"type": "redacted_thinking", "data": "x"},
                       {"type": "text", "text": '{"probability": 40'}, {"type": "text", "text": "}"},
                       {"type": "tool_use", "id": "t"}],
           "usage": {"input_tokens": 12, "output_tokens": 30}}
    out = anthropic_client.extract(msg)
    assert out["text"] == '{"probability": 40}'
    assert out["thinking_text"] == "first"
    assert out["thinking_blocks"] == 2
    assert out["other_blocks"] == ["tool_use"]
    assert (out["input_tokens"], out["output_tokens"], out["reasoning_tokens"]) == (12, 30, None)


@pytest.mark.parametrize("result,retryable", [
    ({"type": "canceled"}, True),
    ({"type": "expired"}, True),
    ({"type": "errored", "error": {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}}, True),
    ({"type": "errored", "error": {"type": "error", "error": {"type": "invalid_request_error", "message": "no"}}},
     False),
])
def test_anthropic_result_entries_that_are_not_replies(result, retryable):
    out = anthropic_client.result_entry({"custom_id": "a", "result": result})
    assert out["ok"] is False and out["custom_id"] == "a"
    assert out["error"]["type"] == result["type"] and out["error"]["retryable"] is retryable


def test_anthropic_client_refuses_another_sdk_version_and_a_missing_key(no_keys, monkeypatch):
    import anthropic
    monkeypatch.setattr(anthropic, "__version__", "0.0.1")
    with pytest.raises(ClientError) as e:
        anthropic_client.AnthropicClient()
    assert e.value.kind == "setup" and settings.ANTHROPIC_SDK in e.value.message
    monkeypatch.setattr(anthropic, "__version__", settings.ANTHROPIC_SDK)
    with pytest.raises(keys.MissingKey):
        anthropic_client.AnthropicClient()


# ----------------------------------------------------------------------------------------------- OpenRouter

def test_openrouter_sync_request_body_and_headers(no_keys, monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=completion(provider="Mistral"), headers={"x-request-id": "r-1"})

    transport(monkeypatch, handler)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE)
    st = settings.setting("mistral_small")
    body = openrouter_client.sync_body(rec_of("mistral_small"), st)
    assert list(body) == ["model", "messages", "max_tokens", "reasoning", "provider"]
    assert body["provider"] == {"only": ["mistral/zdr"], "sort": "price", "allow_fallbacks": False,
                                "require_parameters": True}
    data, headers = openrouter_client.OpenRouterClient().send_sync(body)
    req = seen[0]
    assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {FAKE}"
    assert req.headers["x-openrouter-metadata"] == "enabled"
    assert req.headers["user-agent"] == config.USER_AGENT == "research-client/0.1"
    assert req.headers["content-type"] == "application/json"
    sent = json.loads(req.content)
    assert sent == body and list(sent) == list(body)
    assert headers == {"x-request-id": "r-1"}
    assert openrouter_client.extract(data)["serving_provider"] == "Mistral"


def test_the_key_never_appears_in_an_error(no_keys, monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(400, json={"error": {"message": "bad request"}}))
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE)
    client = openrouter_client.OpenRouterClient()
    with pytest.raises(ClientError) as e:
        client.send_sync(openrouter_client.sync_body(rec_of("mistral_small"), settings.setting("mistral_small")))
    assert e.value.status == 400 and not e.value.retryable
    for text in (str(e.value), e.value.body, json.dumps(e.value.to_dict())):
        assert FAKE not in text


def test_a_reply_that_holds_only_an_error_is_an_error(no_keys, monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(200, json={"error": {"message": "busy", "code": 503}}))
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE)
    with pytest.raises(ClientError) as e:
        openrouter_client.OpenRouterClient().send_sync({"model": "m"})
    assert e.value.status == 503 and e.value.retryable and "busy" in e.value.message


def test_openrouter_batch_payload():
    st = settings.setting("deepseek_flash")
    recs = build.round1("pilot_batch_test", "deepseek_flash", PILOT)
    payload = openrouter_client.batch_payload(recs, st)
    assert list(payload) == ["endpoint", "model", "provider", "completion_window", "requests"]
    assert payload["endpoint"] == "/v1/chat/completions" and payload["completion_window"] == "24h"
    assert payload["provider"] == {"only": ["deepinfra"], "allow_fallbacks": False}
    assert len(payload["requests"]) == 10
    one = payload["requests"][0]
    assert list(one) == ["custom_id", "body"] and one["custom_id"] == recs[0]["custom_id"]
    assert list(one["body"]) == ["messages", "max_tokens", "reasoning"]
    assert one["body"]["messages"][0] == {"role": "system", "content": recs[0]["system"]}
    assert one["body"]["reasoning"] == st["reasoning"]
    with pytest.raises(ValueError, match="no OpenRouter batch provider serves google/gemini-3.1-flash-lite"):
        openrouter_client.batch_payload([], settings.setting("gemini_flash_lite"))


def test_openrouter_extract_names_where_the_serving_provider_came_from():
    def source(body, batch_provider=None):
        out = openrouter_client.extract(body, batch_provider=batch_provider)
        return out["serving_provider"], out["serving_provider_source"]

    assert source(completion(provider="DeepInfra")) == ("DeepInfra", "reply")
    meta = {"endpoints": {"available": [{"provider": {"name": "Other"}}, {"provider": {"name": "Chosen"},
                                                                           "selected": True}]}}
    assert source(completion(openrouter_metadata=meta)) == ("Chosen", "metadata")
    meta_list = {"endpoints": [{"provider": "Listed", "selected": True}]}
    assert source(completion(openrouter_metadata=meta_list)) == ("Listed", "metadata")
    assert source(completion(), batch_provider="openai") == ("openai", "batch")
    assert source(completion()) == (None, None)


def test_openrouter_extract_reads_thinking_and_usage():
    body = completion(usage={"prompt_tokens": 20, "completion_tokens": 9, "cost": 0.0001,
                             "completion_tokens_details": {"reasoning_tokens": 4}})
    body["choices"][0]["message"]["reasoning"] = "some thought"
    out = openrouter_client.extract(body)
    assert out["thinking_text"] == "some thought" and out["thinking_blocks"] == 1
    assert (out["input_tokens"], out["output_tokens"], out["reasoning_tokens"]) == (20, 9, 4)
    assert out["reported_cost"] == 0.0001 and out["stop_reason"] == "stop" and out["text"] == "{}"
    body["choices"][0]["message"]["reasoning_details"] = [{"type": "reasoning.text"}, {"type": "reasoning.text"}]
    assert openrouter_client.extract(body)["thinking_blocks"] == 2
    plain = openrouter_client.extract(completion())
    assert plain["thinking_text"] is None and plain["thinking_blocks"] == 0


def test_batch_entries():
    entries = openrouter_client.batch_entries
    assert entries({"status": "in_progress"}, ["a"]) == ({}, False)
    assert entries({"status": "completed", "results": None}, ["a"]) == ({}, False)
    out, ready = entries({"status": "failed", "results": None, "error": {"message": "boom"}}, ["a", "b"])
    assert ready and set(out) == {"a", "b"}
    assert out["a"]["error"]["type"] == "batch_failed" and "boom" in out["a"]["error"]["message"]
    results = [
        {"custom_id": "a", "error": {"type": "invalid_request_error", "message": "bad"}},
        {"custom_id": "b", "response": {"status_code": 500, "body": {"error": {"message": "oops"}}}},
        {"custom_id": "c", "response": {"status_code": 200, "body": completion(), "request_id": "r1"}},
        {"custom_id": "e", "response": {"status_code": 200, "body": {"error": {"message": "late"}}}},
        {"custom_id": "c", "response": {"status_code": 500, "body": None}},
        {"custom_id": "not-asked", "response": {"status_code": 200, "body": completion()}},
    ]
    out, ready = entries({"status": "completed", "results": results}, ["a", "b", "c", "d", "e"])
    assert ready and set(out) == {"a", "b", "c", "d", "e"}
    assert out["a"]["error"]["type"] == "invalid_request_error"
    assert (out["b"]["error"]["type"], out["b"]["error"]["status"], out["b"]["error"]["retryable"]) == (
        "http", 500, True)
    assert "oops" in out["b"]["error"]["message"]
    assert out["c"] == {"ok": True, "body": completion(), "request_id": "r1"}
    assert out["d"]["error"]["type"] == "missing"
    assert out["e"]["ok"] is False and "late" in out["e"]["error"]["message"]


@pytest.mark.parametrize("reply,uncertain", [
    (httpx.ReadTimeout, True),
    (httpx.ConnectError, True),
    (httpx.Response(500, json={"error": {"message": "x"}}), True),
    (httpx.Response(408, text="timeout"), True),
    (httpx.Response(200, json={"status": "validating"}), True),
    (httpx.Response(200, text="not json"), True),
    (httpx.Response(400, json={"error": {"message": "bad"}}), False),
    (httpx.Response(402, json={"error": {"message": "credit"}}), False),
])
def test_openrouter_batch_create_failures(no_keys, monkeypatch, reply, uncertain):
    def handler(request):
        if isinstance(reply, type):
            raise reply("simulated", request=request)
        return reply

    transport(monkeypatch, handler)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE)
    with pytest.raises(ClientError) as e:
        openrouter_client.OpenRouterClient().submit({"requests": []})
    assert isinstance(e.value, SubmitUncertain) is uncertain
    assert FAKE not in str(e.value)


def test_openrouter_batch_create_reply_is_unwrapped(no_keys, monkeypatch):
    replies = iter([{"id": "batch_1", "status": "validating"}, {"data": {"id": "batch_2", "status": "validating"}}])
    transport(monkeypatch, lambda request: httpx.Response(200, json=next(replies)))
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE)
    client = openrouter_client.OpenRouterClient()
    assert client.submit({"requests": []})["id"] == "batch_1"
    assert client.submit({"requests": []}) == {"id": "batch_2", "status": "validating"}


# ------------------------------------------------------------------------------------------- Hugging Face

def test_hf_body_names_the_reasoning_effort_only_where_set():
    gpt = hf_client.sync_body(rec_of("gpt_oss_120b"), settings.setting("gpt_oss_120b"))
    llama = hf_client.sync_body(rec_of("llama4_scout"), settings.setting("llama4_scout"))
    assert gpt["reasoning_effort"] == "low" and "reasoning_effort" not in llama
    assert gpt["model"] == "openai/gpt-oss-120b:deepinfra"
    assert gpt["messages"][0]["role"] == "system" and "provider" not in gpt
    for name in ("gpt_oss_120b", "llama4_scout"):
        assert hf_client.provider_requested(settings.setting(name)) == "deepinfra"


def test_hf_serving_provider_comes_from_the_header():
    out = hf_client.extract(completion(), {"x-inference-provider": "deepinfra"})
    assert (out["serving_provider"], out["serving_provider_source"]) == ("deepinfra", "header")
    out = hf_client.extract(completion(), {})
    assert (out["serving_provider"], out["serving_provider_source"]) == (None, None)


def test_hf_sync_request_sends_the_token_only_in_the_header(no_keys, monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=completion(), headers={"x-inference-provider": "deepinfra",
                                                               "set-cookie": "dropped"})

    transport(monkeypatch, handler)
    monkeypatch.setenv("HF_TOKEN", FAKE)
    body = hf_client.sync_body(rec_of("llama4_scout"), settings.setting("llama4_scout"))
    data, headers = hf_client.HFClient().send_sync(body)
    assert str(seen[0].url) == hf_client.URL
    assert seen[0].headers["authorization"] == f"Bearer {FAKE}"
    assert FAKE not in seen[0].content.decode("utf-8")
    assert headers == {"x-inference-provider": "deepinfra"}


def test_hf_listing_sends_the_token_only_after_a_401(monkeypatch):
    auth = []

    def handler(request):
        auth.append(request.headers.get("authorization"))
        if "authorization" not in request.headers:
            return httpx.Response(401, json={"error": "unauthorised"})
        return httpx.Response(200, json={"data": []})

    transport(monkeypatch, handler)
    assert hf_client.listing("tok") == (hf_client.MODELS_URL, {"data": []})
    assert auth == [None, "Bearer tok"]
    with pytest.raises(ClientError) as e:
        hf_client.listing(None)
    assert e.value.status == 401


def test_hf_requests_go_over_ipv4_only(no_keys, monkeypatch):
    # 11 November 2026: the TLS handshake over the NAT64 IPv6 addresses of router.huggingface.co timed out, so every
    # HF request binds its socket to an IPv4 address; the other clients are unchanged, and a test transport is kept
    monkeypatch.setattr(common, "TRANSPORT", None)
    for ipv4, bound in ((True, "0.0.0.0"), (False, None)):
        with common.http_client(5.0, ipv4=ipv4) as c:
            assert c._transport._pool._local_address == bound
    monkeypatch.setenv("HF_TOKEN", FAKE)
    hf = hf_client.HFClient()
    assert hf._http._transport._pool._local_address == "0.0.0.0"
    hf._http.close()
    seen = []

    def fake_request(method, url, headers=None, **kw):
        seen.append((bool(headers), kw.get("ipv4")))
        if not headers:
            raise ClientError("HTTP 401", status=401)
        return httpx.Response(200, json={"data": []})

    monkeypatch.setattr(common, "request", fake_request)
    assert hf_client.listing("tok") == (hf_client.MODELS_URL, {"data": []})
    assert seen == [(False, True), (True, True)]
    mock = httpx.MockTransport(lambda r: httpx.Response(200))
    monkeypatch.setattr(common, "TRANSPORT", mock)
    with common.http_client(5.0, ipv4=True) as c:
        assert c._transport is mock


# ------------------------------------------------------------------------------------- shared error mapping

def test_transport_failures_and_retry_after(monkeypatch):
    replies = iter([httpx.ReadTimeout, httpx.ConnectError,
                    httpx.Response(503, text="busy", headers={"Retry-After": "7"}),
                    httpx.Response(429, text="slow", headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}),
                    httpx.Response(404, text="gone")])

    def handler(request):
        r = next(replies)
        if isinstance(r, type):
            raise r("simulated", request=request)
        return r

    transport(monkeypatch, handler)
    url = "https://example.test/x"
    errors = []
    for _ in range(5):
        with pytest.raises(ClientError) as e:
            common.request("GET", url)
        errors.append(e.value)
    assert (errors[0].kind, errors[0].message) == ("timeout", f"ReadTimeout on GET {url}")
    assert (errors[1].kind, errors[1].message) == ("transport", f"ConnectError on GET {url}")
    assert (errors[2].status, errors[2].retryable, errors[2].retry_after) == (503, True, 7.0)
    assert (errors[3].status, errors[3].retryable, errors[3].retry_after) == (429, True, 0.0)
    assert (errors[4].status, errors[4].retryable, errors[4].retry_after) == (404, False, None)
    assert common.retry_after_seconds({"retry-after": "soon"}) is None


def test_a_reply_that_is_not_json_is_a_decode_error():
    with pytest.raises(ClientError) as e:
        common.json_of(httpx.Response(200, text="<html>"))
    assert e.value.kind == "decode" and e.value.status == 200


# --------------------------------------------------------------------------------------------- .env reader

def test_load_env_reads_names_and_keeps_values_already_set(tmp_path, monkeypatch):
    clear_env(monkeypatch, "EPI_TEST_A", "EPI_TEST_B", "EPI_TEST_C", "NOEQUALS")
    monkeypatch.setenv("EPI_TEST_C", "keep")
    path = tmp_path / "test.env"
    path.write_text("# comment\n\nexport EPI_TEST_A='one'\nEPI_TEST_B=\"two\"\nNOEQUALS\n1BAD=3\nEPI_TEST_C=new\n",
                    encoding="utf-8")
    assert keys.load_env(path) == ["EPI_TEST_A", "EPI_TEST_B", "EPI_TEST_C"]
    import os
    assert (os.environ["EPI_TEST_A"], os.environ["EPI_TEST_B"], os.environ["EPI_TEST_C"]) == ("one", "two", "keep")
    assert "NOEQUALS" not in os.environ


def test_a_missing_key_names_the_variable_and_not_a_value(no_keys):
    with pytest.raises(keys.MissingKey) as e:
        keys.key("openrouter")
    assert "OPENROUTER_API_KEY is not set" in str(e.value)


# ---------------------------------------------------------------------------------------------------- prices

def test_pick_endpoint():
    rows = [{"tag": "deepinfra/fp8", "pricing": {"prompt": "0.1", "completion": "0.3"}},
            {"tag": "deepinfra/fp8/flex", "pricing": {"prompt": "0.05", "completion": "0.2"}},
            {"tag": "openai", "pricing": {"prompt": "0.2", "completion": "0.4"}}]
    assert pricing.pick_endpoint(rows, "openai") == (rows[2], None)
    assert pricing.pick_endpoint(rows, "deepinfra/fp8") == (rows[0], None)
    row, note = pricing.pick_endpoint(rows, "deepinfra")
    assert row is rows[0] and note.startswith("ambiguous: tags deepinfra/fp8, deepinfra/fp8/flex")
    row, note = pricing.pick_endpoint(rows[2:], "open")
    assert row is None and note == "no endpoint in the listing has the tag open"
    row, note = pricing.pick_endpoint(rows[1:], "deepinfra")
    assert row is rows[1] and note == "tag deepinfra/fp8/flex matched by prefix"


def test_offline_and_anthropic_price_records_use_the_cost_model(monkeypatch):
    def no_network(request):
        raise AssertionError(f"network: {request.url}")

    transport(monkeypatch, no_network)
    rec = pricing.price_record("gpt6luna", "sync", offline=True)
    assert rec["source"] == "cost_model" and rec["note"].startswith("offline")
    assert (rec["price_in"], rec["price_out"]) == pricing.model_price("gpt6luna", "sync")
    for name in settings.ANTHROPIC:
        rec = pricing.price_record(name, "batch")
        assert rec["provider"] == "anthropic" and rec["source"] == "cost_model"
        assert (rec["price_in"], rec["price_out"]) == pricing.model_price(name, "batch")


def saved_listings(request):
    """The listings saved on 6 and 7 November 2026, served at the URLs pricing.py reads."""
    path = urllib.parse.unquote(request.url.path)
    if request.url.host == "router.huggingface.co" and path == "/v1/models":
        return httpx.Response(200, content=(RAW / "huggingface_2026-11-06" / "router_v1_models.json").read_bytes())
    prefix, suffix = "/api/v1/models/", "/endpoints"
    if request.url.host == "openrouter.ai" and path.startswith(prefix) and path.endswith(suffix):
        model = path[len(prefix):-len(suffix)]
        batch = model.endswith(":batch")
        stem = model.removesuffix(":batch").replace("/", "_") + ("_batch" if batch else "")
        f = RAW / "openrouter_endpoints_2026-11-07" / f"{stem}.json"
        if f.exists():
            return httpx.Response(200, content=f.read_bytes())
    return httpx.Response(404, json={"error": {"message": f"no saved listing for {path}"}})


@pytest.mark.parametrize("name,route,price_in,price_out,note", [
    ("gpt6luna", "sync", 0.10, 0.50, None),
    ("gpt6luna", "batch", 0.05, 0.25, None),
    ("deepseek_flash", "sync", 0.14, 0.42, None),
    ("deepseek_flash", "batch", 0.112, 0.336, "tag deepinfra/fp8 matched by prefix"),
    ("gemini_flash_lite", "sync", 0.25, 1.50, None),
    ("mistral_small", "sync", 0.15, 0.60, None),
    ("qwen_flash", "sync", 0.03, 0.13, None),
    ("glm_flash", "sync", 0.075, 0.25, None),
    ("gpt_oss_120b", "sync", 0.037, 0.17, "the Hugging Face router states no precision"),
    ("llama4_scout", "sync", 0.10, 0.30, "the Hugging Face router states no precision"),
])
def test_price_records_from_the_saved_listings(no_keys, monkeypatch, capsys, name, route, price_in, price_out,
                                               note):
    transport(monkeypatch, saved_listings)
    rec = pricing.price_record(name, route)
    assert rec["source"] == "listing"
    assert rec["price_in"] == pytest.approx(price_in) and rec["price_out"] == pytest.approx(price_out)
    assert rec["provider"] == pricing.provider_requested(name, route)
    if note is None:
        assert rec["note"] is None and rec["endpoint_tag"] == rec["provider"]
    else:
        assert rec["note"].startswith(note)
    assert rec["listing_url"] and rec["listing"]
    assert "warning" not in capsys.readouterr().err


def test_an_unreadable_listing_leaves_the_cost_model_with_a_warning(no_keys, monkeypatch, capsys):
    transport(monkeypatch, lambda request: httpx.Response(503, text="down"))
    rec = pricing.price_record("mistral_small", "sync")
    assert rec["source"] == "cost_model" and rec["note"].startswith("listing not read (ClientError")
    assert (rec["price_in"], rec["price_out"]) == pricing.model_price("mistral_small", "sync")
    assert "warning: mistral_small sync: listing not read" in capsys.readouterr().err


def test_a_listing_dearer_than_the_cost_model_gives_a_warning(no_keys, monkeypatch, capsys):
    dear = {"data": {"endpoints": [{"tag": "mistral/zdr", "pricing": {"prompt": "0.0000003",
                                                                    "completion": "0.0000012"}}]}}
    transport(monkeypatch, lambda request: httpx.Response(200, json=dear))
    rec = pricing.price_record("mistral_small", "sync")
    assert rec["source"] == "listing" and (rec["price_in"], rec["price_out"]) == (0.3, 1.2)
    assert "exceeds the cost model" in rec["note"]
    assert "exceeds the cost model" in capsys.readouterr().err
