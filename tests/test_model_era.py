import pytest
from src.model_era import classify_model_era


@pytest.mark.parametrize(
    "name",
    [
        "GPT-6.2 Astra",
        "GPT 6.2 Astra (High)",
        "Astra 6.2",
        "6.2 Astra",
        "GPT-7",
        "GPT-6.10",
        "Fable 5.2",
        "Opus 5.5",
        "Opus 5.6",
        "Gemini 4 Neon",
        "Neon 4",
        "Carbon 4",
        "Gemini 10",
    ],
)
def test_explicit(name):
    assert classify_model_era(["Marble", name], None) == "frontier"


@pytest.mark.parametrize(
    "name",
    [
        "GPT-6 Astra",
        "GPT-6.1",
        "Fable 5.1",
        "Opus 4.6",
        "Gemini 3 Pro",
        "Marble",
        "Qwen",
        "DeepSeek",
        "Kimi",
    ],
)
def test_legacy(name):
    assert classify_model_era(["Claude", name], "2026-11-24") == "legacy"


@pytest.mark.parametrize(
    "model,stamp,expected",
    [
        ("Claude", "2026-11-10", "frontier"),
        ("Claude", "2026-10-15", "legacy"),
        ("Codex", "2026-11-17", "frontier"),
        ("Codex", "2026-11-05", "legacy"),
        ("Astra", None, "legacy"),
    ],
)
def test_generic(model, stamp, expected):
    assert classify_model_era([model], stamp) == expected


def test_extraction_disclosure_preserves_literal_source_and_version():
    from src.extract_structured import model_words, source_model_quote
    sentence = "I built this browser world using Astra 6.2."
    assert source_model_quote("GPT-6.2 Astra", [sentence]) == sentence
    assert source_model_quote("GPT-6.3 Astra", [sentence]) is None
    assert source_model_quote("GPT-6.2 Astra", ["I never used Astra 6.2."]) is None
    assert model_words("Gemini 4 Neon") == model_words("Neon 4")


@pytest.mark.parametrize("text", ["用GPT‑6.2制作", "Gemini 4で生成", "使用Claude做了Three.js场景", "I used Astra to build a voxel village in Godot."])
def test_unspaced_multilingual_frontier_signal(text):
    from src.model_era import has_frontier_signal

    assert has_frontier_signal(text, "2026-11-24")
    assert not has_frontier_signal("microgpt-6.2", "2026-11-24")

@pytest.mark.parametrize("aliases,canonical",[
    (["Fable5.2","Anthropic Fable 5.2","Claude(Fable 5.2)","Fable 5.2 xhigh"],"Claude Fable 5.2"),
    (["Claude Code（Opus 5.5）","Opus5.5","opus 5.5 Medium"],"Claude Opus 5.5"),
    (["opus model (5.6)","OPUS 5.6"],"Claude Opus 5.6"),
    (["ChatGPT-6.2 Astra","Astra 6.2 High","GPT-6.2 Atra High","6.2 Astra","GPT Astra-6.2"],"GPT-6.2 Astra"),
    (["GPT-6.2 Sol(高)","sol 6.2","GPT 6.2 SOL MAX"],"GPT-6.2 Sol"),
    (["gemini neon","Neon 4","Gemini4 Neon Low"],"Gemini 4 Neon"),
    (["Gemini 4 Hydrogen Flash","Google Gemini 4 Hydrogen (Extra)"],"Gemini 4 Hydrogen"),
    (["Gemini Carbon 4","Gemini 4 Carbon-H"],"Gemini 4 Carbon"),
    (["Google's Gemini 4 Argon","gemini argon"],"Gemini 4 Argon"),
    (["GPT-6 Astra Pro"],"GPT-6 Astra"),(["Fable 5.1"],"Claude Fable 5.1"),
    (["Marble"],"Marble"),(["Kimi K3.1 Pro"],"Kimi K3.1 Pro")
])
def test_taxonomy_aliases(aliases,canonical):
    from src.model_era import canonicalize_models_and_stack as clean
    assert clean(aliases,[])==([canonical],[])
    assert clean(*clean(aliases,[]))==([canonical],[])

def test_auxiliary_models_move_to_stack():
    from src.model_era import canonicalize_models_and_stack as clean
    tools=["Tripo HD 3.1","Two.js","UE 5.9","gifenc","@fal","Higgsfield","Rust + Vulkan","Rokoko","Seedance 2.5","Suno"]
    models,stack=clean(["Gemini 4 Neon","Antigravity",*tools],["Two.js"])
    assert models==["Gemini 4 Neon"] and set(stack)==set(tools)
    assert clean([], ["Google Antigravity platform", "Antigravity /swarm", "Three.js"]) == ([], ["Three.js"])
    assert clean(["Antigravity"],[])==(["Antigravity"],[])


def test_astra_missing_decimal():
    from src.model_era import canonicalize_models_and_stack
    for spelling in ("GPT-62 Astra", "GPT 62 Astra"):
        assert canonicalize_models_and_stack([spelling], [])[0] == ["GPT-6.2 Astra"]
