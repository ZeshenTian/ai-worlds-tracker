from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from difflib import SequenceMatcher
import re
from urllib.parse import urlsplit

from rapidfuzz import fuzz, process

from .ingest_x import DEMO_LABEL
from .links import external_url, identity_url, repo_project_key, repo_root, urls_in, work_demo_key
from .models import CaseGroup, RawTweetRecord
from .x_media import record_keys


def post_text(record: RawTweetRecord) -> str:
    text = record.post.text
    for url, _ in urls_in(text):
        text = text.replace(url, "")
    return re.sub(r"[\W_]+", " ", text.casefold()).strip()


def attributed_elsewhere(record: RawTweetRecord) -> bool:
    attributed = re.search(r"\b(?:credit to|made by|built by|via)\s+@([\w]+)|(?:作者|转自)[：:\s]*@([\w]+)",
                           record.post.text, re.I)
    return bool(attributed and next(group for group in attributed.groups() if group).casefold()
                != record.post.author_handle.casefold())


def origin_rank(record: RawTweetRecord, owners: set[str], excluded: set[str]) -> tuple:
    timestamp = record.post.published_at or datetime.max.replace(tzinfo=UTC)
    timestamp = timestamp.replace(tzinfo=timestamp.tzinfo or UTC)
    handle = record.post.author_handle.casefold()
    return (handle in excluded, handle not in owners, attributed_elsewhere(record),
            timestamp, int(record.post.tweet_id))


def record_demo_urls(record: RawTweetRecord) -> list[str]:
    # Older normalized caches removed hash routes. Restore only author-labelled destinations.
    demos = dict.fromkeys(record.demo_urls)
    if not demos:
        return []
    old_bases = {identity_url(url): url for url in demos if not urlsplit(url).fragment}
    for post in [record.post, *record.thread]:
        for url, position in urls_in(post.text):
            expanded = post.expanded_urls.get(url, url)
            if "#" not in expanded or not DEMO_LABEL.search(post.text[max(position - 80, 0):position]):
                continue
            clean = external_url(expanded)
            if clean and urlsplit(clean).fragment:
                base = old_bases.get(identity_url(clean.split("#", 1)[0]))
                if base:
                    demos.pop(base, None)
                    demos[clean] = None
    return list(demos)


def record_work_keys(record: RawTweetRecord) -> tuple[set[str], set[str]]:
    """Return project-level labelled demos and specific source-code destinations."""
    return ({key for url in record_demo_urls(record) if (key := work_demo_key(url))},
            {key for url in record.external_urls if (key := repo_project_key(url))})


SOURCE_LINK = re.compile(r"(?:source(?: code)?|code|repository|repo|源码|源代码|仓库|ソース)\W{0,12}$", re.I)


def project_repo_evidence(record: RawTweetRecord, key: str) -> bool:
    owner = urlsplit(key).path.split("/")[1].casefold()
    if owner == record.post.author_handle.casefold():
        return True
    for post in [record.post, *record.thread]:
        if re.search(rf"\bby\s+@{re.escape(owner)}\b", post.text, re.I):
            return True
        for url, position in urls_in(post.text):
            if SOURCE_LINK.search(post.text[max(0, position - 80):position]) and repo_project_key(
                    post.expanded_urls.get(url, url)) == key:
                return True
    return False


