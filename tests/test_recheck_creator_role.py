from types import SimpleNamespace

import pytest
from src.models import ReviewStatus
from src.recheck_attribution import RULES as TEXT_RULES, apply_attribution
from src.recheck_creator_role import ModelClaim, Resolution, ground_resolution, reference_rule_id, role_rule_id
from src.storage import digest, encode


def example():
    return {"post": "Gemini 4 — shaded conservatory\n\nI prompted it to build my conservatory in a 3D engine.",
            "thread": [], "own_quote": ""}


def decision(**updates):
    fields = dict(index=0, pattern="split_disclosure", human_role="maker_or_team", scope="coded_scene",
        source_basis="actual_frame_and_original", counterevidence="none", prior_excerpt_resolution="no_prior_excerpt",
        creation_quote="I prompted it to build my conservatory", subject_quote="shaded conservatory", contrary_quote="",
        observation="The frame shows the conservatory's vaulted geometry in an engine viewport.",
        models=[ModelClaim(term="Gemini 4", quote="Gemini 4 — shaded conservatory")])
    return Resolution(**{**fields, **updates})


def test_disclosure_and_human_creation_can_appear_in_separate_paragraphs():
    result = ground_resolution(example(), decision(), has_images=True, previous_quotes=[])
    assert result["decision"] == "allow"
    assert result["models"][0]["term"] == "Gemini 4"


def test_ai_grammatical_subject_and_engine_handle_can_refer_to_human_operated_tools():
    packet = {"post": "Aurora generated my observatory in @graphEngine. My prompt asked for the domed roof.",
              "thread": [], "own_quote": ""}
    verdict = decision(pattern="model_as_actor", creation_quote="My prompt asked for the domed roof",
        subject_quote="Aurora generated my observatory", models=[ModelClaim(term="Aurora", quote="Aurora generated my observatory")],
        prior_excerpt_resolution="tool_or_model_reference")
    assert ground_resolution(packet, verdict, has_images=True,
                             previous_quotes=["Aurora generated my observatory"])["decision"] == "allow"


@pytest.mark.parametrize("changes", [
    {"counterevidence": "other_human_or_team"}, {"counterevidence": "sponsored_or_promo"},
    {"counterevidence": "tool_or_roundup"}, {"human_role": "reporting_on_others"},
    {"scope": "outside_scope"}, {"creation_quote": "I built an entirely different scene"},
    {"subject_quote": "a project the author never named"}, {"pattern": "none"},
    {"models": [ModelClaim(term="GPT", quote="I used GPT")]}, {"contrary_quote": "shaded conservatory"},
])
def test_a_picture_cannot_override_missing_or_contrary_source_evidence(changes):
    assert ground_resolution(example(), decision(**changes), has_images=True, previous_quotes=[])["decision"] == "hold"


def test_text_without_images_requires_direct_human_and_implementation_evidence():
    assert ground_resolution(example(), decision(), has_images=False, previous_quotes=[])["decision"] == "hold"
    verdict = decision(source_basis="explicit_original_implementation")
    assert ground_resolution(example(), verdict, has_images=False, previous_quotes=[])["decision"] == "allow"
    unresolved = ["I prompted it to build my conservatory"]
    assert ground_resolution(example(), verdict, has_images=False, previous_quotes=unresolved)["decision"] == "hold"


def test_durable_creator_correction_requires_same_original_and_does_not_override_manual_rejection(tmp_path):
    case = SimpleNamespace(world_id="world-role", author_handle="builder", original_post_url="https://x.com/builder/status/432",
        source_kind="x_post", review_status=ReviewStatus.PENDING, models_used=[], evidence_quotes=[], published_at="2026-11-24T00:00:00Z")
    proof = ground_resolution(example(), decision(), has_images=True, previous_quotes=[])
    corrected = {**proof, "rules": role_rule_id(), "reference_rules": reference_rule_id(), "source_url": case.original_post_url, "text_key": "record"}
    entry = {"source": case.original_post_url, "key": "record", "policy": digest(encode([TEXT_RULES, "mini"])),
             "proof": {"decision": "hold", "quote": "", "models": []}, "creator_resolution": corrected}
    policy = {"model": "mini", "protected": set(), "decisions": {case.world_id: entry}}
    assert apply_attribution(case, tmp_path, policy) == "allow"
    assert case.models_used == ["Gemini 4"]
    corrected["text_key"] = "different original"
    assert apply_attribution(case, tmp_path, policy) == "hold"
    case.review_status = ReviewStatus.REJECTED
    assert apply_attribution(case, tmp_path, policy) == "reject"


