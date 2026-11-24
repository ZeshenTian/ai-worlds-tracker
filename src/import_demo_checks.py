"""Apply newer browser-check artifacts to matching works and rebuild the public snapshot."""
import argparse
from datetime import datetime
from pathlib import Path
import re
from shutil import copyfile
from tempfile import NamedTemporaryFile

from PIL import Image

from .models import AIWorldCase, DemoHealth
from .publish_catalog import PROJECT, publish
from .storage import read_json, read_rows, run_lock, write_json


def merge_checks(root, platform, directories, *, auto=False):
    thumbnails = platform / "public/thumbnails"
    thumbnails.mkdir(parents=True, exist_ok=True)
    path = root / "state/demo_health.json"
    applied = 0
    with run_lock(root), run_lock(path.parent / ".demo-verifier"):
        state = read_json(path) if path.exists() else {}
        works = {c.world_id:c.live_demo_url for c in read_rows(root / "processed/cases.jsonl", AIWorldCase)}
        for directory in directories:
            for key, check in read_json(directory / "health.json").items():
                if not re.fullmatch(r"world-[a-f0-9]{24}", key) or not works.get(key) or works[key] != check.get("live_demo_url"):
                    continue
                old = state.get(key, {})
                if old.get("checked_at") and datetime.fromisoformat(old["checked_at"]) >= datetime.fromisoformat(check["checked_at"]):
                    continue
                DemoHealth(check["demo_health_status"])
                target = thumbnails / (key + ".webp")
                if check.get("thumbnail_url"):
                    if check["thumbnail_url"] != "/thumbnails/" + target.name:
                        raise ValueError("Invalid artifact thumbnail")
                    source = directory / "thumbnails" / target.name
                    with Image.open(source) as preview:
                        if preview.format != "WEBP":
                            raise ValueError("Invalid preview format")
                        preview.verify()
                    with NamedTemporaryFile(dir=thumbnails, delete=False) as f:
                        tmp = Path(f.name)
                    try:
                        copyfile(source,tmp)
                        tmp.replace(target)
                    finally:
                        tmp.unlink(missing_ok=True)
                elif (old.get("live_demo_url") == works[key] and old.get("thumbnail_url") and target.is_file()
                      and check["demo_health_status"] == "unverified"
                      and any(t in check.get("evidence","") for t in ("超时","浏览器未完成加载","浏览器访问检查","HTTP 5"))):
                    check["thumbnail_url"] = old["thumbnail_url"]
                    check["thumbnail_checked_at"] = old.get("thumbnail_checked_at") or old.get("checked_at")
                state[key] = check
                applied += 1
        write_json(path,state)
        publish(root,platform,auto=auto)
    return applied


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("directories", type=Path, nargs="+", help="Extracted demo-check artifact directories")
    p.add_argument("--auto", action="store_true", help="Apply the configured evidence-based approval rules")
    args=p.parse_args()
    print(f"{merge_checks(PROJECT/'data', PROJECT/'platform', args.directories, auto=args.auto)} newer checks applied")
