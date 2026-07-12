"""Refresh Artificial Analysis model and matching benchmark-cost data."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


URL = "https://artificialanalysis.ai/models"
AGENTIC_URL = "https://artificialanalysis.ai/models/capabilities/agentic"
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
    transient = {502, 503, 504, 520, 521, 522, 524}
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in transient:
                raise
            last_error = exc
        except urllib.error.URLError as exc:
            last_error = exc
        if attempt < 3:
            time.sleep(2 * attempt)
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
    r'"manifest":\{"path":"([^"]+)","key":"([0-9a-f]{64})"\}'
)


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
    for path, key in _MANIFEST_RE.findall(stream):
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


def find_model_array(
    stream: str, *, min_models: int, required_keys: set[str]
) -> list[dict]:
    decoder = json.JSONDecoder()
    candidates = []
    for match in re.finditer(r'"models"\s*:\s*\[', stream):
        try:
            value, _ = decoder.raw_decode(stream, match.end() - 1)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, list) or len(value) < min_models or not value:
            continue
        if isinstance(value[0], dict) and required_keys <= set(value[0]):
            candidates.append(value)
    if not candidates:
        raise RuntimeError(f"No model array found with keys {sorted(required_keys)}")
    return max(candidates, key=len)


def fetch_agentic_models() -> list[dict]:
    stream = extract_rsc_stream(_get_text(AGENTIC_URL))
    return find_model_array(
        stream,
        min_models=20,
        required_keys={"slug", "headlineValue", "costPerTask", "evalCost"},
    )


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
    return {
        "snapshot_updated_at_utc": updated_at,
        "name": model.get("name"), "short_name": model.get("shortName") or model.get("short_name"),
        "slug": model.get("slug"), "model_family_slug": model.get("model_family_slug"),
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
    agentic = fetch_agentic_models()
    print(f"Parsed {len(models)} catalog models and {len(agentic)} agentic rows")
    prior = previous_model_count()
    if prior and len(models) / prior < 0.8:
        print(f"ABORT: parsed {len(models)} models, previous snapshot had {prior}", file=sys.stderr)
        return 2
    by_slug = {row["slug"]: row for row in agentic if row.get("slug")}
    rows = [flatten(model, by_slug.get(model.get("slug")), updated_at) for model in models]
    if not any(row["slug"].startswith("gpt-5-6") for row in rows):
        raise RuntimeError("fresh catalog is missing GPT-5.6")
    ART.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  source_updated_at: {updated_at}")
    print(f"  wrote {CSV_PATH} ({CSV_PATH.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