def test_missing_optional_provider_keeps_existing_decisions_available(tmp_path, monkeypatch):
    import src.recheck_creator_role as module
    monkeypatch.delenv("ALIBABA_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)
    assert module.qwen_client() is None
    assert module.PROVIDER == "Alibaba Cloud Model Studio"


def test_specific_other_creator_credit_or_unmapped_source_excerpt_cannot_be_overridden():
    from src.recheck_creator_role import Referent, ReferenceCheck, apply_references
    source = example()
    excerpt = "I prompted it to build my conservatory"
    valid = ReferenceCheck(**decision().model_dump(),
        references=[Referent(index=0, source_span="I prompted it", role="this_creator_or_own_project")])
    assert apply_references(source, valid, [excerpt], has_images=True)["decision"] == "allow"
    for references in ([], [Referent(index=0, source_span="some other person's words", role="model_or_engine")],
                       [Referent(index=0, source_span="I prompted it", role="third_party_created_it")]):
        assert apply_references(source, valid.model_copy(update={"references": references}),
                                [excerpt], has_images=True)["decision"] == "hold"


def test_correcting_creator_semantics_cannot_override_previously_verified_2d_only_work():
    from src.recheck_creator_role import corrected_application
    confirmed = {"decision": "allow", "rules": role_rule_id(), "reference_rules": reference_rule_id()}
    assert corrected_application({"creator_resolution": confirmed})
    assert not corrected_application({"creator_resolution": confirmed,
                                      "video_visual": {"author_check": {"media": "only_2d_or_ui"}}})
    assert not corrected_application({"creator_resolution": {**confirmed, "reference_rules": "missing"}})


def test_unrecognized_verbatim_referent_label_defers_the_whole_claim():
    from src.recheck_creator_role import apply_references, parse_reference_response
    raw = {**decision().model_dump(), "references": [
        {"index": 0, "source_span": "my conservatory", "role": "some_unrecognized_reply"}]}
    item, unknown = parse_reference_response(raw)
    assert unknown == ["some_unrecognized_reply"]
    assert apply_references(example(), item, ["my conservatory"], has_images=True)["decision"] == "hold"


def test_absence_of_a_named_outside_human_requires_positive_first_party_proof():
    from src.recheck_creator_role import HumanCreditCheck, ground_human_credit
    packet = example()
    valid = HumanCreditCheck(**decision().model_dump(), references=[], human_credit="posting_person_or_team",
        outside_party_span="", credited_work_span="shaded conservatory", posting_creator_span="I prompted it",
        who_made_what="The poster prompted the model to build the conservatory.")
    proof = {"decision": "allow", "models": [{"term": "Gemini 4", "quote": "Gemini 4 — shaded conservatory"}]}
    assert ground_human_credit(packet, valid, proof)["decision"] == "allow"
    unknown = valid.model_copy(update={"human_credit": "external_person_or_team", "outside_party_span": ""})
    outcome = ground_human_credit(packet, unknown, proof)
    assert outcome["decision"] == "hold"
    assert outcome["human_credit"] == "unresolved"
    no_maker = valid.model_copy(update={"posting_creator_span": ""})
    assert ground_human_credit(packet, no_maker, proof)["decision"] == "hold"


def test_external_human_work_credit_is_preserved_as_verbatim_evidence():
    from src.recheck_creator_role import HumanCreditCheck, ground_human_credit
    packet = {**example(), "post": "A developer created the conservatory with an engine. I found their demo yesterday."}
    item = HumanCreditCheck(**decision().model_dump(), references=[], human_credit="external_person_or_team",
        outside_party_span="A developer", credited_work_span="created the conservatory", posting_creator_span="",
        who_made_what="A developer created the conservatory and the poster found it.")
    out = ground_human_credit(packet, item, {"decision": "hold", "models": []})
    assert out["human_credit"] == "external_person_or_team"
    assert out["outside_party_span"] == "A developer"
    assert out["decision"] == "hold"


def test_named_model_is_not_an_outside_human_even_if_a_verb_takes_it_as_subject():
    from src.recheck_outside_credit import EntityVerdict, ground_entity
    p = {"post": "Gemini 4 built the terraced scene. My prompt specified the three ramps.", "own_quote": "", "thread": []}
    previous = {"claimed_party": "Gemini 4", "source_basis": "actual_frame_and_original"}
    v = EntityVerdict(index=0, alleged_kind="ai_model", creator="outside_human_or_team",
        human_identity_quote="Gemini 4", human_credit_clause="Gemini 4 built the terraced scene.",
        personal_creation_quote="", project_quote="terraced scene", spatial_or_coded_scene=True,
        supported_original_work=False, exclusion="unclear", models=[], findings="The named party is a model.")
    out = ground_entity(p, previous, v, observed=True)
    assert out["decision"] == "hold"
    assert out["human_credit"] == "unresolved"
    assert not out["outside_party_span"]
    v = v.model_copy(update={"creator": "poster", "exclusion": "none", "supported_original_work": True,
        "human_credit_clause": "", "human_identity_quote": "", "personal_creation_quote": "My prompt specified the three ramps",
        "models": [ModelClaim(term="Gemini 4", quote="Gemini 4 built the terraced scene.")]})
    assert ground_entity(p, previous, v, observed=True)["decision"] == "allow"


def test_distinct_human_who_used_an_ai_can_be_the_actual_outside_creator():
    from src.recheck_outside_credit import EntityVerdict, ground_entity
    p = {"post": "Another developer using Gemini built this game.", "own_quote": "", "thread": []}
    previous = {"claimed_party": "Another developer using Gemini"}
    v = EntityVerdict(index=0, alleged_kind="human", creator="outside_human_or_team",
        human_identity_quote="Another developer using Gemini", human_credit_clause=p["post"], personal_creation_quote="",
        project_quote="this game", spatial_or_coded_scene=True, supported_original_work=False, exclusion="reporting",
        models=[], findings="The poster attributes the game to a different developer.")
    out = ground_entity(p, previous, v, observed=True)
    assert out["decision"] == "hold"
    assert out["human_credit"] == "external_person_or_team"


def test_reporting_or_naming_alone_is_insufficient_to_assign_outside_authorship():
    from src.recheck_outside_credit import direct_credit_clause
    assert not direct_credit_clause("The studio", "The studio says the AI generated the world.")
    assert not direct_credit_clause("某团队", "某团队给它起名叫《城》。")
    assert direct_credit_clause("The studio", "The studio says they built the world using an AI model.")
    assert direct_credit_clause("Custom Games", "The demo was developed by Custom Games.")


def test_verified_native_reposts_support_a_concrete_originator_prompt_but_upload_alone_does_not():
    from src.recheck_native_credits import NativeFinding, ground_native
    packet = {"post": "Orion made my 3D library. I asked it to generate a library with balconies.", "thread": [], "own_quote": ""}
    later = [{"source_text": "Orion produced this library.", "explicit_attribution_lines": []}]
    finding = NativeFinding(action="posted_own_prompt_for_this_result", own_action_quote="I asked it to generate a library with balconies",
        work_quote="3D library", external_credit_quote="", contradictory_credit_quote="", cited_another_human_as_creator=False,
        original_spatial_or_coded_work=True, promo_or_roundup=False, models=[ModelClaim(term="Orion", quote="Orion made my 3D library")],
        finding="The poster specifies the actual request and the pictured work matches.")
    assert ground_native(packet, later, finding)["decision"] == "allow"
    for change in ({"action":"none"}, {"own_action_quote":""}, {"cited_another_human_as_creator":True},
                   {"action":"explicitly_credited_by_later_creator", "external_credit_quote":"Orion produced this library."}):
        assert ground_native(packet, later, finding.model_copy(update=change))["decision"] == "hold"

def test_token_plan_key_and_endpoint_are_paired(monkeypatch):
    import src.recheck_creator_role as m
    monkeypatch.setenv("ALIBABA_TOKEN_PLAN_API_KEY","test-token-plan")
    monkeypatch.setenv("DASHSCOPE_BASE_URL","https://wrong.example")
    with m.qwen_client() as client:
        assert str(client.base_url).rstrip("/")==m.TOKEN_PLAN_URL

def test_native_subject_is_enough_without_first_person_quote():
    source={**example(),"has_attached_media":True}
    assert ground_resolution(source,decision(creation_quote="",pattern="none"),has_images=True,previous_quotes=[])["decision"]=="allow"

def test_official_concrete_demo_vs_release_only():
    from src.frontier_review import assess
    case=SimpleNamespace(author_handle="GoogleAI",original_post_url="https://x.com/GoogleAI/status/808",live_demo_url=None,evidence_quotes=[])
    def check(post):
        return assess(case,dict(post=post,thread=[],own_quote="",has_attached_media=True),{}, {},[])["decision"]
    assert check("Gemini 4 generated this interactive 3D ocean scene.")=="allow"
    assert check("Announcing Gemini 4 with new pricing plans.")!="allow"
    assert check("3D ocean scene by @OtherCreator with Gemini 4.")!="allow"
