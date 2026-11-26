"""Attach provable same-work creator updates, and keep other new sources available for review."""
import argparse
from collections import defaultdict
from contextlib import nullcontext
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import yaml

from .dedup import attributed_elsewhere, deduplicate, project_repo_evidence, record_work_keys
from .links import external_url, post_id, repo_project_key, repo_root, urls_in, work_demo_key
from .models import AIWorldCase, RawTweetRecord, ReviewStatus
from .qualify_candidates import PROMO
from .storage import digest, read_rows, run_lock, write_text


# Require a creator's own action or a demo invitation tied directly to the displayed link.
CREATOR_ACTION = re.compile(
    r"\b(?:I|we)(?:['’]ve)?\s+(?:(?:just|also|finally|recently)\s+)?(?:built|made|created|coded|added|updated|shipped|released|fixed|implemented)\b"
    r"|(?:我|我们)(?:刚|又|也|已经|给它)?(?:做了|制作|开发|改了|更新|新增|发布)"
    r"|(?:作りました|作ってみた|実装しました|追加しました|更新しました)", re.I)
LINK_INVITATION = re.compile(r"(?:\b(?:play(?:able demo)?|try (?:it|the demo)|(?:live )?demo)|试玩|プレイ)[\s:：→👇-]{0,10}$", re.I)
UPDATE = re.compile(r"\b(?:added|updated|fixed|improved|patched|implemented)\b|新增|更新|修复|実装|追加", re.I)


def source_id(url):
    try:
        return post_id(url)
    except ValueError:
        return None


def direct_links(record):
    """Only links actually present in the top-level post, resolved by its own entities."""
    links = []
    post = record.post
    for url, position in urls_in(post.text):
        expanded = external_url(post.expanded_urls.get(url, url))
        if expanded:
            links.append((expanded, post.text[max(0, position - 60):position]))
    return links


def source_additions(cases, records, excluded_authors=()):
    by_id = {r.post.tweet_id: r for r in records}
    known = {source_id(url) for c in cases for url in [c.original_post_url, *c.related_post_urls]}
    excluded = {h.casefold() for h in excluded_authors}
    demo_owners, repo_owners = defaultdict(list), defaultdict(list)
    for case in cases:
        if case.live_demo_url and (key := work_demo_key(case.live_demo_url)):
            demo_owners[key].append(case)
        if case.repo_url and (key := repo_root(case.repo_url)):
            repo_owners[key].append(case)

    additions = defaultdict(list)
    for record in records:
        post = record.post
        handle = post.author_handle.casefold()
        if (post.tweet_id in known or handle in excluded or attributed_elsewhere(record)
                or PROMO.search(post.text)):
            continue
        links = direct_links(record)
        hits = {c.world_id: c for url, _ in links for c in
                [*demo_owners.get(work_demo_key(url), ()), *repo_owners.get(repo_root(url), ())]}
        if len(hits) != 1:
            continue
        case = next(iter(hits.values()))
        original_id = source_id(case.original_post_url)
        original = by_id.get(original_id)
        if (not original or case.source_kind != "x_post" or case.review_status == ReviewStatus.REJECTED
                or (case.author_handle or "").casefold() != handle
                or original.post.author_handle.casefold() != handle):
            continue
        # Reject roundups, tool links and mixed-purpose posts as a source of automatic provenance.
        demos = {work_demo_key(url) for url, _ in links if not repo_root(url)}
        repos = {repo_project_key(url) for url, _ in links if repo_root(url)}
        if len(demos) > 1 or len(repos) > 1 or None in demos or None in repos:
            continue
        own_original = {u for u, _ in direct_links(original)}
        demo_key = case.live_demo_url and work_demo_key(case.live_demo_url)
        same_demo = demo_key and demos == {demo_key} and any(work_demo_key(u) == demo_key for u in own_original)
        case_repo = case.repo_url and repo_root(case.repo_url)
        if repos and (not case_repo or any(repo_root(k) != case_repo for k in repos)):
            continue
        if demos and not same_demo:
            continue
        refers_to_original = original_id in post.referenced_post_ids
        scoped_repos = {key for key in repos if key != case_repo}
        same_repo = (refers_to_original and case_repo and case_repo.split("/")[-2].casefold() == handle
                     and UPDATE.search(post.text)
                     and scoped_repos.intersection(repo_project_key(u) for u in own_original))
        own_action = CREATOR_ACTION.search(post.text)
        invitation = any(work_demo_key(u) == demo_key and LINK_INVITATION.search(before) for u, before in links) if demo_key else False
        if same_demo:
            parts = urlsplit(demo_key)
            route = (parts.fragment.lstrip("!") or parts.path).strip("/").casefold()
            if any(segment in {"catalog", "dashboard", "portfolio", "gallery", "trending"} for segment in route.split("/")):
                continue
            if route in {"", "play", "demo", "projects", "index.html", "index.htm"} and not refers_to_original:
                continue
        creator_demo = same_demo and ((own_action and invitation) or (refers_to_original and (own_action or invitation)))
        if creator_demo or (same_repo and own_action):
            additions[case.world_id].append(record.original_url)
    return {wid: sorted(urls, key=lambda u: int(post_id(u))) for wid, urls in additions.items()}


