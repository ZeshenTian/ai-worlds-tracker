from enum import StrEnum
import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
import httpx
import typer
import yaml

from .recheck_attribution import record_manual_reviews
from .apify_x import ApifyXAdapter, RunLedger, api_token, incremental as apify_incremental
from .dedup import deduplicate
from .x_media import load_media_evidence
from .enrich_firecrawl import EnrichmentCache, Firecrawl, FixtureScraper
from .export_and_analyze import export_cases
from .extract_structured import AnnotatedExtractor, OpenAIExtractor, extract_cases
from .ingest_x import MockXAdapter, OfficialXApiAdapter, ThirdPartyXAdapter, import_records, ingest
from .models import AIWorldCase, CaseGroup, EnrichedLinkContent, RawTweetRecord, ReviewStatus
from .storage import digest, read_json, read_rows, run_lock, write_json, write_rows


PROJECT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT / "tests" / "fixtures"
app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


class Mode(StrEnum):
    SEED = "seed"
    SEARCH = "search"
    INCREMENTAL = "incremental"


class Pipeline:
    def __init__(self, source: str, root: Path, seed_file: Path | None, report: Path, client: httpx.Client):
        self.source = source
        self.root = root
        self.seeds = seed_file or (FIXTURES / "seeds.yaml" if source == "mock" else PROJECT / "config" / "seeds.yaml")
        self.report = report
        self.client = client
        self.processed = root / "processed"

    def required_env(self, key: str) -> str:
        value = os.environ.get(key)
        if not value:
            raise ValueError(f"{key} is required for this stage. See .env.example.")
        return value

    def ingest(self, mode: Mode, limit: int, refresh: bool):
        if self.source == "manual":
            raise ValueError("Use import-x for manual JSON / JSONL. Seed URL lookup requires an X adapter.")
        if self.source == "apify":
            config = yaml.safe_load(self.seeds.read_text(encoding="utf-8"))
            budget = os.getenv("APIFY_DAILY_BUDGET_USD", "1.50")
            # Keep the Apify credential confined to API requests, never t.co or project URLs.
            with httpx.Client(headers={"Authorization": "Bearer " + api_token()}, timeout=45) as http:
                ledger = RunLedger(self.root, http, budget, daily=True)
                if mode == Mode.INCREMENTAL:
                    from datetime import UTC, datetime
                    import time
                    catalogs = self.seeds.parent / "catalogs.yaml"
                    if catalogs.exists():
                        config["official_threads"] = yaml.safe_load(catalogs.read_text()).get("official_threads", [])
                    ledger.deadline = time.monotonic() + 360
                    apify_incremental(ledger, config, datetime.now(UTC).date(), limit)
                    typer.echo("Saved the Apify incremental search state.")
                else:
                    rows = ingest(ApifyXAdapter(ledger), config, self.root, mode, limit, self.client, refresh=refresh)
                    typer.echo(f"Ingested {len(rows)} X records.")
            return
        if self.source == "mock":
            adapter = MockXAdapter(FIXTURES / "tweets.json")
        elif self.source == "x_api_v2":
            archive = os.environ.get("X_THREAD_ARCHIVE", "").lower() in {"true", "1", "yes"}
            adapter = OfficialXApiAdapter(self.required_env("X_BEARER_TOKEN"), self.client, archive=archive)
        else:
            adapter = ThirdPartyXAdapter(self.required_env("X_THIRD_PARTY_BASE_URL"),
                                         self.required_env("X_THIRD_PARTY_API_KEY"), self.client)
        config = yaml.safe_load(self.seeds.read_text(encoding="utf-8"))
        rows = ingest(adapter, config, self.root, mode, limit,
                      None if self.source == "mock" else self.client, refresh=refresh)
        typer.echo(f"Ingested {len(rows)} X records.")

    def dedup(self) -> None:
        records = [RawTweetRecord.model_validate_json(path.read_text(encoding="utf-8"))
                   for path in (self.root / "raw" / "x").glob("*.json")]
        if not records:
            raise ValueError("No X records. Run ingest or import-x first.")
        config = (yaml.safe_load(self.seeds.read_text(encoding="utf-8")) or {}) if self.seeds.is_file() else {}
        groups = deduplicate(records, excluded_authors=config.get("excluded_aggregator_accounts", ()),
                             media_evidence=load_media_evidence(self.root))
        write_rows(self.processed / "groups.jsonl", groups)
        typer.echo(f"Deduplicated {len(records)} posts into {len(groups)} groups.")

    def enrich(self) -> None:
        cache = EnrichmentCache(self.root)
        groups = read_rows(self.processed / "groups.jsonl", CaseGroup)
        if self.source == "mock":
            scraper = FixtureScraper(FIXTURES / "pages.json")
        else:
            scraper = Firecrawl(os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_TOKEN", ""), self.client, os.environ.get("GITHUB_TOKEN"))
        cache.enrich(groups, scraper)
        typer.echo(f"Enriched {len(groups)} groups.")

    def extract(self, annotations: Path | None = None, evidence_file: Path | None = None) -> None:
        groups = read_rows(self.processed / "groups.jsonl", CaseGroup)
        model = os.environ.get("EXTRACTION_MODEL", "gpt-5-mini")
        fixture = FIXTURES / "extractions.json"
        manual_pages = None
        if annotations is not None:
            if self.source != "manual" or evidence_file is None:
                raise ValueError("Manual annotations require X_ADAPTER=manual and --evidence-file.")
            manual_pages = [EnrichedLinkContent.model_validate(item) for item in read_json(evidence_file)]
        elif evidence_file is not None:
            raise ValueError("--evidence-file requires --annotations.")

        if self.source == "mock" or annotations is not None:
            annotation_path = annotations or fixture
            namespace = "annotations:" + digest(annotation_path.read_text(encoding="utf-8"))

            def load_extractor():
                return AnnotatedExtractor(annotation_path)
        else:
            namespace = f"openai:{model}"

            def load_extractor():
                return OpenAIExtractor(self.required_env("OPENAI_API_KEY"), model)

        if annotations:
            annotation_ids = read_json(annotations).keys()
            groups = [group for group in groups if group.original.post.tweet_id in annotation_ids]
        rows = extract_cases(groups, self.root, namespace, load_extractor, self.cases(missing_ok=True), manual_pages)
        write_json(self.processed / "annotation_mode.json", annotations is not None)
        typer.echo(f"Validated {len(rows)} cases.")

    def cases(self, *, missing_ok=False) -> list[AIWorldCase]:
        path = self.processed / "cases.jsonl"
        if missing_ok and not path.exists():
            return []
        return read_rows(path, AIWorldCase)

    def export(self) -> None:
        mode_file = self.processed / "annotation_mode.json"
        manual = mode_file.exists() and read_json(mode_file)
        if self.source != "mock" and self.root.resolve() == (PROJECT / "data").resolve():
            from .publish_catalog import publish
            publish(self.root, PROJECT / "platform")
        else:
            export_cases(self.cases(), self.root / "exports", self.report,
                         is_mock=self.source == "mock", manual=manual)
        typer.echo(f"Exports: {self.root / 'exports'}\nReport: {self.report}")


def run(ctx, action):
    load_dotenv(PROJECT / ".env", override=False)
    directory, seed_file, report, source_override = ctx.obj
    source = source_override or os.environ.get("X_ADAPTER", "mock")
    if source not in {"mock", "x_api_v2", "third_party", "manual", "apify"}:
        raise typer.BadParameter("X_ADAPTER must be mock, x_api_v2, third_party, apify or manual")
    root = directory or (PROJECT / "data" / "mock" if source == "mock" else PROJECT / "data")
    report = report or (PROJECT / "reports" / "step1_summary.md" if source == "mock"
                        else PROJECT / "reports" / "live" / "step1_summary.md")
    try:
        with httpx.Client(timeout=45, follow_redirects=False) as client, run_lock(root):
            action(Pipeline(source, root, seed_file, report, client))
    except (ValueError, OSError, httpx.HTTPError, KeyError, yaml.YAMLError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error


@app.callback()
def configure(
    ctx: typer.Context,
    data_dir: Annotated[Path | None, typer.Option(help="Override the data root.")] = None,
    seed_file: Annotated[Path | None, typer.Option(help="Override the seed YAML.")] = None,
    report_path: Annotated[Path | None, typer.Option(help="Override the Markdown report path.")] = None,
    source: Annotated[str | None, typer.Option(help="Override X_ADAPTER for this invocation.")] = None,
):
    """Collect and analyze documented AI-generated interactive worlds."""
    ctx.obj = data_dir, seed_file, report_path, source


Limit = Annotated[int, typer.Option(min=1, max=100, help="Maximum results per search query.")]


@app.command("ingest")
def ingest_command(ctx: typer.Context, mode: Mode = Mode.SEED, limit: Limit = 30, refresh: bool = False):
    run(ctx, lambda pipeline: pipeline.ingest(mode, limit, refresh))


@app.command("import-x")
def import_command(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    expand_short_links: Annotated[bool, typer.Option(help="Resolve t.co links that have no expanded URL.")] = False,
):
    def action(pipeline: Pipeline) -> None:
        if pipeline.source == "mock":
            raise ValueError("Set X_ADAPTER=manual (or a live adapter) before importing real records.")
        rows = import_records(path, pipeline.root, pipeline.client if expand_short_links else None)
        typer.echo(f"Imported {len(rows)} records.")

    run(ctx, action)


@app.command()
def dedup(ctx: typer.Context):
    run(ctx, Pipeline.dedup)


@app.command()
def enrich(ctx: typer.Context):
    run(ctx, Pipeline.enrich)


@app.command()
def extract(ctx: typer.Context,
            annotations: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
            evidence_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None):
    run(ctx, lambda pipeline: pipeline.extract(annotations, evidence_file))


@app.command()
def export(ctx: typer.Context):
    run(ctx, Pipeline.export)


@app.command()
def review(ctx: typer.Context, world_id: str, status: ReviewStatus):
    def action(pipeline: Pipeline):
        rows = pipeline.cases()
        matched = next((row for row in rows if row.world_id == world_id), None)
        if matched is None:
            raise ValueError(f"Unknown world_id: {world_id}")
        matched.review_status = status
        record_manual_reviews(pipeline.root, [matched])
        write_rows(pipeline.processed / "cases.jsonl", rows)
        pipeline.export()

    run(ctx, action)


@app.command()
def run_all(ctx: typer.Context, mode: Mode = Mode.SEED, limit: Limit = 30, refresh: bool = False):
    def action(pipeline: Pipeline):
        if pipeline.source != "manual":
            pipeline.ingest(mode, limit, refresh)
        pipeline.dedup()
        pipeline.enrich()
        pipeline.extract()
        pipeline.export()

    run(ctx, action)


if __name__ == "__main__":
    app()
