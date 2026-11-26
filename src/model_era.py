"""Classify disclosed models; dates only resolve unversioned family names."""

from __future__ import annotations
import re
from datetime import date
from typing import Literal
from unicodedata import normalize

# Model names are ASCII tokens even in unspaced Chinese or Japanese prose.
TOKEN_FLAGS = re.IGNORECASE | re.ASCII
HYPHENS = str.maketrans("‐‑‒–—−", "------")
VERSION = re.compile(r"\b(gpt|astra|fable|opus|gemini)[\s-]*(\d+)(?:\.(\d+))?\b", TOKEN_FLAGS)
REVERSED = re.compile(r"\b(\d+)\.(\d+)\s*astra\b", TOKEN_FLAGS)
GEMINI_ALIAS = re.compile(r"\b(?:neon|hydrogen|carbon|argon)[\s-]*(\d+)\b", TOKEN_FLAGS)
MINIMUM = {
    "gpt": (6, 2),
    "astra": (6, 2),
    "fable": (5, 2),
    "opus": (5, 5),
    "gemini": (4, 0),
}
CUTOFF = {
    key: cutoff
    for cutoff, keys in [
        ("2026-11-10", ("claude", "claude code", "gemini", "antigravity")),
        ("2026-11-17", ("gpt", "chatgpt", "codex", "astra")),
    ]
    for key in keys
}
CUE = re.compile(
    r"three[ .]?js|webgpu|webgl|blender|unreal|unity|glsl|shader|(?:single|one)[- ]html|\b3d\b|三维|3Dシーン"
    r"|\b(?:babylon\.js|playcanvas|godot|voxel(?:s)?|diorama|ray[- ]trac(?:ed|ing)|"
    r"path[- ]trac(?:ed|ing)|first[- ]person|procedural (?:geometry|terrain))\b",
    TOKEN_FLAGS,
)


def explicit_frontier(text):
    text = normalize("NFKC", text).translate(HYPHENS)
    return (
        any(
            (int(v), int(m or 0)) >= MINIMUM[k.lower()]
            for k, v, m in VERSION.findall(text)
        )
        or any((int(v), int(m)) >= (6, 2) for v, m in REVERSED.findall(text))
        or any(int(v) >= 4 for v in GEMINI_ALIAS.findall(text))
    )


def classify_model_era(
    models_used: list[str], published_at: str | None
) -> Literal["frontier", "legacy"]:
    if any(explicit_frontier(name) for name in models_used):
        return "frontier"
    names = [s.strip().lower() for s in models_used]
    if not names or not all(s in CUTOFF for s in names) or not published_at:
        return "legacy"
    try:
        stamp = date.fromisoformat(str(published_at)[:10]).isoformat()
    except ValueError:
        return "legacy"
    return "frontier" if any(stamp >= CUTOFF[s] for s in names) else "legacy"


def has_frontier_signal(text, published_at):
    return bool(
        explicit_frontier(text)
        or re.search(r"\b(hydrogen|carbon)\b", text, TOKEN_FLAGS)
        or (
            str(published_at or "")[:10] >= "2026-11-10"
            and CUE.search(text)
            and re.search(r"\b(claude|gemini|antigravity|gpt|codex|chatgpt|astra)\b", text, TOKEN_FLAGS)
        )
    )


# Preserve undisclosed versions. Unidentified labels stay in the source evidence and
# do not become model-filter options simply because an extractor produced them.
_AUX = re.compile(
    r"^(?:@?fal(?:ai)?\b|tripo(?:ai|\b)|meshy|hyper3d|hunyuan3d|higgsfield|ue\s*\d|unreal|two\.js|rust\s*\+|gifenc|procedural blender|rokoko|mesh2motion|suno|depth anything|vfx studio|claudeanimationbase|seedance|seedream|grok imagine|qwen[- ]image|gpt[- ]image|nano banana|flux|kimodo|three[. ]?js|blender|web audio|webgpu|webgl|unity|playcanvas|babylon)",
    re.I,
)
_OTHER_LLM = re.compile(
    r"^(?:deepseek|glm|kimi|minimax|step|qwen|grok|hermes|world labs|marble|llama|mistral|mixtral|gemma|yi|ernie|gpt-oss|command-r)\b",
    re.I,
)
_VARIANT = r"(neon|carbon|argon|hydrogen|krypton)"
_VERSION = r"(\d+(?:\.\d+)*)"
_GENERIC = {
    s.casefold(): s
    for s in (
        "Claude",
        "Claude Code",
        "Codex",
        "GPT",
        "ChatGPT",
        "Gemini",
        "Astra",
        "Antigravity",
    )
}
_GENERIC.update({"claude ai": "Claude", "gpt astra": "Astra", "astra pro": "Astra"})


