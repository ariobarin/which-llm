"""Refresh Artificial Analysis model and matching benchmark-cost data."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


URL = "https://artificialanalysis.ai/models"
BASE_URL = "https://artificialanalysis.ai"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ART = Path(__file__).parent / "artifacts"
HTML_PATH = ART / "models.html"
CSV_PATH = ART / "models.csv"
ENRICHED_CSV_PATH = ART / "models_enriched.csv"
MIN_MODELS = 400


def _open(url: str, timeout: int = 60):
    transient = {429, 500, 502, 503, 504, 520, 521, 522, 524}
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in transient:
                raise
            last_error = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        if attempt < 3:
            time.sleep(2 ** attempt)
    raise last_error or RuntimeError(f"failed to fetch {url}")


def _get_text(url: str, timeout: int = 60) -> str:
    with _open(url, timeout) as response:
        return response.read().decode("utf-8")


def _get_bytes(url: str, timeout: int = 60) -> tuple[bytes, str | None]:
    with _open(url, timeout) as response:
        return response.read(), response.headers.get("Last-Modified")


def fetch_html(refresh: bool) -> str:
    if HTML_PATH.exists() and not refresh:
        return HTML_PATH.read_text(encoding="utf-8")
    ART.mkdir(parents=True, exist_ok=True)
    print(f"GET {URL}")
    text = _get_text(URL)
    HTML_PATH.write_text(text, encoding="utf-8")
    print(f"  saved {len(text):,} chars -> {HTML_PATH}")
    return text


_CHUNK_RE = re.compile(
    r'self\.__next_f\.push\(\[(\d+),\s*"((?:[^"\\]|\\.)*)"\]\)', re.DOTALL
)
_MANIFEST_RE = re.compile(
    r'"manifest"\s*:\s*(\{[^{}]+\})'
)


def manifests(stream: str):
    seen = set()
    for match in _MANIFEST_RE.finditer(stream):
        value = json.loads(match.group(1))
        path, key = value.get("path"), value.get("key")
        if isinstance(path, str) and isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key):
            if (path, key) not in seen:
                seen.add((path, key))
                yield path, key


def extract_rsc_stream(html: str) -> str:
    parts = []
    for match in _CHUNK_RE.finditer(html):
        if match.group(1) == "1":
            parts.append(json.loads('"' + match.group(2) + '"'))
    if not parts:
        raise RuntimeError("No __next_f.push chunks found - page format changed?")
    return "".join(parts)


def _decrypt_manifest(path: str, key_hex: str) -> tuple[object, str | None]:
    payload, last_modified = _get_bytes(urllib.request.urljoin(URL, path))
    key = bytes.fromhex(key_hex)
    iv = hashlib.sha256(key).digest()[:12]
    cleartext = AESGCM(key).decrypt(iv, payload, None)
    value = json.loads(gzip.decompress(cleartext))
    if last_modified:
        updated = parsedate_to_datetime(last_modified).astimezone(timezone.utc)
        return value, updated.isoformat().replace("+00:00", "Z")
    return value, None


def find_catalog_manifest(stream: str, min_models: int = MIN_MODELS) -> tuple[list[dict], str]:
    errors = []
    for path, key in manifests(stream):
        try:
            value, updated = _decrypt_manifest(path, key)
        except Exception as exc:
            errors.append(f"{path}: {exc}")
            continue
        if not updated:
            errors.append(f"{path}: missing Last-Modified source timestamp")
            continue
        models = value.get("models") if isinstance(value, dict) else None
        if not isinstance(models, list) or len(models) < min_models:
            continue
        first = models[0] if models else {}
        required = {"slug", "name", "intelligenceIndex", "creator"}
        if required <= set(first):
            return models, updated
    detail = "; ".join(errors[:3])
    raise RuntimeError(f"No valid AA model manifest found. {detail}".strip())


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith(("/evaluations/", "/models/capabilities/")):
                self.links.add(href.split("#")[0])


def shared_dataset(url: str, row_key: str | None = None) -> tuple[dict, str]:
    stream = extract_rsc_stream(_get_text(url))
    errors = []
    for path, key in manifests(stream):
        try:
            value, updated = _decrypt_manifest(path, key)
            if not isinstance(value, dict) or not updated:
                continue
            if row_key:
                rows = value.get("models")
                if not isinstance(rows, list) or not rows:
                    continue
                if not all(isinstance(row, dict) and row.get("slug") for row in rows):
                    continue
                if not any(row_key in row for row in rows):
                    continue
            elif not all(key in value for key in ("media", "speech", "codingAgents")):
                continue
            return value, updated
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(f"No dated shared dataset at {url}: {'; '.join(errors[:2])}")


def discover_dataset(index_url: str, row_key: str) -> tuple[dict, str, str]:
    links = PageLinks()
    links.feed(_get_text(index_url))
    prefix = urllib.parse.urlparse(index_url).path.rstrip("/") + "/"
    errors = []
    for path in sorted(link for link in links.links if link.startswith(prefix)):
        url = BASE_URL + path
        try:
            value, updated = shared_dataset(url, row_key)
            return value, updated, url
        except (RuntimeError, OSError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError(f"No shared dataset discovered from {index_url}: {'; '.join(errors[:3])}")


def collect_details(models: list[dict], updated_at: str) -> dict:
    from data import DATA_PATH, age_days, read_bundle

    try:
        previous = read_bundle(DATA_PATH)
    except (OSError, ValueError):
        previous = {"datasets": {}}
    datasets = {"catalog": {"source_url": URL, "source_updated_at_utc": updated_at, "rows": models}}
    groups = [
        ("evaluations", BASE_URL + "/evaluations", "canonicalEvalTokenCounts"),
        ("capabilities", BASE_URL + "/models/capabilities", "capabilities"),
        ("home", BASE_URL, None),
    ]
    errors = {}
    for name, url, row_key in groups:
        try:
            if row_key:
                value, stamp, source_url = discover_dataset(url, row_key)
                tables = {name: value["models"]}
            else:
                value, stamp = shared_dataset(url)
                source_url = url
                tables = {"coding-agents": value["codingAgents"], "providers": value.get("hostModels", [])}
                for group in ("media", "speech"):
                    tables.update({f"{group}/{key}": rows for key, rows in value[group].items()})
            for table, rows in tables.items():
                if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
                    raise RuntimeError(f"Empty or invalid {table} dataset")
                cached = previous["datasets"].get(table, {})
                if cached and len(rows) < len(cached["rows"]) * 0.8:
                    raise RuntimeError(f"{table} lost over 20% of its rows")
                if cached and age_days(stamp) > age_days(cached.get("source_updated_at_utc")):
                    raise RuntimeError(f"{table} source timestamp regressed")
            datasets.update({table: {"source_url": source_url, "source_updated_at_utc": stamp,
                                    **({"scope": "AA homepage provider comparison subset, not the full hosting catalog"} if table == "providers" else {}),
                                    "rows": rows}
                             for table, rows in tables.items()})
        except (RuntimeError, OSError, ValueError) as exc:
            errors[name] = str(exc)
            print(f"WARNING: {name} unavailable: {exc}", file=sys.stderr)
            for table, cached in previous["datasets"].items():
                if table == name or (name == "home" and table not in {"catalog", "evaluations", "capabilities"}):
                    datasets[table] = {**cached, "refresh_error": str(exc)}
    return {"schema_version": 1, "refresh_errors": errors, "datasets": datasets}


CSV_FIELDS = [
    "snapshot_updated_at_utc",
    "name", "short_name", "slug", "model_family_slug", "creator_name",
    "creator_slug", "release_date", "knowledge_cutoff_date", "deprecated",
    "intelligence_index", "intelligence_index_cost_per_task_usd",
    "intelligence_index_cost_usd", "intelligence_index_is_estimated",
    "estimated_intelligence_index", "intelligence_index_per_m_output_tokens",
    "intelligence_index_input_cost_usd", "intelligence_index_output_cost_usd",
    "intelligence_index_reasoning_cost_usd", "indexTokensTotal",
    "coding_index", "math_index", "agentic_index",
    "agentic_index_cost_per_task_usd", "agentic_index_total_cost_usd",
    "agentic_index_time_per_task_seconds", "agentic_index_output_tokens_per_task",
    "gpqa", "hle", "mmlu_pro", "mmmu_pro", "livecodebench", "math_500",
    "aime", "aime25", "scicode", "humaneval", "tau2", "terminalbench_hard",
    "ifbench", "apex_agents", "lcr", "critpt", "gdpval", "omniscience",
    "price_1m_input_tokens", "price_1m_output_tokens",
    "price_1m_blended_0_100_1", "price_1m_blended_0_1_1",
    "price_1m_blended_0_3_1", "price_1m_blended_100_1_1",
    "price_1m_blended_7_2_1", "cache_hit_price", "reasoning_model",
    "frontier_model", "is_open_weights", "commercial_allowed",
    "input_modality_text", "input_modality_image", "input_modality_speech",
    "input_modality_video", "output_modality_text", "output_modality_image",
    "output_modality_speech", "output_modality_video", "context_window_tokens",
    "parameters_billions", "active_parameters_billions", "size_class",
    "ttft_seconds", "e2e_response_seconds",
]

EXTRA_FIELDS = {
    "release_slug": "release.slug", "reasoning_effort": "effort.slug",
    "license_name": "licenseName", "license_url": "licenseUrl",
    "weights_url": "modelWeightsSourceUrl", "openness_category": "openSourceCategorization",
    "openness_index": "openness.opennessIndex", "cache_write_price": "cacheWritePrice",
    "output_tokens_per_second": "timescaleData.medianOutputSpeed",
    "time_to_first_chunk_seconds": "timescaleData.medianTimeToFirstChunk",
    "output_speed_p05": "outputSpeedVariance.p05", "output_speed_p95": "outputSpeedVariance.p95",
    "performance_provider": "performanceDataSource.providerName",
    "intelligence_index_time_per_task_seconds": "intelligenceIndexTimePerTask",
    "intelligence_index_output_tokens_per_task": "intelligenceIndexOutputTokensPerTask.output",
    "intelligence_index_reasoning_tokens_per_task": "intelligenceIndexOutputTokensPerTask.reasoning",
    "intelligence_index_answer_tokens_per_task": "intelligenceIndexOutputTokensPerTask.answer",
    "briefcase_elo": "briefcaseBreakdown.overall.elo",
    "briefcase_rubric_pass_rate": "briefcaseBreakdown.rubricPassRate",
    "gdp_pdf_all_pass": "gdpPdfAllPass", "gdpval_normalized": "gdpvalNormalized",
    "tau3_banking": "tauBanking", "terminalbench_v2_1": "terminalbenchV21",
    "terminalbench_v4_0": "terminalbenchV40", "analyst_agent": "analystAgent",
    "automation_bench": "automationBenchPartialScore", "enterprise_ops_gym": "enterpriseOpsGym",
    "harvey_lab": "harveyLab", "itbench_sre": "itBenchSre",
    "mlcr_overall": "mlcrOverall", "omniscience_accuracy": "omniscienceBreakdown.accuracy",
    "omniscience_hallucination_rate": "omniscienceBreakdown.hallucinationRate",
}
CSV_FIELDS += list(EXTRA_FIELDS)


def _nested(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _positive(value):
    try:
        return value if value is not None and float(value) > 0 else None
    except (TypeError, ValueError):
        return None


def flatten(model: dict, agentic: dict | None = None, updated_at: str | None = None) -> dict:
    """Flatten the current camelCase schema, with legacy-key fallbacks."""
    agentic = agentic or {}
    creator = model.get("creator") or model.get("model_creators") or {}
    cost = model.get("intelligenceIndexCost") or model.get("intelligence_index_cost") or {}
    per_task = model.get("intelligenceIndexCostPerTask") or {}
    canonical = model.get("canonicalIntelligenceIndexTokenCount") or {}
    token_total = model.get("indexTokensTotal")
    if token_total is None and canonical:
        token_total = (canonical.get("input") or 0) + (canonical.get("output") or 0)
    agentic_cost = agentic.get("costPerTask") or {}
    agentic_total = agentic.get("evalCost") or {}
    agentic_tokens = agentic.get("outputTokensPerTask") or {}
    row = {
        "snapshot_updated_at_utc": updated_at,
        "name": model.get("name"), "short_name": model.get("shortName") or model.get("short_name"),
        "slug": model.get("slug"), "model_family_slug": model.get("model_family_slug") or _nested(model, "release", "slug"),
        "creator_name": creator.get("name"), "creator_slug": creator.get("slug"),
        "release_date": model.get("releaseDate") or model.get("release_date"),
        "knowledge_cutoff_date": model.get("knowledgeCutoffDate") or model.get("knowledge_cutoff_date"),
        "deprecated": model.get("deprecated"),
        "intelligence_index": model.get("intelligenceIndex", model.get("intelligence_index")),
        "intelligence_index_cost_per_task_usd": _nested(per_task, "cost", "total"),
        "intelligence_index_cost_usd": cost.get("total", cost.get("total_cost")),
        "intelligence_index_is_estimated": model.get("intelligenceIndexIsEstimated", model.get("intelligence_index_is_estimated")),
        "estimated_intelligence_index": model.get("estimated_intelligence_index"),
        "intelligence_index_per_m_output_tokens": model.get("intelligence_index_per_m_output_tokens"),
        "intelligence_index_input_cost_usd": cost.get("input", cost.get("input_cost")),
        "intelligence_index_output_cost_usd": cost.get("output", cost.get("output_cost")),
        "intelligence_index_reasoning_cost_usd": cost.get("reasoning", cost.get("reasoning_cost")),
        "indexTokensTotal": token_total,
        "coding_index": model.get("codingIndex", model.get("coding_index")),
        "math_index": model.get("math_index"),
        "agentic_index": agentic.get("headlineValue", model.get("agenticIndex", model.get("agentic_index"))),
        "agentic_index_cost_per_task_usd": agentic_cost.get("total"),
        "agentic_index_total_cost_usd": agentic_total.get("total"),
        "agentic_index_time_per_task_seconds": agentic.get("timePerTaskSeconds"),
        "agentic_index_output_tokens_per_task": agentic_tokens.get("output"),
        "gpqa": model.get("gpqa"), "hle": model.get("hle"), "mmlu_pro": model.get("mmluPro", model.get("mmlu_pro")),
        "mmmu_pro": model.get("mmmuPro", model.get("mmmu_pro")), "livecodebench": model.get("livecodebench"),
        "math_500": model.get("math_500"), "aime": model.get("aime"), "aime25": model.get("aime25"),
        "scicode": model.get("scicode"), "humaneval": model.get("humaneval"), "tau2": model.get("tau2"),
        "terminalbench_hard": model.get("terminalbenchHard", model.get("terminalbench_hard")),
        "ifbench": model.get("ifbench"), "apex_agents": model.get("apexAgents", model.get("apex_agents")),
        "lcr": model.get("lcr"), "critpt": model.get("critpt"), "gdpval": model.get("gdpval"),
        "omniscience": model.get("omniscience"),
        "price_1m_input_tokens": model.get("price1mInputTokens", model.get("price_1m_input_tokens")),
        "price_1m_output_tokens": model.get("price1mOutputTokens", model.get("price_1m_output_tokens")),
        "price_1m_blended_0_100_1": model.get("price1mBlended0To100To1", model.get("price_1m_blended_0_100_1")),
        "price_1m_blended_0_1_1": model.get("price1mBlended0To1To1", model.get("price_1m_blended_0_1_1")),
        "price_1m_blended_0_3_1": model.get("price1mBlended0To3To1", model.get("price_1m_blended_0_3_1")),
        "price_1m_blended_100_1_1": model.get("price1mBlended100To1To1", model.get("price_1m_blended_100_1_1")),
        "price_1m_blended_7_2_1": model.get("price1mBlended7To2To1", model.get("price_1m_blended_7_2_1")),
        "cache_hit_price": model.get("cacheHitPrice", model.get("cache_hit_price")),
        "reasoning_model": model.get("isReasoning", model.get("reasoning_model")),
        "frontier_model": model.get("frontier_model"), "is_open_weights": model.get("isOpenWeights", model.get("is_open_weights")),
        "commercial_allowed": model.get("commercialAllowed", model.get("commercial_allowed")),
        "input_modality_text": model.get("inputModalityText", model.get("input_modality_text")),
        "input_modality_image": model.get("inputModalityImage", model.get("input_modality_image")),
        "input_modality_speech": model.get("inputModalitySpeech", model.get("input_modality_speech")),
        "input_modality_video": model.get("inputModalityVideo", model.get("input_modality_video")),
        "output_modality_text": model.get("outputModalityText", model.get("output_modality_text")),
        "output_modality_image": model.get("outputModalityImage", model.get("output_modality_image")),
        "output_modality_speech": model.get("outputModalitySpeech", model.get("output_modality_speech")),
        "output_modality_video": model.get("outputModalityVideo", model.get("output_modality_video")),
        "context_window_tokens": model.get("contextWindowTokens", model.get("context_window_tokens")),
        "parameters_billions": model.get("parameters"),
        "active_parameters_billions": model.get("inferenceParametersActiveBillions", model.get("activeParams")),
        "size_class": model.get("sizeClass", model.get("size_class")),
        "ttft_seconds": _positive(_nested(model, "timeToFirstAnswerToken", "total") or _nested(model, "time_to_first_answer_token_metrics", "total_time")),
        "e2e_response_seconds": _positive(_nested(model, "endToEndResponseTime", "total") or _nested(model, "end_to_end_response_time_metrics", "total_time")),
    }
    row.update({field: _nested(model, *path.split(".")) for field, path in EXTRA_FIELDS.items()})
    return row


def previous_model_count() -> int | None:
    snapshot = ENRICHED_CSV_PATH if ENRICHED_CSV_PATH.exists() else CSV_PATH
    if not snapshot.exists():
        return None
    try:
        with snapshot.open(encoding="utf-8", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except (OSError, csv.Error):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    stream = extract_rsc_stream(fetch_html(args.refresh))
    models, updated_at = find_catalog_manifest(stream)
    print(f"Parsed {len(models)} catalog models")
    prior = previous_model_count()
    if prior and len(models) / prior < 0.8:
        print(f"ABORT: parsed {len(models)} models, previous snapshot had {prior}", file=sys.stderr)
        return 2
    slugs = [model.get("slug") for model in models]
    if not all(slugs) or len(set(slugs)) != len(slugs):
        raise RuntimeError("catalog contains missing or duplicate slugs")
    rows = [flatten(model, updated_at=updated_at) for model in models]
    if not all(any(row[field] is not None for row in rows) for field in
               ("intelligence_index", "intelligence_index_cost_per_task_usd", "context_window_tokens")):
        raise RuntimeError("catalog lost required score, cost, or context fields")
    details = collect_details(models, updated_at)
    from data import DATA_PATH, atomic_write
    # One record per line keeps source changes reviewable without expanding every nested metric.
    tables = []
    for name, dataset in sorted(details["datasets"].items()):
        metadata = json.dumps({k: v for k, v in dataset.items() if k != "rows"}, ensure_ascii=False)
        records = ",\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in dataset["rows"])
        tables.append(json.dumps(name) + ":" + metadata[:-1] + ',"rows":[\n' + records + "]}")
    bundle = '{"schema_version":1,"refresh_errors":' + json.dumps(details["refresh_errors"]) + ',"datasets":{\n' + ",\n".join(tables) + "}}\n"
    atomic_write(DATA_PATH, bundle)
    ART.mkdir(parents=True, exist_ok=True)
    with io.StringIO(newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        atomic_write(CSV_PATH, handle.getvalue())
    print("  datasets: " + ", ".join(f"{key}={len(value['rows'])}" for key, value in details["datasets"].items()))
    print(f"  source_updated_at: {updated_at}")
    print(f"  wrote {CSV_PATH} ({CSV_PATH.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
