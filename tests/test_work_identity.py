from src.dedup import deduplicate, record_work_keys
from src.ingest_x import collect_links
from src.links import external_url, identity_url, repo_project_key, work_demo_key
from src.models import RawPost, RawTweetRecord


def source(i, author="maker", *, repos=(), demos=(), text=""):
    return RawTweetRecord(post=RawPost(tweet_id=str(i), text=text, author_handle=author),
                          external_urls=list(repos), demo_urls=list(demos))


def test_repo_paths_and_shared_monorepo_do_not_merge_worlds():
    root = "https://github.com/maker/experiments"
    tree = root + "/tree/main/worlds"
    a = source(101, repos=[tree + "/clock"], demos=["https://maker.example/clock"])
    b = source(102, repos=[tree + "/island"], demos=["https://maker.example/island"])
    c = source(103, repos=[root + "/blob/main/worlds/clock/index.html"])
    d = source(104, repos=[root])
    groups = deduplicate([a, b, c, d])
    assert [(g.original.post.tweet_id, g.related_post_urls) for g in groups] == [
        ("101", [c.original_url]), ("102", []), ("104", [])]
    assert len({g.fingerprint for g in groups}) == 3
    assert repo_project_key(root + "/issues/315") is None
    assert repo_project_key(root + "/blob/main/README.md") == root


def test_same_repository_with_conflicting_demos_and_compilation_cannot_bridge():
    repo = "https://github.com/maker/lab"
    first, second = "https://maker.example/clock", "https://maker.example/island"
    a, b = source(201, repos=[repo], demos=[first]), source(202, repos=[repo], demos=[second])
    roundup = source(203, repos=[repo], demos=[first, second])
    missing = source(204, repos=[repo])
    again = source(205, repos=[repo], demos=[first])
    groups = deduplicate([a, b, roundup, missing, again])
    assert len(groups) == 4
    assert groups[0].related_post_urls == [again.original_url]
    assert len({g.fingerprint for g in groups}) == 4


def test_standalone_repository_owner_and_explicit_source_are_merged_bare_mentions_are_not():
    repo = "https://github.com/maker/clock"
    made = source(301, repos=[repo])
    source_credit = source(302, "poster", repos=[repo], text="Clock source: " + repo)
    unconnected = source(303, "unconnected", repos=[repo], text="I read about " + repo)
    groups = deduplicate([made, source_credit, unconnected])
    assert [g.related_post_urls for g in groups] == [[source_credit.original_url], []]
    assert groups[0].fingerprint == repo


def test_hash_routes_survive_ingestion_and_recovery_from_previously_stripped_raw_data(tmp_path):
    base = "https://maker.example/play"
    first = base + "#/world/clock"
    second = base + "#!/world/island"
    a = collect_links(source(401, text="Try it: " + first), None, tmp_path)
    b = source(402, demos=[base], text="Demo: https://t.co/game")
    b.post.expanded_urls = {"https://t.co/game": second}
    c = source(403, demos=[base], text="Demo: " + first)
    groups = deduplicate([a, b, c])
    assert [(g.demo_urls, g.related_post_urls) for g in groups] == [
        ([first], [c.original_url]), ([second], [])]
    assert groups[1].external_urls == [second]
    assert record_work_keys(b) == ({second}, set())
    assert external_url(base + "#controls") == base
    assert identity_url(first) != identity_url(second)


def test_project_keys_require_more_than_a_platform_home_or_directory():
    for url in ["https://maker.example/", "https://maker.example/portfolio", "https://maker.example/users/name",
                "https://maker.github.io/", "https://claude.ai/new", "https://gamecatalog.example/games",
                "https://chatgpt.com/share/abc", "https://username.chatgpt.site/", "https://itch.io/browse"]:
        assert work_demo_key(url) is None
    assert work_demo_key("https://one-game.vercel.app/") == "https://one-game.vercel.app"
    assert work_demo_key("https://studio.example/worlds/clock?utm_campaign=a") == "https://studio.example/worlds/clock"
    generic = "https://gamecatalog.example/gallery"
    assert len(deduplicate([source(501, demos=[generic]), source(502, demos=[generic])])) == 2
