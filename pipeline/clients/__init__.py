"""API clients. ops(api) gives the module of one API (request bodies and the extraction of replies, no network);
make(api) gives a client that sends requests with the key, or with stub=True a stand-in that answers from
made-up replies and never touches the network."""
from __future__ import annotations

import importlib

MODULES = {"anthropic": "anthropic_client", "openrouter": "openrouter_client", "hf": "hf_client"}
CLASSES = {"anthropic": "AnthropicClient", "openrouter": "OpenRouterClient", "hf": "HFClient"}
STUBS = {"anthropic": "StubAnthropic", "openrouter": "StubOpenRouter", "hf": "StubHF"}


def ops(api: str):
    if api not in MODULES:
        raise KeyError(f"unknown api {api}; known: {', '.join(MODULES)}")
    return importlib.import_module(f"pipeline.clients.{MODULES[api]}")


def make(api: str, stub: bool = False, store=None):
    module = ops(api)
    if stub:
        from pipeline.clients import stub as s
        return getattr(s, STUBS[api])(store)
    return getattr(module, CLASSES[api])()