def apply_additions(root, additions):
    if not additions:
        return
    path = root / "processed/cases.jsonl"
    with path.open(encoding="utf-8", newline="") as ledger:
        lines = ledger.readlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        row = json.loads(line)
        if extra := additions.get(row["world_id"]):
            row["related_post_urls"] = list(dict.fromkeys([*row.get("related_post_urls", ()), *extra]))
            lines[i] = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
    write_text(path, "".join(lines))


def candidate_groups(groups, cases, records, *, excluded_authors=(), media_evidence=None):
    known = {source_id(u) for c in cases for u in [c.original_post_url, *c.related_post_urls]}
    existing_ids = {c.world_id for c in cases}
    fingerprints = {c.dedup_fingerprint for c in cases}
    by_id = {r.post.tweet_id:r for r in records}
    by_repo, by_demo = defaultdict(list), defaultdict(list)
    original_keys = {}
    for c in cases:
        original = by_id.get(source_id(c.original_post_url))
        raw_demos, raw_projects = record_work_keys(original) if original else (set(), set())
        original_keys[c.world_id] = raw_projects
        if c.live_demo_url and (key := work_demo_key(c.live_demo_url)):
            by_demo[key].append(c)
        elif len(raw_demos) == 1:
            by_demo[next(iter(raw_demos))].append(c)
        if c.repo_url and (repo := repo_root(c.repo_url)):
            by_repo[repo].append(c)
        elif len(raw_projects) == 1:
            project = next(iter(raw_projects))
            if project_repo_evidence(original, project):
                by_repo[repo_root(project)].append(c)
    fresh = []
    for group in groups:
        members = [group.original.post.tweet_id, *(post_id(u) for u in group.related_post_urls)]
        remaining = [by_id[i] for i in members if i not in known]
        if not remaining:
            continue
        if len(remaining) == len(members):
            fresh.append(group)
        else:
            subgroups = deduplicate(remaining, excluded_authors=excluded_authors, media_evidence=media_evidence)
            for sub in subgroups:
                sub.possible_duplicate_urls = list(dict.fromkeys([*sub.possible_duplicate_urls, *group.possible_duplicate_urls]))
            fresh.extend(subgroups)
    for group in fresh:
        demos, projects = record_work_keys(group.original)
        matches = {c.original_post_url for d in demos for c in by_demo.get(d, ())}
        for project in projects:
            if not project_repo_evidence(group.original, project):
                continue
            root = repo_root(project)
            for case in by_repo.get(root, ()):
                old_keys = {k for k in original_keys[case.world_id] if repo_root(k) == root}
                distinct_project = old_keys and all(k != root and k != project for k in old_keys) and project != root
                distinct_demo = demos and case.live_demo_url and work_demo_key(case.live_demo_url) not in demos
                if not (distinct_project and distinct_demo):
                    matches.add(case.original_post_url)
        if group.fingerprint in fingerprints or "world-" + digest(group.fingerprint)[:24] in existing_ids:
            group.fingerprint = "x:" + group.original.post.tweet_id
        fingerprints.add(group.fingerprint)
        group.possible_duplicate_urls = list(dict.fromkeys([*group.possible_duplicate_urls, *sorted(matches)]))
    return fresh


