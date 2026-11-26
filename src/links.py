import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SOCIAL_DOMAINS = {"x.com", "twitter.com", "t.co", "twimg.com"}
TRACKING_KEYS = {"fbclid", "gclid", "igshid", "ref_src"}
GITHUB_SECTIONS = {"about", "apps", "collections", "contact", "enterprise", "events", "features",
                   "issues", "marketplace", "new", "notifications", "orgs", "pulls", "search",
                   "settings", "site", "sponsors", "topics", "trending", "users"}
URL_PATTERN = re.compile(r'https?://[^\s<>"\x60\u3000-\u303f\uff00-\uffef]+', re.IGNORECASE)


def host_is(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def post_id(url: str) -> str:
    parts = urlsplit(url)
    match = re.fullmatch(r"/(?:[\w]+|i/web)/status/([0-9]+)(?:/(?:photo|video)/[0-9]+)?/?", parts.path)
    if parts.hostname not in {"x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"} or not match:
        raise ValueError(f"Invalid X post URL: {url}")
    return match[1]


def external_url(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not host or parts.username is not None:
        return None
    if "." not in host or host_is(host, SOCIAL_DOMAINS | {"localhost", "local", "internal", "test"}):
        return None
    try:
        if not ipaddress.ip_address(host).is_global:
            return None
    except ValueError:
        pass
    netloc = host
    if port and (parts.scheme, port) not in {("http", 80), ("https", 443)}:
        netloc += f":{port}"
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS]
    return urlunsplit((parts.scheme, netloc, parts.path or "/", urlencode(query), route_fragment(parts.fragment)))


def repo_root(url: str) -> str | None:
    parts = urlsplit(url)
    names = parts.path.strip("/").split("/")
    if parts.hostname not in {"github.com", "www.github.com"} or len(names) < 2:
        return None
    owner, repo = names[:2]
    if owner.casefold() in GITHUB_SECTIONS or not re.fullmatch(r"[\w.-]+/[\w.-]+", f"{owner}/{repo}", re.ASCII):
        return None
    repo = repo.removesuffix(".git")
    if owner in {".", ".."} or repo in {"", ".", ".."}:
        return None
    return f"https://github.com/{owner.lower()}/{repo.lower()}"


def route_fragment(fragment: str) -> str:
    # Hash routers identify different applications or scenes on one HTTP path.
    return fragment if fragment.startswith(("/", "!/")) else ""


def repo_project_key(url: str) -> str | None:
    """Identify repository roots and qualified project paths, ignoring issue and profile links."""
    try:
        root = repo_root(url)
    except ValueError:
        return None
    if not root:
        return None
    parts = urlsplit(url).path.strip("/").split("/")[2:]
    if not parts:
        return root
    if len(parts) < 2 or parts[0] not in {"tree", "blob"}:
        return None
    kind, ref, *path = parts
    if any(part in {"", ".", ".."} for part in (ref, *path)):
        return None
    if kind == "blob":
        if not path:
            return None
        if path[-1].lower() in {"readme.md", "index.html", "index.htm"}:
            path.pop()
            kind = "tree"
    if not path and ref in {"main", "master"}:
        return root
    return "/".join([root, kind, ref, *path])


def work_demo_key(url: str) -> str | None:
    """Return an identity for a labelled demo URL with a concrete project destination."""
    cleaned = external_url(url)
    if not cleaned or repo_root(cleaned):
        return None
    parts = urlsplit(cleaned)
    host = parts.hostname or ""
    route = route_fragment(parts.fragment).lstrip("!")
    path = (route or parts.path).strip("/").casefold()
    sections = path.split("/")
    generic = {"", "about", "account", "artifacts", "blog", "catalog", "community", "dashboard", "discover",
               "docs", "documentation", "examples", "explore", "features", "gallery", "games", "home",
               "index.html", "login", "models", "news", "portfolio", "pricing", "profile", "search",
               "showcase", "signup", "templates", "trending", "worlds"}
    if not path or path in {"index.html", "index.htm"}:
        # A deployment-specific hostname can itself identify a playable work.
        for service in ("vercel.app", "netlify.app", "pages.dev", "chatgpt.site", "lovable.app", "replit.app"):
            if not host.endswith("." + service):
                continue
            tenant = host.removesuffix("." + service)
            if tenant not in {"www", "app", "docs"} and (service != "chatgpt.site" or "." in tenant):
                return identity_url(cleaned)
        return None
    if (path in generic or sections[0] in {"blog", "docs", "news", "profile", "search", "users"}
            or (len(sections) == 1 and path.startswith("@"))):
        return None
    if host_is(host, {"github.com", "youtube.com", "youtu.be", "medium.com"}):
        return None
    if host in {"itch.io", "www.itch.io"}:
        return None
    if host in {"chatgpt.com", "www.chatgpt.com"} and not re.fullmatch(r"canvas/shared/[^/]+", path):
        return None
    if host in {"claude.ai", "www.claude.ai"} and not re.fullmatch(r"(?:public/)?artifacts?/[^/]+", path):
        return None
    return identity_url(cleaned)


def identity_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    return urlunsplit(("https", parts.netloc, path, parts.query, route_fragment(parts.fragment)))


def urls_in(text: str) -> list[tuple[str, int]]:
    result = []
    for match in URL_PATTERN.finditer(text):
        url = match.group().rstrip(".,!?:;]}'")
        while url.endswith(")") and url.count(")") > url.count("("):
            url = url[:-1]
        result.append((url, match.start()))
    return result
