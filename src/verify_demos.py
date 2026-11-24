"""Check public demos in fresh Chromium contexts and publish original 16:9 previews."""
import argparse
import asyncio
import base64
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from io import BytesIO
import ipaddress
import json
from pathlib import Path
import re
import socket
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode, urlsplit
from urllib.request import getproxies, urlopen

from PIL import Image, ImageChops, ImageStat
from playwright.async_api import Error as BrowserError, async_playwright

from .links import SOCIAL_DOMAINS, external_url, host_is
from .storage import read_json, run_lock, write_json

VIEWPORT = {"width": 1152, "height": 648}
CHECK_VERSION = 2
STATUSES = {"verified_playable", "login_required", "broken", "no_demo", "unverified"}


def allowed_address(addr: str) -> bool:
    ip = ipaddress.ip_address(addr.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip.sixtofour or ip.teredo or ip in ipaddress.ip_network("64:ff9b::/96"):
            return False
    return ip.is_global and not ip.is_multicast


class PublicConnections:
    def __init__(self):
        configured = getproxies().get("https") or getproxies().get("http")
        self.proxy = urlsplit(configured) if configured else None
        self.lookups = {}

    @staticmethod
    def public_dns(host):
        # On managed hosts the DNS resolver can be reachable only through the system proxy.
        query = urlencode({"name": host, "type": "A"})
        with urlopen("https://dns.google/resolve?" + query, timeout=7) as response:
            result = json.load(response)
        return [entry["data"] for entry in result.get("Answer", []) if entry["type"] == 1]

    async def resolve(self, host):
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            if self.proxy:
                addresses = await asyncio.to_thread(self.public_dns, host)
            else:
                infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
                addresses = [info[4][0] for info in infos]
        else:
            addresses = [str(ip)]
        if not addresses or not all(allowed_address(address) for address in addresses):
            raise ValueError("non-public destination")
        return list(dict.fromkeys(addresses))

    async def connect(self, host, port):
        host = host.lower().rstrip(".")
        if port not in (80, 443) or not external_url(f"https://{host}/") or host_is(host, SOCIAL_DOMAINS):
            raise ValueError("destination prohibited")
        if host not in self.lookups:
            self.lookups[host] = asyncio.create_task(self.resolve(host))
        task = self.lookups[host]
        try:
            addresses = await asyncio.shield(task)
        except OSError:
            if self.lookups.get(host) is task:
                self.lookups.pop(host)
            raise
        for address in addresses:
            try:
                async with asyncio.timeout(6):
                    if not self.proxy:
                        return await asyncio.open_connection(address, port)
                    if self.proxy.scheme != "http" or not self.proxy.hostname:
                        raise ValueError("expected an HTTP CONNECT proxy")
                    reader, writer = await asyncio.open_connection(self.proxy.hostname, self.proxy.port or 80)
                    literal = f"[{address}]" if ":" in address else address
                    destination = f"{literal}:{port}"
                    try:
                        writer.write(f"CONNECT {destination} HTTP/1.1\r\nHost: {destination}\r\n\r\n".encode("ascii"))
                        await writer.drain()
                        headers = await reader.readuntil(b"\r\n\r\n")
                        if headers.split(b" ", 2)[1] != b"200":
                            raise OSError("proxy tunnel unavailable")
                        return reader, writer
                    except BaseException:
                        writer.close()
                        raise
            except OSError:
                continue
        raise OSError("unable to connect")


async def relay(reader, writer):
    while chunk := await reader.read(65536):
        writer.write(chunk)
        await writer.drain()


async def proxy_client(reader, writer, connections):
    """Minimal loopback SOCKS5 CONNECT endpoint for the untrusted-site browser."""
    upstream = None
    transfers = []
    try:
        async with asyncio.timeout(18):
            version, count = await reader.readexactly(2)
            if version != 5 or 0 not in await reader.readexactly(count):
                return
            writer.write(b"\x05\x00")
            await writer.drain()
            version, command, reserved, kind = await reader.readexactly(4)
            if (version, command, reserved) != (5, 1, 0):
                return
            if kind == 3:
                length = (await reader.readexactly(1))[0]
                host = (await reader.readexactly(length)).decode("ascii")
            elif kind in (1, 4):
                host = str(ipaddress.ip_address(await reader.readexactly(4 if kind == 1 else 16)))
            else:
                return
            port = int.from_bytes(await reader.readexactly(2), "big")
            remote_reader, upstream = await connections.connect(host, port)
            writer.write(b"\x05\x00\x00\x01" + bytes(6))
            await writer.drain()
        transfers = [asyncio.create_task(relay(reader, upstream)), asyncio.create_task(relay(remote_reader, writer))]
        await asyncio.wait(transfers, return_when=asyncio.FIRST_COMPLETED)
    except (OSError, ValueError, asyncio.IncompleteReadError):
        if upstream is None:
            writer.write(b"\x05\x02\x00\x01" + bytes(6))
    finally:
        for transfer in transfers:
            transfer.cancel()
        await asyncio.gather(*transfers, return_exceptions=True)
        if upstream is not None:
            upstream.close()
        writer.close()


@asynccontextmanager
async def isolated_browser(channel: str | None):
    connections = PublicConnections()

    async def accept(reader, writer):
        await proxy_client(reader, writer, connections)

    async with await asyncio.start_server(accept, "127.0.0.1", 0) as proxy:
        port = proxy.sockets[0].getsockname()[1]
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                channel=channel,
                chromium_sandbox=True,
                proxy={"server": f"socks5://127.0.0.1:{port}", "bypass": "<-loopback>"},
                args=["--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                      "--enable-unsafe-swiftshader"],
            )
            try:
                yield browser
            finally:
                await browser.close()


async def guard_route(route):
    request = route.request
    if request.method in {"GET", "HEAD", "OPTIONS"} and external_url(request.url):
        await route.continue_()
    else:
        await route.abort()


def page_gate(status: int | None, url: str, title: str, body: str) -> tuple[str, str] | None:
    if (urlsplit(url).path in {"", "/"} and
            re.fullmatch(r"(?:model tests|project directory|showcase directory)", title.strip(), re.I)):
        return "unverified", "链接打开作品目录首页，尚未定位到该案例的独立场景"
    if status in (404, 410):
        return "broken", f"HTTP {status}"
    if status == 401 or re.search(r"/(?:login|log-in|signin|sign-in|ServiceLogin)(?:/|$)", urlsplit(url).path, re.I):
        return "login_required", "页面要求登录"
    if status and status >= 400:
        return "unverified", f"本次访问返回 HTTP {status}"
    if re.search(r"just a moment|verify (?:that )?you are human|security checkpoint|checking your browser", title + "\n" + body[:500], re.I):
        return "unverified", "浏览器访问检查阻止了验证"
    if re.search(r"(?:sign in|log in) to (?:access|view|continue|play|use this)|请先登录|登录后才可", body[:800], re.I):
        return "login_required", "页面提示需登录后访问"
    if re.search(r"404.{0,8}(?:not found|page)|deployment (?:was )?not found|there isn.t a github pages site here", (title + "\n" + body[:500]).lower()):
        return "broken", "页面显示资源不存在"
    return None


def normalized(image: bytes):
    return Image.open(BytesIO(image)).convert("RGB").resize((96, 54))


def change(a: Image.Image, b: Image.Image) -> float:
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def responded(idle: float, gesture: float) -> bool:
    return gesture >= max(2.5, 2.2 * idle + .8)


async def find_scene(page):
    best = None
    best_area = 0
    for frame in page.frames:
        candidates = frame.locator('canvas, model-viewer, svg[role="application"]')
        for index in range(min(8, await candidates.count())):
            item = candidates.nth(index)
            rect = await item.bounding_box(timeout=800)
            if not rect or rect["width"] < 220 or rect["height"] < 140:
                continue
            x = max(0, int(rect["x"]))
            y = max(0, int(rect["y"]))
            width = min(VIEWPORT["width"], int(rect["x"] + rect["width"])) - x
            height = min(VIEWPORT["height"], int(rect["y"] + rect["height"])) - y
            if width < 220 or height < 140 or width * height <= best_area:
                continue
            # Try multiple points, since interface panels often cover the canvas center.
            point = await item.evaluate("""e => {
              const r = e.getBoundingClientRect(), left = Math.max(0, r.left), top = Math.max(0, r.top);
              const w = Math.min(innerWidth, r.right) - left, h = Math.min(innerHeight, r.bottom) - top;
              for (const [u,v] of [[.5,.54],[.7,.55],[.35,.45],[.7,.75],[.3,.7]]) {
                const px = left+w*u, py = top+h*v, hit = document.elementFromPoint(px,py);
                if (hit === e || e.contains(hit)) return [px-r.left,py-r.top];
              }
              return null;
            }""")
            if point:
                best = ({"x": x, "y": y, "width": width, "height": height},
                        (rect["x"] + point[0], rect["y"] + point[1]))
                best_area = width * height
    return best


async def start_scene(page):
    # Restrict activation to explicit game start controls, excluding links and form submissions.
    label = re.compile(r"^(?:(?:start|play|begin|enter|launch|embark)(?: (?:the|a|new|game|now|run|world|adventure|simulation|expedition|exploring|experience|journey|mission|flight|dive|tour|with|without|sound)){0,4}|set forth|开始(?:游戏|探索|骑行|飞行)?|进入世界)[!！→\s]*$", re.I)
    for frame in page.frames:
        candidates = frame.get_by_role("button", name=label)
        for index in range(min(3, await candidates.count())):
            button = candidates.nth(index)
            if await button.is_visible() and await button.is_enabled() and await button.evaluate("e => !e.closest('form,a')"):
                try:
                    await button.click(timeout=1200)
                    return button
                except BrowserError:
                    continue
    return None


async def capture(session, clip=None):
    # Chromium captures the already rendered viewport even if third-party fonts are still downloading.
    params = {"format": "png", "captureBeyondViewport": False}
    if clip:
        params["clip"] = {**clip, "scale": 1}
    result = await session.send("Page.captureScreenshot", params)
    return base64.b64decode(result["data"])


async def scene_interaction(page, session, scene):
    clip, (x, y) = scene
    async def snapshot():
        return normalized(await capture(session, clip))
    await page.mouse.move(x, y)
    first = await snapshot()
    await page.wait_for_timeout(400)
    second = await snapshot()
    idle = change(first, second)
    await page.mouse.down()
    try:
        await page.mouse.move(min(clip["x"] + clip["width"] - 1, x + clip["width"] * .23), y - clip["height"] * .05, steps=8)
    finally:
        await page.mouse.up()
    await page.wait_for_timeout(220)
    moved = await snapshot()
    gesture = change(second, moved)
    # Compare a second idle interval after input to avoid mistaking continuing animation for interaction.
    await page.wait_for_timeout(400)
    still = await snapshot()
    idle = max(idle, change(moved, still))
    if responded(idle, gesture):
        return True, f"画布拖动差值 {gesture:.1f}，空闲画面差值 {idle:.1f}"

    # A named scene control may work even when the camera does not respond to a drag.
    controls = re.compile(r"^(?:x-ray|wireframe|exploded view|cutaway|cross.section|night|top view|side view)$", re.I)
    for frame in page.frames:
        button = frame.get_by_role("button", name=controls).first
        if await button.count() and await button.is_visible() and await button.evaluate("e => !e.closest('a,form')"):
            label = (await button.inner_text())[:35]
            try:
                await button.click(timeout=1100)
            except BrowserError:
                continue
            await page.wait_for_timeout(550)
            after = await snapshot()
            diff = change(still, after)
            if responded(idle, diff):
                return True, f"场景控件「{label}」切换后画面差值 {diff:.1f}，空闲差值 {idle:.1f}"
            break
    # The change in a native range input alone is insufficient. Check the rendered scene as well.
    for frame in page.frames:
        sliders = frame.locator('input[type="range"]:visible:not(:disabled)')
        for index in range(min(5, await sliders.count())):
            slider = sliders.nth(index)
            name = await slider.evaluate("""e => e.closest('form') ? '' :
                (e.ariaLabel || e.title || [...e.labels].map(el=>el.textContent).join(' '))""")
            if not re.search(r"year|time of day|zoom|explode|pull.+apart|light|orbit|angle|speed|gravity", name or "", re.I):
                continue
            previous = await slider.input_value()
            before = await snapshot()
            await slider.press("End" if previous != await slider.get_attribute("max") else "Home", timeout=1500)
            if previous == await slider.input_value():
                continue
            await page.wait_for_timeout(600)
            diff = change(before, await snapshot())
            if responded(idle, diff):
                return True, f"调整场景参数「{name[:35]}」后画面差值 {diff:.1f}，空闲差值 {idle:.1f}"
            break
    hint = await page.locator("body").inner_text(timeout=1200)
    if re.search(r"\bWASD\b|W/S/A/D|W、A、S、D", hint, re.I):
        safe_focus = await page.evaluate("!document.activeElement?.closest('input,textarea,[contenteditable=true]')")
        if safe_focus:
            first = await snapshot()
            await page.wait_for_timeout(950)
            before = await snapshot()
            await page.keyboard.down("w")
            try:
                await page.wait_for_timeout(900)
            finally:
                await page.keyboard.up("w")
            motion = change(before, await snapshot())
            idle = max(idle, change(first, before))
            if responded(idle, motion):
                return True, f"按页面说明前进后画面差值 {motion:.1f}，空闲差值 {idle:.1f}"
    return False, f"画布拖动差值 {gesture:.1f}，空闲画面差值 {idle:.1f}"


def detailed_preview(encoded):
    # A landing screen may be usable as a cover even when its particular controls are unknown.
    # Distribute the detail check across the frame to rule out a spinner, title or skeleton.
    image = Image.open(BytesIO(encoded)).convert("L").resize((192, 120))
    textured = 0
    for x in range(0, 192, 24):
        for y in range(0, 120, 20):
            tile = image.crop((x, y, x + 24, y + 20))
            if ImageStat.Stat(tile).stddev[0] > 13 and tile.entropy() > 3.4:
                textured += 1
    return textured >= 16


def write_preview(encoded: bytes, output: Path) -> bool:
    image = Image.open(BytesIO(encoded)).convert("RGB")
    sample = image.resize((72, 40))
    # Reject blank, uniform backgrounds and tiny centered spinners.
    if max(ImageStat.Stat(sample).stddev) < 13 or sample.entropy() < 2.5:
        return False
    with NamedTemporaryFile(dir=output.parent, suffix=".webp", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        image.save(temp_path, "WEBP", quality=77)
        temp_path.replace(output)
    finally:
        temp_path.unlink(missing_ok=True)
    return True


async def loading_screen(page):
    for frame in page.frames:
        pending = await frame.evaluate(r"""() => {
          const body = document.body;
          if (!body) return false;
          const text = body.innerText || '';
          if (/built with[\s\S]{0,80}\b0\s*%/i.test(text)) return true;
          let node = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
          while (node && node !== body) {
            const words = (node.innerText || '').trim();
            if (words.length < 120 && /^(?:loading|downloading|initializing|preparing|加载中)\b/i.test(words)) return true;
            node = node.parentElement;
          }
          return false;
        }""")
        if pending:
            return True
    return False


async def inspect_page(browser, url: str, output: Path) -> tuple[str, str, str | None]:
    context = await browser.new_context(viewport=VIEWPORT, device_scale_factor=1, service_workers="block",
                                        accept_downloads=False)
    try:
        await context.route("**/*", guard_route)
        await context.route_web_socket("**/*", lambda ws: ws.close())
        page = await context.new_page()
        session = await context.new_cdp_session(page)
        response = await page.goto(url, wait_until="commit", timeout=22000)
        start_button = None
        deadline = asyncio.get_running_loop().time() + 45
        evidence = "等待渲染后仍未发现已显示且可操作的场景"
        while asyncio.get_running_loop().time() < deadline:
            await page.wait_for_timeout(1800)
            try:
                body = await page.evaluate("document.body?.innerText?.slice(0,5000) || ''")
                gate = page_gate(response.status if response else None, page.url, await page.title(), body)
                if gate:
                    return *gate, None
                if start_button is None:
                    start_button = await start_scene(page)
                    if start_button is not None:
                        continue
                scene = await find_scene(page)
                if not scene or await loading_screen(page):
                    continue
                frame = await capture(session)
                scene_image = normalized(await capture(session, scene[0]))
                if max(ImageStat.Stat(scene_image).stddev) < 9:
                    continue
                if write_preview(frame, output):
                    thumbnail = f"/thumbnails/{output.name}"
                    confirmed, evidence = await scene_interaction(page, session, scene)
                    if not confirmed and start_button is not None and not await start_button.is_visible():
                        first = normalized(await capture(session, scene[0]))
                        await page.wait_for_timeout(600)
                        diff = change(first, normalized(await capture(session, scene[0])))
                        if diff > 2 and detailed_preview(frame):
                            return "verified_playable", f"启动试玩后渲染场景持续运行，帧差值 {diff:.1f}", thumbnail
                    return "verified_playable" if confirmed else "unverified", evidence, thumbnail
            except BrowserError as error:
                # A SPA can replace the document or attach/detach its iframe during startup.
                if not any(word in str(error).lower() for word in ("detached", "destroyed", "navigation", "timeout")):
                    raise
        if await loading_screen(page):
            return "unverified", "首屏仍显示加载进度，等待复验", None
        frame = await capture(session)
        for child in page.frames[1:]:
            element = await child.frame_element()
            box = await element.bounding_box()
            if not box or box["width"] * box["height"] < 160000 or not await element.is_visible():
                continue
            text = await child.evaluate("document.body?.innerText?.trim().slice(0, 180) || ''")
            if len(text) < 12 or re.match(r"^(?:loading|preparing|initializing|just a moment|加载中)", text, re.I):
                return "unverified", "内嵌试玩尚未渲染出可用的场景", None
        if detailed_preview(frame) and write_preview(frame, output):
            return "unverified", evidence, f"/thumbnails/{output.name}"
        return "unverified", evidence, None
    finally:
        await context.close()


def fresh(record: dict, url: str | None, thumbnail: Path, ttl: timedelta) -> bool:
    if record.get("check_version") != CHECK_VERSION or record.get("live_demo_url") != url:
        return False
    if record.get("demo_health_status") not in STATUSES or (record.get("thumbnail_url") and not thumbnail.exists()):
        return False
    try:
        return timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(record["checked_at"]) < ttl
    except (KeyError, TypeError, ValueError):
        return False


async def verify(rows, state_path: Path, thumbnails: Path, *, channel=None, jobs=3, max_age_hours=24):
    # CLI and scheduled sync share a lock. Waiting for another process never stalls the event loop.
    lock = run_lock(state_path.parent / ".demo-verifier")
    acquire = asyncio.create_task(asyncio.to_thread(lock.__enter__))
    try:
        await asyncio.shield(acquire)
    except asyncio.CancelledError:
        await acquire
        lock.__exit__(None, None, None)
        raise
    try:
        return await verify_locked(rows, state_path, thumbnails, channel, jobs, max_age_hours)
    finally:
        lock.__exit__(None, None, None)


async def verify_locked(rows, state_path, thumbnails, channel, jobs, max_age_hours):
    state = read_json(state_path) if state_path.exists() else {}
    thumbnails.mkdir(parents=True, exist_ok=True)
    checks = {}
    for row in rows:
        identifier = row["world_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier):
            raise ValueError("Invalid world ID for preview file")
        url = row.get("live_demo_url")
        output = thumbnails / f"{identifier}.webp"
        if not fresh(state.get(identifier, {}), url, output, timedelta(hours=max_age_hours)):
            checks[identifier] = (url, output)
    if not checks:
        return state
    semaphore = asyncio.Semaphore(jobs)

    async def inspect(browser, identifier, url, output):
        async with semaphore:
            thumbnail = None
            if not url:
                status, evidence = "no_demo", "案例未提供试玩链接"
            elif not external_url(url):
                status, evidence = "unverified", "链接超出公开 HTTP(S) 试玩范围"
            else:
                try:
                    async with asyncio.timeout(80):
                        status, evidence, thumbnail = await inspect_page(browser, url, output)
                except TimeoutError:
                    status, evidence = "unverified", "验证超时"
                except BrowserError as error:
                    status = "unverified"
                    evidence = "浏览器未完成加载：" + str(error).splitlines()[0][:160]
            checked_at = datetime.now(UTC).isoformat()
            preview_checked_at = checked_at if thumbnail else None
            previous = state.get(identifier) or {}
            transient = any(message in evidence for message in ("超时", "浏览器未完成加载", "浏览器访问检查", "HTTP 5"))
            if (status == "unverified" and transient and not thumbnail and output.exists()
                    and previous.get("live_demo_url") == url and previous.get("thumbnail_url")):
                thumbnail = previous["thumbnail_url"]
                preview_checked_at = previous.get("thumbnail_checked_at") or previous.get("checked_at")
            state[identifier] = {"check_version": CHECK_VERSION, "checked_at": checked_at,
                                 "live_demo_url": url, "demo_health_status": status,
                                 "thumbnail_url": thumbnail, "thumbnail_checked_at": preview_checked_at,
                                 "evidence": evidence}
            if not thumbnail:
                output.unlink(missing_ok=True)
            write_json(state_path, state)
            print(f"{identifier} {status} {evidence}", flush=True)

    pending = []
    for identifier, (url, output) in checks.items():
        if url and external_url(url):
            pending.append((identifier, url, output))
        else:
            await inspect(None, identifier, url, output)
    if pending:
        async with isolated_browser(channel) as browser:
            await asyncio.gather(*(inspect(browser, identifier, url, output) for identifier, url, output in pending))
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path)
    parser.add_argument("--state", type=Path, default=Path("data/state/demo_health.json"))
    parser.add_argument("--thumbnails", type=Path, default=Path("platform/public/thumbnails"))
    parser.add_argument("--channel", help="Optional installed Chromium channel, e.g. chrome.")
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=3)
    parser.add_argument("--max-age-hours", type=float, default=24)
    args = parser.parse_args()
    rows = [row for file in args.input or [Path("data/exports/ai_worlds.json")] for row in read_json(file)]
    state = asyncio.run(verify(rows, args.state, args.thumbnails, channel=args.channel, jobs=args.jobs,
                               max_age_hours=args.max_age_hours))
    print(dict(Counter(state[row["world_id"]]["demo_health_status"] for row in rows)))


if __name__ == "__main__":
    main()