def deduplicate(records: list[RawTweetRecord], *, excluded_authors: Iterable[str] = (),
                media_evidence=None) -> list[CaseGroup]:
    excluded = {name.casefold() for name in excluded_authors}
    records = sorted(records, key=lambda row: int(row.post.tweet_id))
    clusters = list(range(len(records)))
    demo_urls = [record_demo_urls(r) for r in records]
    demos = [{key for url in urls if (key := work_demo_key(url))} for urls in demo_urls]
    projects = [{key for url in r.external_urls if (key := repo_project_key(url))} for r in records]
    repo_demos, demo_projects, root_projects = defaultdict(set), defaultdict(set), defaultdict(set)
    multiple = set()
    for i, (repo_keys, demo_keys) in enumerate(zip(projects, demos, strict=True)):
        if len(repo_keys) > 1 or len(demo_keys) > 1:
            multiple.add(i)
        for key in repo_keys:
            root_projects[repo_root(key)].add(key)
            repo_demos[key].update(demo_keys)
        for key in demo_keys:
            demo_projects[key].update(repo_keys)

    def root(index: int) -> int:
        while clusters[index] != index:
            clusters[index] = clusters[clusters[index]]
            index = clusters[index]
        return index

    # A roundup cannot bridge multiple works. A shared repository with evidence of
    # different playable destinations cannot identify a work on its own.
    keys: dict[str, int] = {}
    record_keys_used = []
    for i, record in enumerate(records):
        strong = []
        if i not in multiple:
            for key in sorted(projects[i]):
                if (len(repo_demos[key]) <= 1 and (key != repo_root(key) or len(root_projects[key]) == 1)
                        and project_repo_evidence(record, key)):
                    strong.append(key)
            strong.extend(key for key in sorted(demos[i]) if len(demo_projects[key]) <= 1)
        record_keys_used.append(strong)
        for key in strong:
            first = keys.setdefault(key, i)
            clusters[root(i)] = root(first)

    groups = defaultdict(list)
    for index in range(len(records)):
        groups[root(index)].append(index)

    cases = []
    for members in groups.values():
        owners = {urlsplit(url).path.split("/")[1] for index in members for url in projects[index]}
        ranked = sorted(members, key=lambda index: origin_rank(records[index], owners, excluded))
        chosen = ranked[0]
        original = records[chosen]
        repo_urls = list(dict.fromkeys(repo_root(key) for index in ranked for key in sorted(projects[index])))
        group_demos = list(dict.fromkeys(url for index in ranked for url in demo_urls[index]))
        work_keys = [key for index in ranked for key in record_keys_used[index]]
        fingerprint = work_keys[0] if work_keys else f"x:{original.post.tweet_id}"
        cases.append(CaseGroup(
            original=original, fingerprint=fingerprint,
            related_post_urls=[records[index].original_url for index in ranked[1:]],
            external_urls=list(dict.fromkeys(url for index in ranked for url in [*records[index].external_urls, *demo_urls[index]])),
            repo_urls=repo_urls, demo_urls=group_demos,
        ))

    texts = [post_text(group.original) for group in cases]
    # Normalized longest common subsequence is an upper bound for SequenceMatcher.
    # RapidFuzz's native cutoff cheaply discards pairs that cannot reach 0.9.
    no_link = {i: text for i, text in enumerate(texts)
               if len(text) >= 32 and not (cases[i].repo_urls or cases[i].demo_urls)}
    with_link = {i: text for i, text in enumerate(texts) if len(text) >= 32 and i not in no_link}
    media = defaultdict(set)
    media_keys = [record_keys(group.original, media_evidence or {}) for group in cases]
    for i, keys in enumerate(media_keys):
        for key in keys:
            media[key].add(i)
    for i, group in enumerate(cases):
        shared = {j for key in media_keys[i] for j in media[key] if j > i}
        no_link.pop(i, None)
        with_link.pop(i, None)
        pools = [no_link] if group.repo_urls or group.demo_urls else [no_link, with_link]
        candidates = set()
        if len(texts[i]) >= 32:
            for pool in pools:
                candidates.update(j for _, _, j in process.extract_iter(
                    texts[i], pool, scorer=fuzz.ratio, score_cutoff=89.999999))
        for j in sorted(candidates | shared):
            other = cases[j]
            if (group.repo_urls or group.demo_urls) and (other.repo_urls or other.demo_urls):
                continue
            if j in shared or SequenceMatcher(None, texts[i], texts[j]).ratio() >= 0.9:
                group.possible_duplicate_urls.append(other.original.original_url)
                other.possible_duplicate_urls.append(group.original.original_url)
    return sorted(cases, key=lambda group: int(group.original.post.tweet_id))
