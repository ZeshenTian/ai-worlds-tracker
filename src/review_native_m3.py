"""Independently review original X frames for evidence-bearing pending frontier cases."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
import os
from pathlib import Path
import re
import time

from openai import APIError, OpenAI
from PIL import Image
import yaml

from .frontier_review import assess, evaluate_rows
from .models import AIWorldCase, ReviewStatus
from .publish_catalog import publish
from .qualify_candidates import record_usage
from .recheck_attribution import evidence, load_policy, in_scope
from .recheck_creator_role import RULES, Resolutions, prior_counterquotes
from .storage import digest, encode, read_json, read_rows, run_lock, write_json


def image_url(path):
    with Image.open(path) as frame:
        frame.thumbnail((512, 512))
        output = BytesIO()
        frame.convert("RGB").save(output, format="JPEG", quality=84)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()


def review(root, platform, config, baseline_ids):
    rows = read_rows(root / "processed/cases.jsonl", AIWorldCase)
    policy = load_policy(root)
    covers = read_json(root / "state/x_covers.json")
    stored = root / "state/frontier_native_reviews.json"
    receipts = read_json(stored) if stored.exists() else {}
    excluded = {h.casefold() for h in config.get("excluded_aggregator_accounts", [])}
    watched = {h.casefold() for h in config.get("watch_accounts", [])}
    jobs = []
    for case in rows:
        if (
            case.world_id in baseline_ids
            or case.review_status != ReviewStatus.PENDING
            or case.model_era != "frontier"
            or case.possible_duplicate_urls
            or not in_scope(case, policy)
        ):
            continue
        tid = case.original_post_url.rsplit("/", 1)[-1]
        source_file = root / "raw/x/signals" / (tid + ".json")
        signal = read_json(source_file) if source_file.is_file() else {}
        if (
            case.author_handle.casefold() not in watched
            and int(signal.get("likes") or 0) < 15
        ):
            continue
        packet = evidence(root, case)
        prior = policy["decisions"].get(case.world_id, {})
        if not packet or not packet["has_attached_media"] or prior_counterquotes(prior):
            continue
        screening = assess(case, packet, signal, prior, excluded)
        if screening["reason"] not in {
            "work_or_presentation_unclear",
            "missing_model_disclosure",
            "native_creator_presentation",
            "official_first_party",
        }:
            continue
        cover = covers.get(case.world_id, {})
        fname = case.world_id + "-x.webp"
        path = platform / "public/thumbnails" / fname
        if (
            not path.is_file()
            or cover.get("source_url") != case.original_post_url
            or cover.get("thumbnail_url") != "/thumbnails/" + fname
            or not cover.get("source_sha256")
        ):
            continue
        provenance = dict(
            source=case.original_post_url,
            provider_model="MiniMax-M3",
            rules=digest(RULES),
            packet_key=digest(encode(packet)),
            source_sha256=cover["source_sha256"],
        )
        if all(
            receipts.get(case.world_id, {}).get(k) == v for k, v in provenance.items()
        ):
            continue
        jobs.append((case.world_id, packet, path, provenance))
    print(f"Independent native frame reviews scheduled: {len(jobs)}", flush=True)
    if jobs:
        client = OpenAI(
            api_key=os.environ["MINIMAX_API_KEY"],
            base_url="https://api.minimax.cn/v1",
            timeout=110,
            max_retries=1,
        )
        instructions = (
            RULES
            + "\nEach numbered packet is immediately followed by its actual native image. Return only JSON matching this schema. Use short, literal quotes and a one-sentence observation. "
            + encode(Resolutions.model_json_schema())
        )

        def check(batch):
            content = []
            for index, (_, packet, path, _) in enumerate(batch, 1):
                content.extend(
                    [
                        {
                            "type": "text",
                            "text": encode({"index": index, "original": packet}),
                        },
                        {"type": "image_url", "image_url": {"url": image_url(path)}},
                    ]
                )
            for attempt in range(3):
                try:
                    response = client.chat.completions.create(
                        model="MiniMax-M3",
                        max_tokens=3400,
                        extra_body={"thinking": {"type": "disabled"}},
                        messages=[
                            {"role": "system", "content": instructions},
                            {"role": "user", "content": content},
                        ],
                    )
                    record_usage(
                        root, "MiniMax-M3", "native_frame_attribution", response
                    )
                    choice = response.choices[0]
                    if choice.finish_reason != "stop":
                        raise ValueError("Incomplete visual response")
                    raw = re.sub(
                        r"^\s*```(?:json)?\s*|\s*```\s*$",
                        "",
                        choice.message.content or "",
                    )
                    responses = Resolutions.model_validate(json.loads(raw)).items
                    by_index = {item.index: item for item in responses}
                    if len(responses) != len(batch) or set(by_index) != set(
                        range(1, len(batch) + 1)
                    ):
                        raise ValueError("Missing or duplicated visual decision")
                    return {
                        key: {**provenance, "resolution": by_index[index].model_dump()}
                        for index, (key, _, _, provenance) in enumerate(batch, 1)
                    }
                except (APIError, ValueError) as err:
                    if attempt == 2:
                        print(
                            "Deferred native review batch",
                            len(batch),
                            type(err).__name__,
                            flush=True,
                        )
                        return {}
                    time.sleep(6 * (attempt + 1))

        batches = [jobs[i : i + 3] for i in range(0, len(jobs), 3)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            for result in pool.map(check, batches):
                if result:
                    receipts.update(result)
                    write_json(stored, receipts)
    with run_lock(root):
        rows = read_rows(root / "processed/cases.jsonl", AIWorldCase)
        evaluate_rows(root, rows, load_policy(root), config)
        publish(root, platform, auto=True)
    print(f"Stored {len(receipts)} native frame reviews", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-ledger",
        type=Path,
        required=True,
        help="Limit to cases added since this frozen ledger",
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--platform", type=Path, default=Path("platform"))
    parser.add_argument("--seeds", type=Path, default=Path("config/seeds.yaml"))
    args = parser.parse_args()
    with args.baseline_ledger.open() as stream:
        baseline = {json.loads(line)["world_id"] for line in stream if line.strip()}
    review(
        args.data_dir, args.platform, yaml.safe_load(args.seeds.read_text()), baseline
    )