def _canonical_disclosure(raw):
    name = " ".join(normalize("NFKC", raw).translate(HYPHENS).split())
    if _AUX.match(name):
        return None
    low = name.lower()
    if low in _GENERIC:
        return _GENERIC[low]
    claude = re.search(
        r"\b(fable|opus|sonnet|haiku)(?:[\s(-]*(?:model\s*)?[\s(-]*" + _VERSION + r")?",
        low,
    )
    if claude:
        return "Claude " + claude[1].title() + (" " + claude[2] if claude[2] else "")
    if re.fullmatch(r"claude\s+" + _VERSION, low):
        return "Claude " + low.split()[-1]
    variant = re.search(r"(astra|atra|sol)(?![a-z])", low)
    if re.match(
        r"(?:openai\s+)?(?:chatgpt|gpt|codex|astra|sol|\d+(?:\.\d+)?\s+(?:astra|sol))",
        low,
    ):
        version = re.search(_VERSION, low)
        if version:
            return (
                "GPT-"
                + ("6.2" if version[1] == "62" and variant and variant[1] in {"astra", "atra"} else version[1])
                + (" " + ("Sol" if variant[1] == "sol" else "Astra") if variant else "")
            )
    if "gemini" in low or re.match(_VARIANT + r"(?:\s+\d+)?$", low):
        variant = re.search(_VARIANT, low)
        version = re.search(_VERSION, low)
        if variant and not version and "gemini" not in low:
            return variant[1].title()
        if variant:
            # These marketing aliases refer to Gemini 4. An explicit version wins.
            return (
                "Gemini " + (version[1] if version else "4") + " " + variant[1].title()
            )
        if version:
            tier = re.search(r"\b(flash|pro|ultra)\b", low)
            return "Gemini " + version[1] + (" " + tier[1].title() if tier else "")
    if _OTHER_LLM.match(name):
        return (
            re.sub(r"(?i)^deepseek[-\s]*v?", "DeepSeek ", name).strip()
            if low.startswith("deepseek")
            else name
        )
    return None


def canonicalize_models_and_stack(models_used, tech_stack):
    """Produce stable filters without altering original disclosure quotations."""
    models, stack = [], list(tech_stack)
    for supplied in models_used:
        # Preserve compound tool names such as Rust + Vulkan.
        parts = (
            [supplied]
            if _AUX.match(supplied)
            else re.split(r"\s+\+\s+|\s+with\s+(?=Antigravity\b)", supplied, flags=re.I)
        )
        for part in parts:
            label = _canonical_disclosure(part)
            if label:
                if label not in models:
                    models.append(label)
            elif _AUX.match(part):
                stack.append(part.strip())
    if "Antigravity" in models and len(models) > 1:
        models.remove("Antigravity")
    unique_stack = {}
    for tag in stack:
        if re.match(r"^(?:google\s+)?antigravity\b", tag.strip(), re.I):
            continue
        if tag.strip() and tag.casefold() not in {m.casefold() for m in models}:
            unique_stack.setdefault(tag.strip().casefold(), tag.strip())
    # "Gemini" and "Gemini 4 Neon" in the same disclosure are one model mention.
    folded = {
        "Claude": r"Claude (?:Fable|Opus|Haiku|Sonnet|\d)",
        "GPT": r"GPT-\d",
        "Gemini": r"Gemini \d",
    }
    models = [
        m
        for m in models
        if m not in folded or not any(re.match(folded[m], n) for n in models)
    ]
    return models, list(unique_stack.values())
