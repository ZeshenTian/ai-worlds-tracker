from datetime import datetime
from enum import StrEnum
import re
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


def web_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username is not None:
        raise ValueError("expected a public-facing HTTP(S) URL without credentials")
    return value


WebURL = Annotated[str, AfterValidator(web_url)]
Text = Annotated[str, Field(min_length=1)]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
Handle = Annotated[str, Field(pattern=r"^[A-Za-z0-9_]{1,15}$")]
TweetID = Annotated[str, Field(pattern=r"^[0-9]+$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RawPost(Record):
    tweet_id: TweetID
    author_handle: Handle
    text: str
    published_at: datetime | None = None
    conversation_id: TweetID | None = None
    expanded_urls: dict[str, WebURL] = Field(default_factory=dict)
    media_keys: list[str] = Field(default_factory=list)
    referenced_post_ids: list[TweetID] = Field(default_factory=list)


class RawTweetRecord(Record):
    post: RawPost
    thread: list[RawPost] = Field(default_factory=list)
    external_urls: list[WebURL] = Field(default_factory=list)
    demo_urls: list[WebURL] = Field(default_factory=list)
    thread_status: str = "unknown"

    @model_validator(mode="after")
    def author_thread(self) -> Self:
        seen = {self.post.tweet_id}
        for reply in self.thread:
            if reply.author_handle.casefold() != self.post.author_handle.casefold():
                raise ValueError("thread must contain only author replies")
            if reply.tweet_id in seen:
                raise ValueError("duplicate post in thread")
            if reply.conversation_id and reply.conversation_id != (self.post.conversation_id or self.post.tweet_id):
                raise ValueError("reply belongs to another conversation")
            seen.add(reply.tweet_id)
        return self

    @property
    def original_url(self) -> str:
        return f"https://x.com/{self.post.author_handle}/status/{self.post.tweet_id}"


class EnrichedLinkContent(Record):
    url: WebURL
    final_url: WebURL | None = None
    fetch_method: str | None = None
    firecrawl_status_code: int | None = None
    markdown: str = ""
    kind: str = "page"
    status: str = "ok"
    status_code: int | None = None
    repository_owner: str | None = None
    repository_license: str | None = None


class CaseGroup(Record):
    original: RawTweetRecord
    related_post_urls: list[WebURL] = Field(default_factory=list)
    external_urls: list[WebURL] = Field(default_factory=list)
    repo_urls: list[WebURL] = Field(default_factory=list)
    demo_urls: list[WebURL] = Field(default_factory=list)
    possible_duplicate_urls: list[WebURL] = Field(default_factory=list)
    fingerprint: Text


class Theme(StrEnum):
    CITY = "city_diorama"
    FANTASY = "fantasy_rpg"
    SCI_FI = "sci_fi"
    PHYSICS = "physics_sim"
    VOXEL = "voxel_sandbox"
    HISTORICAL = "historical"
    NATURE = "nature_ecosystem"
    OTHER = "other"


class GenerationMode(StrEnum):
    ONE_SHOT = "one_shot"
    ITERATIVE = "iterative_chat"
    AGENTIC = "agentic_loop"
    HYBRID = "hybrid_pipeline"
    UNKNOWN = "unknown"


class Reproducibility(StrEnum):
    VIDEO = "video_only"
    PROMPT = "prompt_shared"
    DEMO = "live_demo"
    REPO = "full_repo"


class Disclosure(StrEnum):
    DISCLOSED = "disclosed"
    PARTIAL = "partial"
    UNDISCLOSED = "undisclosed"


class DemoHealth(StrEnum):
    VERIFIED = "verified_playable"
    LOGIN = "login_required"
    BROKEN = "broken"
    NO_DEMO = "no_demo"
    UNVERIFIED = "unverified"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def disclosure(cost: float | None, minutes: float | None) -> Disclosure:
    return (Disclosure.DISCLOSED if cost is not None and minutes is not None
            else Disclosure.PARTIAL if cost is not None or minutes is not None
            else Disclosure.UNDISCLOSED)


TECH_ALIASES = {
    "#threejs": "Three.js", "threejs": "Three.js", "three.js": "Three.js",
    "blender": "Blender", "blender-mcp": "Blender MCP",
    "webgl 2.0": "WebGL2", "web audio api": "Web Audio",
    "vanilla js": "JavaScript", "antigravity": "Antigravity",
    "single html": "Single-file HTML",
}
NON_TECH_TAGS = {
    "", "-", "—", "unknown", "undisclosed", "none", "n/a", "other", "未披露", "其他",
    "3d", "3d cities", "3d racing game", "3d rendering software", "ai agents",
    "browser", "browser game", "browser 3d game", "click and drag", "code",
    "flight physics simulation", "host cli", "plain modules", "physics pieces",
    "voxel san francisco bay area in the browser", "we rowser wegl", "x-high",
    "スマホのブラウザ", "ブラウザ", "ブラウザゲーム", "マウス",
}


def technology_tags(raw, models):
    # Some older imports expanded a comma-delimited string one character at a time.
    if isinstance(raw, list) and len(raw) > 3 and all(isinstance(v, str) and len(v) == 1 for v in raw):
        raw = "".join(raw)
    if isinstance(raw, str):
        raw = re.split(r"[,，;；]", raw)
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
        return raw
    seen = {name.strip().casefold() for name in models if isinstance(name, str)}
    tags = []
    for value in raw:
        tag = value.strip()
        tag = TECH_ALIASES.get(tag.casefold(), tag)
        key = tag.casefold()
        if key in seen or key in NON_TECH_TAGS:
            continue
        if re.fullmatch(r"(?:claude |gemini )?(?:opus|fable|sonnet|argon|carbon|neon|astra|gpt)(?:[- .0-9a-z]*)", key):
            continue
        seen.add(key)
        tags.append(tag)
    return tags


class AIWorldCase(Record):
    model_era: Literal["frontier", "legacy"] = "legacy"
    work_type: Literal["interactive_world", "coded_3d_scene"] = "interactive_world"
    world_id: Text
    title: Text
    summary: Text
    summary_en: Text | None = None
    workflow_steps_en: list[Text] = Field(default_factory=list)
    cover_source: Literal["demo", "x_media", "project_media", "project_poster"] | None = None
    cover_source_url: WebURL | None = None
    theme_category: Theme
    models_used: list[Text]
    tech_stack: list[Text]
    generation_mode: GenerationMode
    is_open_source: bool | None = Field(strict=True)
    reproducibility_level: Reproducibility
    repo_url: WebURL | None = None
    live_demo_url: WebURL | None = None
    original_post_url: WebURL
    source_kind: Literal["x_post", "primary_page"] = "x_post"
    author_name: Text | None = None
    author_handle: Handle | None = None
    first_seen_at: str | None = None
    demo_health_status: DemoHealth = DemoHealth.UNVERIFIED
    thumbnail_url: str | None = None
    published_at: str | None = None
    cost_disclosure_status: Disclosure
    reported_cost_usd: NonNegative | None = None
    reported_time_minutes: NonNegative | None = None
    workflow_steps: list[Text]
    skills_or_prompts_used: list[Text]
    evidence_quotes: list[Text]
    evidence_source_urls: list[WebURL] = Field(default_factory=list)
    dedup_fingerprint: Text
    review_status: ReviewStatus = ReviewStatus.PENDING
    related_post_urls: list[WebURL] = Field(default_factory=list)
    possible_duplicate_urls: list[WebURL] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def separate_build_tools(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get("models_used"), list):
            return value
        known_tools = {"three.js", "threejs", "blender", "web audio api", "webgpu", "webgl", "unity", "playcanvas", "babylon.js"}
        supplied = value["models_used"]
        tools = [name for name in supplied if isinstance(name, str) and name.casefold() in known_tools]
        models = [name for name in supplied if name not in tools]
        if "tech_stack" not in value:
            return value
        stack = technology_tags(value["tech_stack"], models)
        if isinstance(stack, list) and tools:
            stack = technology_tags(stack + tools, models)
        return {**value, "models_used": models, "tech_stack": stack}

    def normalize_taxonomy(self):
        from .model_era import canonicalize_models_and_stack, classify_model_era
        self.models_used, self.tech_stack = canonicalize_models_and_stack(self.models_used, self.tech_stack)
        self.model_era = classify_model_era(self.models_used, self.published_at)

    @field_validator("published_at", "first_seen_at")
    @classmethod
    def iso_timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            if "T" not in value:
                raise ValueError("published_at requires an ISO 8601 timestamp")
            datetime.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def consistent_case(self) -> Self:
        post = urlsplit(self.original_post_url)
        if self.source_kind == "primary_page" and (not self.author_name or post.hostname in {"x.com", "twitter.com"}):
            raise ValueError("a primary project page requires a credited author and project URL")
        if self.source_kind == "x_post" and (not self.author_handle or post.hostname != "x.com" or not re.fullmatch(
            rf"/{re.escape(self.author_handle)}/status/[0-9]+", post.path, re.IGNORECASE
        )):
            raise ValueError("original_post_url does not match the author")
        if not self.live_demo_url:
            if self.demo_health_status not in {DemoHealth.NO_DEMO, DemoHealth.UNVERIFIED}:
                raise ValueError("demo health requires a demo URL")
            self.demo_health_status = DemoHealth.NO_DEMO
        elif self.demo_health_status == DemoHealth.NO_DEMO:
            raise ValueError("no_demo conflicts with a demo URL")
        if self.thumbnail_url is not None:
            suffix = {"x_media": "-x", "project_media": "-project", "project_poster": "-project"}.get(self.cover_source, "")
            if (self.thumbnail_url != f"/thumbnails/{self.world_id}{suffix}.webp"
                    or (not self.live_demo_url and not suffix) or "/" in self.world_id or ".." in self.world_id):
                raise ValueError("invalid thumbnail path")
        if self.cost_disclosure_status != disclosure(self.reported_cost_usd, self.reported_time_minutes):
            raise ValueError("inconsistent cost disclosure")
        if self.reproducibility_level == Reproducibility.REPO and not self.repo_url:
            raise ValueError("full_repo requires a repository URL")
        if self.reproducibility_level == Reproducibility.DEMO and not self.live_demo_url:
            raise ValueError("live_demo requires a demo URL")
        return self
