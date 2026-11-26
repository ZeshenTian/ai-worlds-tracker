"""Capture X's public primary post and embed receipts for a reproducible sample of unresolved media pairs."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode

import httpx
import yaml

from .models import AIWorldCase, RawTweetRecord, ReviewStatus
from .public_x_media import cached_native_entities, origins
from .recheck_attribution import apply_attribution, load_policy
from .recheck_duplicates import attributed_repost, definite_asset, OWN_BUILD, QUOTED, source_id
from .reconcile_sources import CREATOR_ACTION
from .storage import read_json, read_rows, run_lock, write_json
from .x_media import load_media_evidence, record_keys


TRANSIENT = {"ConnectTimeout", "ReadTimeout", "ConnectError", "ProxyError", "RemoteProtocolError"}


def select_pairs(root, seed_path, records, limit):
    cases = read_rows(root / "processed/cases.jsonl", AIWorldCase)
    approved = {source_id(c.original_post_url) for c in cases if c.review_status == ReviewStatus.APPROVED}
    signals = {p.stem:read_json(p) for p in (root / "raw/x/signals").glob("*.json")}
    media = load_media_evidence(root, signals)
    keys = {key:record_keys(post, media) for key,post in records.items()}
    policy = load_policy(root)
    config = (yaml.safe_load(seed_path.read_text()) or {}) if seed_path.is_file() else {}
    excluded = {h.casefold() for h in config.get("excluded_aggregator_accounts", ())}
    choices = []
    for case in cases:
        if case.source_kind != "x_post" or case.review_status != ReviewStatus.PENDING or not case.possible_duplicate_urls:
            continue
        first = source_id(case.original_post_url)
        original = records.get(first)
        if not original or (case.author_handle or "").casefold() != original.post.author_handle.casefold():
            continue
        allowed = apply_attribution(case.model_copy(deep=True),root,policy) == "allow"
        texts = [original.post.text, *(post.text for post in original.thread)]
        literal = any(OWN_BUILD.search(QUOTED.sub("", t)) or CREATOR_ACTION.search(QUOTED.sub("", t)) for t in texts)
        if not (allowed or literal):
            continue
        for link in case.possible_duplicate_urls:
            second = source_id(link)
            later = records.get(second)
            if not later or second in approved or original.post.author_handle.casefold() == later.post.author_handle.casefold():
                continue
            shared = definite_asset(keys[first]) & definite_asset(keys[second])
            when, after = original.post.published_at, later.post.published_at
            if not shared or not when or not after or not when.tzinfo or not after.tzinfo or when >= after:
                continue
            # For ranking only. Publication always verifies both actual source pages separately.
            supported = attributed_repost(original,later,keys[first],keys[second],signals.get(second,{}),excluded,
                                           ("unverified_for_ranking",""))
            choices.append({"original":first,"reporter":second,"creator":original.post.author_handle,
                            "reporter_handle":later.post.author_handle,"original_url":case.original_post_url,
                            "report_url":later.original_url,"shared":sorted(shared),
                            "independent_author_allow":allowed,"satisfies_remaining_policy_checks":bool(supported)})
    choices.sort(key=lambda p:(not p["independent_author_allow"], not p["satisfies_remaining_policy_checks"],
                               -len(p["shared"]),int(p["original"]),int(p["reporter"])))
    return choices[:limit]


def fetch(client, folder, post, provider, retry):
    path = folder / post.post.tweet_id / f"{provider}.json"
    if path.exists():
        cached = read_json(path)
        if not retry or cached["result"] not in TRANSIENT:
            return cached["result"]
        previous = path.with_name(f"{provider}.first-attempt.json")
        if not previous.is_file():
            write_json(previous,cached)
    identifier = post.post.tweet_id
    url = {"page": post.original_url,
           "syndication": "https://cdn.syndication.twimg.com/tweet-result?"+urlencode({"id":identifier,"lang":"en"}),
           "embed": "https://publish.x.com/oembed?"+urlencode({"url":post.original_url,"omit_script":"1"})}[provider]
    rec = {"post_id":identifier,"provider":provider,"request_url":url,"checked_at":datetime.now(UTC).isoformat()}
    try:
        with client.stream("GET",url) as response:
            rec["status"] = response.status_code
            if response.is_redirect:
                rec.update(result="redirect",location=response.headers.get("location",""))
            else:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body)>4_000_000:
                        raise ValueError("Public response exceeds four megabytes")
                path.parent.mkdir(parents=True,exist_ok=True)
                target = path.with_name(f"{provider}.body.gz")
                with NamedTemporaryFile(dir=path.parent,delete=False) as out:
                    out.write(gzip.compress(body,mtime=0))
                Path(out.name).replace(target)
                rec.update(body_file=target.name,sha256=sha256(body).hexdigest(), result=f"http_{response.status_code}")
                if response.status_code == 200 and provider != "page":
                    payload = json.loads(body)
                    if provider == "syndication":
                        returned = str(payload.get("id_str") or payload.get("id") or "")
                        rec.update(returned_id=returned, returned_author=(payload.get("user") or {}).get("screen_name"),
                                   result="identified" if returned==identifier else "anonymous_payload")
                    else:
                        rec.update(returned_canonical=payload.get("url"),returned_author_url=payload.get("author_url"),
                                   result="oembed_response")
    except (httpx.HTTPError,ValueError) as error:
        rec["result"] = type(error).__name__
    write_json(path,rec)
    return rec["result"]


def capture(root, seeds, limit, retry):
    folder = root / "raw/x/public_media_origin"
    records = {row.post.tweet_id:row for path in (root / "raw/x").glob("*.json")
               if (row:=RawTweetRecord.model_validate_json(path.read_bytes()))}
    with run_lock(folder):
        sample = folder / "sample.json"
        if not sample.exists():
            write_json(sample,{"rank":"validated creator receipt, remaining policy checks, shared identifiers, ascending status IDs",
                               "pairs":select_pairs(root,seeds,records,limit)})
        pairs = read_json(sample)["pairs"][:limit]
        ids = list(dict.fromkeys(p[k] for p in pairs for k in ("original","reporter")))
        summary = {"pairs":len(pairs),"distinct_posts":len(ids)}
        with httpx.Client(timeout=httpx.Timeout(12,connect=6),follow_redirects=False,
                          headers={"User-Agent":"Mozilla/5.0 (compatible; AIWorldsCatalog/1.0)"}) as client, ThreadPoolExecutor(max_workers=8) as pool:
            for kind in ("page","syndication","embed"):
                def load(i):
                    return fetch(client,folder,records[i],kind,retry)
                counts = Counter(pool.map(load,ids[:4]))
                if any(k in counts for k in ("http_200","identified","oembed_response")):
                    counts.update(pool.map(load,ids[4:]))
                summary[kind] = dict(counts)
        verified = cached_native_entities(root,records)
        for i, receipt in verified.items():
            write_json(folder / i / "verified-native-entity.json",receipt)
        selected = {(p["original"],p["reporter"]) for p in pairs}
        summary.update(exact_native_entities=len(verified),native_source_pairs=len(selected & origins(verified).keys()))
        write_json(folder / "summary.json",summary)
        return summary


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,default=Path("data"))
    parser.add_argument("--seeds",type=Path,default=Path("config/seeds.yaml"))
    parser.add_argument("--max-pairs",type=int,default=120)
    parser.add_argument("--retry-timeouts",action="store_true",help="Retry a transient response once during this invocation.")
    args=parser.parse_args()
    if not 1 <= args.max_pairs <= 120:
        parser.error("--max-pairs must be from 1 to 120 for this capture")
    print(json.dumps(capture(args.data_dir,args.seeds,args.max_pairs,args.retry_timeouts),sort_keys=True))
