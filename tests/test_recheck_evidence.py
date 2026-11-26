from types import SimpleNamespace
from src.models import ReviewStatus
from src.recheck_evidence import Disclosure, Evidence, evidence_patch


def test_disclosure_review_requires_verbatim_claim_in_author_text():
    work = SimpleNamespace(review_status=ReviewStatus.PENDING, models_used=[], tech_stack=["WebGL"], evidence_quotes=[])
    source = "I built the city with Neon 4."
    proof = Evidence(original_spatial_work=True, models=[
        Disclosure(term="Neon 4", quote=source),
        Disclosure(term="GPT-6.2", quote=source),
        Disclosure(term="Opus 5.6", quote="I built it in Opus 5.6."),
    ], technologies=[Disclosure(term="city", quote=source)])
    assert evidence_patch(work, [source], proof) == {"models_used": ["Neon 4"], "evidence_quotes": [source]}
    work.review_status = ReviewStatus.REJECTED
    assert evidence_patch(work, [source], proof) == {}
    work.review_status = ReviewStatus.PENDING
    assert evidence_patch(work, [source], proof.model_copy(update={"original_spatial_work":False})) == {}
