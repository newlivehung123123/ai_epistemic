"""Model settings of PLAN 5.2 to 5.5 and the provider choices of design/notes/openrouter_providers_2026-11-07.md.
FROZEN at the freeze. Output caps are PILOT values (PLAN 5.5) until the freeze.

Keys
    api              anthropic, openrouter or hf
    model            the model ID sent (HF IDs carry the provider suffix)
    thinking         Anthropic only: the thinking object sent, or None to omit the field (the model's default)
    reasoning        OpenRouter only: the reasoning object sent
    reasoning_effort HF only: the OpenAI chat-completions parameter, or None to omit it
    sync_provider    OpenRouter sync: the one provider slug named in provider.only
    batch_provider   OpenRouter batch: the base provider named at the top level of the batch
    route            {"pilot": ..., "sprint": ...}, each batch or sync
    max_tokens       output cap, including any thinking or reasoning tokens
    thinks           True where the cost model assumes thinking or reasoning tokens
    stubborn         True only for the stubbornness demonstration (PLAN 4.7)
"""
from __future__ import annotations

CAP_PLAIN = 600       # PLAN 5.5, settings without reasoning (PILOT)
CAP_REASONING = 4000  # PLAN 5.5, settings with reasoning or thinking (PILOT)

ANTHROPIC_SDK = "0.85.0"   # PLAN 5.2: pinned; sends the API version header 2023-06-01

SETTINGS = {
    # PLAN 5.2. Effort is never sent, so every Anthropic setting runs at its default effort.
    "haiku_off": {"api": "anthropic", "label": "Haiku 5.5 off", "model": "claude-haiku-5-5",
                  "thinking": {"type": "disabled"}, "max_tokens": CAP_PLAIN, "thinks": False,
                  "route": {"pilot": "batch", "sprint": "batch"}},
    "haiku_medium": {"api": "anthropic", "label": "Haiku 5.5 medium", "model": "claude-haiku-5-5",
                     "thinking": None, "max_tokens": CAP_REASONING, "thinks": True,
                     "route": {"pilot": "batch", "sprint": "batch"}},
    "sonnet_off": {"api": "anthropic", "label": "Sonnet 5.5 off", "model": "claude-sonnet-5-5",
                   "thinking": {"type": "between_tools"}, "max_tokens": CAP_PLAIN, "thinks": False,
                   "route": {"pilot": "batch", "sprint": "batch"}},
    "sonnet_high": {"api": "anthropic", "label": "Sonnet 5.5 high (pilot only)", "model": "claude-sonnet-5-5",
                    "thinking": None, "max_tokens": CAP_REASONING, "thinks": True,
                    "route": {"pilot": "batch", "sprint": None}},
    # PLAN 5.3 and the provider note of 7 November 2026
    "gpt6luna": {"api": "openrouter", "label": "gpt-6-luna", "model": "openai/gpt-6-luna",
                 "reasoning": {"effort": "none"}, "sync_provider": "openai", "batch_provider": "openai",
                 "max_tokens": CAP_PLAIN, "thinks": False, "route": {"pilot": "sync", "sprint": "sync"}},
    "gemini_flash_lite": {"api": "openrouter", "label": "gemini-3.1-flash-lite",
                          "model": "google/gemini-3.1-flash-lite", "reasoning": {"effort": "none"},
                          "sync_provider": "google-ai-studio", "batch_provider": None,
                          "max_tokens": CAP_PLAIN, "thinks": False, "route": {"pilot": "sync", "sprint": "sync"}},
    "mistral_small": {"api": "openrouter", "label": "mistral-small-2603", "model": "mistralai/mistral-small-2603",
                      "reasoning": {"effort": "none"}, "sync_provider": "mistral/zdr", "batch_provider": None,
                      "max_tokens": CAP_PLAIN, "thinks": False, "route": {"pilot": "sync", "sprint": "sync"}},
    "deepseek_flash": {"api": "openrouter", "label": "deepseek-v4.1-flash", "model": "deepseek/deepseek-v4.1-flash",
                       "reasoning": {"effort": "none"}, "sync_provider": "deepinfra/fp8",
                       "batch_provider": "deepinfra", "max_tokens": CAP_PLAIN, "thinks": False,
                       "route": {"pilot": "sync", "sprint": "sync"}},
    # Reasoning off if the API accepts off (PLAN 10.3 rule 7); the cap allows for reasoning in case it does not.
    "qwen_flash": {"api": "openrouter", "label": "qwen3.7-flash", "model": "qwen/qwen3.7-flash",
                   "reasoning": {"enabled": False}, "sync_provider": "alibaba", "batch_provider": None,
                   "max_tokens": CAP_REASONING, "thinks": True, "route": {"pilot": "sync", "sprint": "sync"}},
    "glm_flash": {"api": "openrouter", "label": "glm-5.3-flash", "model": "z-ai/glm-5.3-flash",
                  "reasoning": {"effort": "low"}, "sync_provider": "gmicloud/fp8", "batch_provider": None,
                  "max_tokens": CAP_REASONING, "thinks": True, "route": {"pilot": "sync", "sprint": "sync"}},
    # PLAN 5.4: HF sync through DeepInfra, provider named in the model ID
    "gpt_oss_120b": {"api": "hf", "label": "gpt-oss-120b", "model": "openai/gpt-oss-120b:deepinfra",
                     "reasoning_effort": "low", "max_tokens": CAP_REASONING, "thinks": True,
                     "route": {"pilot": "sync", "sprint": "sync"}},
    "llama4_scout": {"api": "hf", "label": "llama-4-scout",
                     "model": "meta-llama/Llama-4-Scout-17B-16E-Instruct:deepinfra", "reasoning_effort": None,
                     "max_tokens": CAP_PLAIN, "thinks": False, "route": {"pilot": "sync", "sprint": "sync"}},
}
# PLAN 4.7: Haiku 5.5 off with one sentence added to the system prompt; a key of its own keeps its custom_ids apart
SETTINGS["haiku_off_stub"] = {**SETTINGS["haiku_off"], "label": "Haiku 5.5 off, stubbornness demonstration",
                              "stubborn": True, "route": {"pilot": None, "sprint": "batch"}}

