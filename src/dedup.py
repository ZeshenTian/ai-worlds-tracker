from collections import Counter, defaultdict
from datetime import UTC, datetime
from difflib import SequenceMatcher
import re
from urllib.parse import urlsplit

from .links import identity_url, repo_root, urls_in
from .models import CaseGroup, RawTweetRecord


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


def origin_rank(record: RawTweetRecord, owners: set[str]) -> tuple:
    timestamp = record.post.published_at or datetime.max.replace(tzinfo=UTC)
    timestamp = timestamp.replace(tzinfo=timestamp.tzinfo or UTC)
    return (record.post.author_handle.casefold() not in owners, attributed_elsewhere(record),
            timestamp, int(record.post.tweet_id))


def deduplicate(records: list[RawTweetRecord]) -> list[CaseGroup]:
    records = sorted(records, key=lambda row: int(row.post.tweet_id))
    clusters = list(range(len(records)))
    keys: dict[str, int] = {}
    repos = [{repo for url in row.external_urls if (repo := repo_root(url))} for row in records]
    demos = [{identity_url(url): url for url in row.demo_urls} for row in records]

    def root(index: int) -> int:
        while clusters[index] != index:
            clusters[index] = clusters[clusters[index]]
            index = clusters[index]
        return index

    for index, (repo_keys, demo_keys) in enumerate(zip(repos, demos, strict=True)):
        for key in sorted(repo_keys | demo_keys.keys()):
            representative = keys.setdefault(key, index)
            clusters[root(index)] = root(representative)

    groups = defaultdict(list)
    for index in range(len(records)):
        groups[root(index)].append(index)

    cases = []
    for members in groups.values():
        owners = {urlsplit(url).path.split("/")[1] for index in members for url in repos[index]}
        ranked = sorted(members, key=lambda index: origin_rank(records[index], owners))
        chosen = ranked[0]
        original = records[chosen]
        repo_urls = list(dict.fromkeys(url for index in ranked for url in sorted(repos[index])))
        demo_urls = list(dict.fromkeys(url for index in ranked for url in demos[index].values()))
        fingerprint = repo_urls[0] if repo_urls else (
            identity_url(demo_urls[0]) if demo_urls else f"x:{original.post.tweet_id}"
        )
        cases.append(CaseGroup(
            original=original, fingerprint=fingerprint,
            related_post_urls=[records[index].original_url for index in ranked[1:]],
            external_urls=list(dict.fromkeys(url for index in ranked for url in records[index].external_urls)),
            repo_urls=repo_urls, demo_urls=demo_urls,
        ))

    texts = [post_text(group.original) for group in cases]
    counts = [Counter(text) for text in texts]
    for index, current in enumerate(cases):
        current_media = set(current.original.post.media_keys)
        for second in range(index + 1, len(cases)):
            other = cases[second]
            if (current.repo_urls or current.demo_urls) and (other.repo_urls or other.demo_urls):
                continue
            same_media = current_media.intersection(other.original.post.media_keys)
            a, b = texts[index], texts[second]
            combined = len(a) + len(b)
            # Both tests are upper bounds on the number of characters a matcher can align.
            if not same_media:
                if min(len(a), len(b)) < 32 or 20 * min(len(a), len(b)) < 9 * combined:
                    continue
                if 20 * sum((counts[index] & counts[second]).values()) < 9 * combined:
                    continue
            if same_media or SequenceMatcher(None, a, b).ratio() >= 0.9:
                current.possible_duplicate_urls.append(other.original.original_url)
                other.possible_duplicate_urls.append(current.original.original_url)
    return sorted(cases, key=lambda group: int(group.original.post.tweet_id))
