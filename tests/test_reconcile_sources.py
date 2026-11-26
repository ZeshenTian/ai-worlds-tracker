import json

from src.dedup import deduplicate
from src.models import AIWorldCase, RawPost, RawTweetRecord
from src.reconcile_sources import candidate_groups, replay, source_additions
from src.storage import digest, write_json, write_rows


DEMO = "https://play.example/games/island"
REPO = "https://github.com/maker/experiments"


def record(i, text, handle="maker", *, demo=None, repo=None, refs=()):
    return RawTweetRecord(post=RawPost(tweet_id=str(i), author_handle=handle, text=text,
                                       referenced_post_ids=list(refs)), demo_urls=[demo] if demo else [],
                          external_urls=[repo] if repo else [])


def case_for(r, demo=None, repo=None, fingerprint=None):
    fingerprint = fingerprint or f"x:{r.post.tweet_id}"
    return AIWorldCase(world_id="world-" + digest(fingerprint)[:24], title="An island", summary="Explore the island",
                       original_post_url=r.original_url, author_handle=r.post.author_handle, theme_category="other",
                       models_used=[], tech_stack=[], generation_mode="unknown", reproducibility_level="video_only",
                       repo_url=repo, live_demo_url=demo, is_open_source=None, cost_disclosure_status="undisclosed",
                       workflow_steps=[], skills_or_prompts_used=[], evidence_quotes=[], dedup_fingerprint=fingerprint,
                       review_status="approved")


def test_replay_only_attaches_direct_first_party_same_work_and_is_idempotent(tmp_path):
    original = record(411, "I built an island. Demo: " + DEMO, demo=DEMO)
    good = record(412, "I updated the island. Play: https://t.co/world", demo=DEMO)
    good.post.expanded_urls["https://t.co/world"] = DEMO
    other_author = record(413, "I updated a game. Play: " + DEMO, handle="elsewhere", demo=DEMO)
    mention = record(414, "I made a forest inspired by " + DEMO, demo=DEMO)
    other_demo = "https://play.example/games/second"
    roundup = record(415, f"I built new worlds. Play: {DEMO} and {other_demo}", demo=DEMO)
    ad = record(416, f"I updated this game. Play: {DEMO} #ad", demo=DEMO)
    metadata_only = record(417, "I updated the island. Play: https://t.co/absent", demo=DEMO)
    metadata_only.post.expanded_urls["https://t.co/not-in-post"] = DEMO
    homepage = record(418, "I built games. Play: https://example.com", demo="https://example.com")
    more_homepage = record(419, "I released a game. Play: https://example.com", demo="https://example.com")
    first = case_for(original, DEMO)
    second = case_for(homepage, "https://example.com")
    rows = [first, second]
    posts = [original, good, other_author, mention, roundup, ad, metadata_only, homepage, more_homepage]
    expected = {first.world_id: [good.original_url]}
    assert source_additions(rows, posts) == expected
    assert source_additions(rows, posts, excluded_authors=["MaKeR"]) == {}
    assert source_additions([first.model_copy(update={"review_status":"rejected"})], posts) == {}
    assert source_additions([first, case_for(other_author, DEMO)], posts) == {}
    root = tmp_path / "data"
    ledger = root / "processed/cases.jsonl"
    write_rows(ledger, rows)
    for src in posts:
        write_json(root / "raw/x" / f"{src.post.tweet_id}.json", src.model_dump(mode="json"))
    before = ledger.read_bytes()
    assert replay(root, tmp_path / "seeds.yaml") == {"cases":1, "related_posts_added":1}
    assert ledger.read_bytes() == before
    assert not (root / ".pipeline.lock").exists()
    assert replay(root, tmp_path / "seeds.yaml", apply=True)["related_posts_added"] == 1
    changed = ledger.read_bytes().splitlines()
    assert json.loads(changed[0]) == json.loads(before.splitlines()[0]) | {"related_post_urls": [good.original_url]}
    assert changed[1] == before.splitlines()[1]
    assert replay(root, tmp_path / "seeds.yaml", apply=True)["related_posts_added"] == 0


def test_repository_update_requires_same_author_reference_and_exact_project_subpath():
    a, b = REPO + "/tree/main/island", REPO + "/tree/main/other"
    source = record(421, "I built an island. Source: " + a, repo=a)
    good = record(422, "I updated the level. Source: " + a, repo=a, refs=["421"])
    unrelated = record(423, "I added a second game. Source: " + b, repo=b, refs=["421"])
    unproven = record(424, "I added a revision. Source: " + a, repo=a)
    root_only = record(425, "I updated a game. Source: " + REPO, repo=REPO, refs=["421"])
    c = case_for(source, repo=REPO)
    assert source_additions([c], [source, good, unrelated, unproven, root_only]) == {c.world_id: [good.original_url]}


def test_existing_shared_repo_cannot_swallow_other_games_or_overwrite_old_case():
    a, b = REPO + "/tree/main/island", REPO + "/tree/main/maze"
    maze = "https://play.example/games/maze"
    original = record(431, f"I built an island. Play: {DEMO} Source: {a}", demo=DEMO, repo=a)
    second = record(432, f"I built a maze. Play: {maze} Source: {b}", demo=maze, repo=b)
    third = record(433, f"I built another thing. Source: {REPO}", repo=REPO)
    curator = record(434, "Try a project. Play: " + DEMO, handle="curator", demo=DEMO)
    c = case_for(original, DEMO, REPO, fingerprint=REPO)
    posts = [original, second, third, curator]
    groups = candidate_groups(deduplicate(posts), [c], posts)
    candidates = {g.original.post.tweet_id:g for g in groups}
    assert set(candidates) == {"432", "433", "434"}
    assert not candidates["432"].possible_duplicate_urls
    assert c.original_post_url in candidates["434"].possible_duplicate_urls
    assert all(c.original_post_url not in g.related_post_urls for g in groups)
    assert c.original_post_url in candidates["433"].possible_duplicate_urls
    assert all(g.fingerprint != c.dedup_fingerprint for g in groups)
    missing = candidate_groups(deduplicate([third]), [c], [third])
    assert len(missing) == 1 and missing[0].fingerprint == "x:433"
    assert missing[0].possible_duplicate_urls == [c.original_post_url]


def test_known_raw_demo_stays_in_review_without_blocking_unrelated_repository_mentions():
    original = record(441, f"I built the island. Play: {DEMO} Source: {REPO}", demo=DEMO, repo=REPO)
    third_party = record(442, f"Play: {DEMO}", handle="gallery", demo=DEMO)
    library_user = record(443, f"I made something with a library from {REPO}", handle="independent", repo=REPO)
    c = case_for(original)
    posts = [original, third_party, library_user]
    fresh = {g.original.post.tweet_id:g for g in candidate_groups(deduplicate(posts), [c], posts)}
    assert fresh["442"].possible_duplicate_urls == [c.original_post_url]
    assert not fresh["443"].possible_duplicate_urls