ANTHROPIC = tuple(k for k, v in SETTINGS.items() if v["api"] == "anthropic")
PANEL = ("gpt6luna", "gemini_flash_lite", "mistral_small", "deepseek_flash", "qwen_flash", "glm_flash",
         "gpt_oss_120b", "llama4_scout")
PROBE_SETTINGS = ("haiku_off", "sonnet_off") + PANEL   # PLAN 4.6

# Cost-model names (design/cost_model.py) for the price of each setting
COST_MODEL_NAME = {
    "haiku_off": ("Haiku 5.5", "off"), "haiku_medium": ("Haiku 5.5", "medium"),
    "sonnet_off": ("Sonnet 5.5", "off"), "sonnet_high": ("Sonnet 5.5", "high"),
    "haiku_off_stub": ("Haiku 5.5", "off"),
    "gpt6luna": ("gpt-6-luna", "off"), "gemini_flash_lite": ("gemini-3.1-flash-lite", "off"),
    "mistral_small": ("mistral-small-2603", "off"), "deepseek_flash": ("deepseek-v4.1-flash", "off"),
    "qwen_flash": ("qwen3.7-flash", "off"), "glm_flash": ("glm-5.3-flash", "off"),
    "gpt_oss_120b": ("gpt-oss-120b", "off"), "llama4_scout": ("llama-4-scout", "off"),
}


def setting(name: str) -> dict:
    if name not in SETTINGS:
        raise KeyError(f"unknown setting {name}; known: {', '.join(SETTINGS)}")
    return SETTINGS[name]


def route(name: str, run: str) -> str | None:
    """batch or sync for this setting in this run (pilot or sprint)."""
    return SETTINGS[name]["route"].get(run)
