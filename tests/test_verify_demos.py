import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO

from PIL import Image
import pytest

from src import verify_demos as demos


@pytest.mark.parametrize("address", [
    "127.0.0.1", "169.254.169.254", "10.0.0.1", "192.168.1.2", "100.64.0.1",
    "224.0.0.1", "::1", "::ffff:127.0.0.1", "64:ff9b::7f00:1", "2002:7f00:1::",
])
def test_private_and_transition_addresses_are_blocked(address):
    assert not demos.allowed_address(address)


def test_mixed_dns_answer_is_rejected(monkeypatch):
    connections = demos.PublicConnections()
    connections.proxy = True
    monkeypatch.setattr(connections, "public_dns", lambda _: ["8.8.8.8", "127.0.0.1"])
    with pytest.raises(ValueError, match="non-public"):
        asyncio.run(connections.resolve("author.example.com"))


@pytest.mark.parametrize(("status", "path", "title", "body", "expected"), [
    (404, "/", "", "", "broken"),
    (410, "/", "", "", "broken"),
    (503, "/", "", "", "unverified"),
    (200, "/sign-in", "", "", "login_required"),
    (200, "/", "", "Sign in to access this experience.", "login_required"),
    (403, "/", "Security Checkpoint", "", "unverified"),
    (200, "/", "Just a moment", "", "unverified"),
    (200, "/", "A live world", "Explore our playground. Sign in for extras.", None),
])
def test_navigation_status(status, path, title, body, expected):
    result = demos.page_gate(status, "https://author.example.com" + path, title, body)
    assert (result[0] if result else None) == expected


def test_ambient_animation_does_not_verify_interaction():
    assert not demos.responded(4, 5)
    assert not demos.responded(0, 1)
    assert demos.responded(0.5, 5)


def test_preview_is_useful_webp(tmp_path):
    output = tmp_path / "case.webp"
    frame = Image.new("RGB", (1152, 648), "white")
    blank = BytesIO()
    frame.save(blank, "PNG")
    assert not demos.write_preview(blank.getvalue(), output)
    assert not output.exists()
    patterned = Image.linear_gradient("L").resize(frame.size)
    data = BytesIO()
    patterned.save(data, "PNG")
    assert demos.write_preview(data.getvalue(), output)
    with Image.open(output) as image:
        assert image.format == "WEBP"
        assert image.size == (1152, 648)


def test_cache_requires_same_url_fresh_time_and_existing_preview(tmp_path):
    url = "https://author.example.com/scene"
    thumbnail = tmp_path / "world.webp"
    ttl = timedelta(hours=24)
    now = datetime.now(timezone.utc)
    record = dict(check_version=demos.CHECK_VERSION, checked_at=now.isoformat(), live_demo_url=url,
                  demo_health_status="verified_playable", thumbnail_url="/thumbnails/world.webp")
    assert not demos.fresh(record, url, thumbnail, ttl)
    thumbnail.touch()
    assert demos.fresh(record, url, thumbnail, ttl)
    assert not demos.fresh(record, url + "2", thumbnail, ttl)
    record["checked_at"] = (now - timedelta(days=2)).isoformat()
    assert not demos.fresh(record, url, thumbnail, ttl)


def test_batch_preserves_cache_and_does_not_visit_social_links(tmp_path, monkeypatch):
    state = tmp_path / "data" / "demo_health.json"
    thumbnails = tmp_path / "thumbnails"
    visited = []

    @asynccontextmanager
    async def fake_browser(channel):
        yield None

    async def inspect(browser, url, output):
        visited.append(url)
        return "unverified", "interaction was inconclusive", None

    monkeypatch.setattr(demos, "isolated_browser", fake_browser)
    monkeypatch.setattr(demos, "inspect_page", inspect)
    rows = [{"world_id": "empty", "live_demo_url": None},
            {"world_id": "social", "live_demo_url": "https://x.com/original"},
            {"world_id": "scene", "live_demo_url": "https://studio.example.com/world"}]
    results = asyncio.run(demos.verify(rows, state, thumbnails))
    assert [results[row["world_id"]]["demo_health_status"] for row in rows] == ["no_demo", "unverified", "unverified"]
    assert demos.read_json(state) == results
    assert asyncio.run(demos.verify(rows, state, thumbnails)) == results
    assert visited == ["https://studio.example.com/world"]


def test_transient_failure_preserves_previous_preview_for_same_url(tmp_path, monkeypatch):
    state = tmp_path / "demo_health.json"
    thumbnails = tmp_path / "thumbnails"
    thumbnails.mkdir()
    url = "https://studio.example.com/slow-world"
    previous = "2026-01-01T00:00:00+00:00"
    demos.write_json(state, {"world": {"live_demo_url": url, "checked_at": previous,
                                     "thumbnail_url": "/thumbnails/world.webp"}})
    (thumbnails / "world.webp").touch()

    @asynccontextmanager
    async def fake_browser(channel):
        yield None

    async def slow(browser, link, output):
        raise TimeoutError()

    monkeypatch.setattr(demos, "isolated_browser", fake_browser)
    monkeypatch.setattr(demos, "inspect_page", slow)
    rows = [{"world_id": "world", "live_demo_url": url}]
    record = asyncio.run(demos.verify(rows, state, thumbnails))["world"]
    assert record["demo_health_status"] == "unverified"
    assert record["thumbnail_checked_at"] == previous
    assert (thumbnails / "world.webp").is_file()
    rows[0]["live_demo_url"] += "-moved"
    record = asyncio.run(demos.verify(rows, state, thumbnails))["world"]
    assert record["thumbnail_url"] is None
    assert not (thumbnails / "world.webp").exists()


def test_overlapping_runs_share_state_without_launching_browser_for_empty_demos(tmp_path):
    async def run():
        state = tmp_path / "state.json"
        thumbnails = tmp_path / "thumbnails"
        await asyncio.gather(*(demos.verify([{"world_id": key, "live_demo_url": None}], state, thumbnails)
                               for key in ("first", "second")))
        assert set(demos.read_json(state)) == {"first", "second"}
    asyncio.run(run())