def replay(root, seeds, *, apply=False):
    with run_lock(root) if apply else nullcontext():
        rows = read_rows(root / "processed/cases.jsonl", AIWorldCase)
        records = [RawTweetRecord.model_validate_json(p.read_bytes()) for p in (root / "raw/x").glob("*.json")]
        config = yaml.safe_load(seeds.read_text()) if seeds.is_file() else {}
        additions = source_additions(rows, records, (config or {}).get("excluded_aggregator_accounts", ()))
        if apply:
            apply_additions(root, additions)
        return {"cases": len(additions), "related_posts_added": sum(map(len, additions.values()))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--seeds", type=Path, default=Path("config/seeds.yaml"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps({"apply": args.apply, **replay(args.data_dir, args.seeds, apply=args.apply)}))


def canonical_originals(root, cases, excluded):
    """Orient duplicate relations by work identity and X upload chronology, across accounts."""
    from .x_media import record_keys, load_media_evidence
    from .public_x_media import cached_native_entities
    from .storage import read_json
    from .recheck_duplicates import DERIVATIVE, MIXED

    records = {
        p.stem: RawTweetRecord.model_validate_json(p.read_bytes())
        for p in (root / "raw/x").glob("*.json")
    }
    by_id = {
        source_id(c.original_post_url): c for c in cases if c.source_kind == "x_post"
    }
    if not records or not by_id:
        return {}
    excluded = {a.casefold() for a in excluded}
    native = cached_native_entities(root, records)
    assets = load_media_evidence(root)
    cover_file = root / "state/x_covers.json"
    covers = read_json(cover_file) if cover_file.is_file() else {}
    members = defaultdict(set)
    related = defaultdict(set)
    blockers = defaultdict(set)
    blocked_owner = set()
    for tid, record in records.items():
        row = by_id.get(tid)
        media = record_keys(record, assets)
        keys = {
            ("media", m)
            for m in media
            if m.isdecimal() or m.startswith("https://pbs.twimg.com/")
        }
        # A gallery can reuse images belonging to several different projects.
        if (
            sum(m.isdecimal() for m in media) > 1
            or sum(m.startswith("https://") for m in media) > 1
        ):
            keys.clear()
        if row and keys:
            cover = covers.get(row.world_id, {})
            sha = cover.get("source_sha256") or ""
            if cover.get("source_url") == record.original_url and re.fullmatch(
                "[0-9a-f]{64}", sha
            ):
                keys.add(("attachment_sha256", sha))
        demos, repos = record_work_keys(record)
        repos = {r for r in repos if project_repo_evidence(record, r)}
        if row and row.live_demo_url and (key := work_demo_key(row.live_demo_url)):
            demos.add(key)
        if row and row.repo_url and (key := repo_project_key(row.repo_url)):
            repos.add(key)
        if len(demos) <= 1 and len(repos) <= 1:
            keys.update(("demo", d) for d in demos)
            keys.update(("repo", r) for r in repos)
        for key in keys:
            members[key].add(tid)
        receipt = native.get(tid, {})
        origin = str(receipt.get("source_status_id") or "")
        if (
            origin.isdecimal()
            and int(origin) < int(tid)
            and receipt.get("source_user_id") != receipt.get("user_id")
        ):
            blocked_owner.add(tid)
            url = (
                records[origin].original_url
                if origin in records
                else (
                    f"https://x.com/{receipt['source_author']}/status/{origin}"
                    if receipt.get("source_author")
                    else None
                )
            )
            if url:
                blockers[tid].add(url)

    def eligible(tid):
        row = by_id.get(tid)
        rec = records[tid]
        return (
            tid not in blocked_owner
            and (not row or row.review_status != ReviewStatus.REJECTED)
            and rec.post.author_handle.casefold() not in excluded
            and not attributed_elsewhere(rec)
            and not PROMO.search(rec.post.text)
            and not MIXED.search(rec.post.text)
        )

    for ids in members.values():
        if len(ids) < 2 or not (ids & by_id.keys()):
            continue
        first = min((tid for tid in ids if eligible(tid)), key=int, default=None)
        if not first:
            continue
        original = records[first].original_url
        for tid in ids:
            if (
                int(tid) <= int(first)
                or DERIVATIVE.search(records[tid].post.text)
                or MIXED.search(records[tid].post.text)
            ):
                continue
            blockers[tid].add(original)
            if not PROMO.search(records[tid].post.text):
                related[first].add(records[tid].original_url)
    changes = {}
    for tid, row in by_id.items():
        if not tid or (not related.get(tid) and not blockers.get(tid)):
            continue
        before = (
            list(row.possible_duplicate_urls),
            list(row.related_post_urls),
            row.review_status,
        )
        # An earlier owner takes precedence even when this intermediate poster was subsequently copied.
        moved = (
            related[tid] if not blockers[tid] and tid not in blocked_owner else set()
        )
        row.possible_duplicate_urls = sorted(
            (set(row.possible_duplicate_urls) - moved) | blockers[tid]
        )
        row.related_post_urls = sorted(
            (set(row.related_post_urls) | moved) - set(row.possible_duplicate_urls)
        )
        if blockers[tid] and row.review_status == ReviewStatus.APPROVED:
            row.review_status = ReviewStatus.PENDING
        if before != (
            row.possible_duplicate_urls,
            row.related_post_urls,
            row.review_status,
        ):
            changes[row.world_id] = {
                "original": row.original_post_url,
                "related": sorted(moved),
                "earlier": sorted(blockers[tid]),
            }
    return changes
