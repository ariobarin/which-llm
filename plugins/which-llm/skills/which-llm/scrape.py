"""Scrape Artificial Analysis model leaderboard data.

Fetches https://artificialanalysis.ai/models, extracts the embedded RSC
payload, locates the full model array (the `defaultData` prop), and dumps:

  artifacts/models.html          raw HTML (cached for re-runs)
  artifacts/models.rsc           raw RSC payload (cached for re-runs)
  artifacts/models.json          raw model objects
  artifacts/models.csv           local flat rows for enrichment
  artifacts/provider_endpoints.csv
                                 provider-specific endpoint rows
  artifacts/benchmark_token_counts.csv
                                 per-benchmark token accounting
  artifacts/index_cost_by_evaluation.csv
                                 per-evaluation weighted index costs
  artifacts/prompt_performance.csv
                                 prompt-length performance rows
  artifacts/multilingual_scores.csv
                                 multilingual score and token rows
  artifacts/omniscience_breakdown.csv
                                 Omniscience category rows

Run:
  python scrape.py            use cached RSC or HTML if present
  python scrape.py --refresh  re-download RSC, with HTML fallback
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://artificialanalysis.ai/models"
RSC_URL = f"{URL}?_rsc=1"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

ART = Path(__file__).parent / "artifacts"
HTML_PATH = ART / "models.html"
RSC_PATH = ART / "models.rsc"
JSON_PATH = ART / "models.json"
CSV_PATH = ART / "models.csv"
HOST_CSV_PATH = ART / "provider_endpoints.csv"
BENCHMARK_TOKENS_CSV_PATH = ART / "benchmark_token_counts.csv"
INDEX_COST_CSV_PATH = ART / "index_cost_by_evaluation.csv"
PROMPT_PERFORMANCE_CSV_PATH = ART / "prompt_performance.csv"
MULTILINGUAL_CSV_PATH = ART / "multilingual_scores.csv"
OMNISCIENCE_CSV_PATH = ART / "omniscience_breakdown.csv"
ENRICHED_CSV_PATH = ART / "models_enriched.csv"

# Minimum sanity bounds on a parse. If we come back below these the page
# structure changed or AA is half-broken. Refuse to overwrite the snapshot.
MIN_MODELS = 400
REQUIRED_KEYS = ("name", "slug", "intelligence_index", "model_creator_id")


def _decode_text(payload: bytes, content_encoding: str | None) -> str:
    if content_encoding == "gzip":
        payload = gzip.decompress(payload)
    elif content_encoding not in (None, "", "identity"):
        raise RuntimeError(f"unsupported response encoding {content_encoding!r}")
    return payload.decode("utf-8")


def _get_text(
    url: str,
    timeout: int = 60,
    headers: dict[str, str] | None = None,
) -> str:
    """Fetch text with a small retry loop for transient upstream failures."""
    transient_status = {502, 503, 504, 520, 521, 522, 524}
    last_error: Exception | None = None
    request_headers = {
        "User-Agent": UA,
        "Accept-Encoding": "gzip",
    }
    if headers:
        request_headers.update(headers)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return _decode_text(
                    response.read(),
                    response.headers.get("Content-Encoding"),
                )
        except urllib.error.HTTPError as exc:
            if exc.code not in transient_status:
                raise
            last_error = exc
        except urllib.error.URLError as exc:
            last_error = exc
        if attempt < 3:
            time.sleep(2 * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"failed to fetch {url}")


def fetch_html(refresh: bool) -> str:
    if HTML_PATH.exists() and not refresh:
        return HTML_PATH.read_text(encoding="utf-8")
    ART.mkdir(parents=True, exist_ok=True)
    print(f"GET {URL}")
    text = _get_text(URL)
    HTML_PATH.write_text(text, encoding="utf-8")
    print(f"  saved {len(text):,} chars -> {HTML_PATH}")
    return text


def fetch_rsc_stream(refresh: bool) -> str:
    if RSC_PATH.exists() and not refresh:
        return RSC_PATH.read_text(encoding="utf-8")
    if HTML_PATH.exists() and not refresh:
        return extract_rsc_stream(HTML_PATH.read_text(encoding="utf-8"))

    ART.mkdir(parents=True, exist_ok=True)
    try:
        print(f"GET {RSC_URL}")
        stream = _get_text(
            RSC_URL,
            headers={
                "Accept": "text/x-component",
                "Next-Router-Prefetch": "1",
                "RSC": "1",
            },
        )
        if _DEFAULT_DATA_RE.search(stream) is None:
            raise RuntimeError("direct RSC response did not contain defaultData")
    except Exception as exc:
        print(
            f"direct RSC fetch failed: {exc}; falling back to HTML",
            file=sys.stderr,
        )
        stream = extract_rsc_stream(fetch_html(refresh=True))

    RSC_PATH.write_text(stream, encoding="utf-8")
    print(f"  saved {len(stream):,} chars -> {RSC_PATH}")
    return stream


_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[(\d+),\s*"((?:[^"\\]|\\.)*)"\]\)', re.DOTALL)


def extract_rsc_stream(html: str) -> str:
    """Concatenate every kind=1 __next_f.push chunk into the raw RSC stream."""
    parts: list[str] = []
    for m in _CHUNK_RE.finditer(html):
        if m.group(1) != "1":
            continue
        parts.append(json.loads('"' + m.group(2) + '"'))
    if not parts:
        raise RuntimeError("No __next_f.push chunks found - page format changed?")
    return "".join(parts)


# Anchored: the model-list `defaultData` lives inside a component whose props
# include both `selectModelsByDefault` and `addToSelectedModels`. Requiring
# them adjacent kills any chance of latching onto an unrelated `defaultData`
# array AA might add elsewhere on the page later.
_DEFAULT_DATA_RE = re.compile(
    r'"addToSelectedModels":\s*"\$undefined"\s*,\s*"defaultData":\['
)


def find_default_data(stream: str, min_models: int = MIN_MODELS) -> list[dict]:
    """Locate the model-list array in the RSC stream and JSON-parse it.

    Anchored to a multi-key signature so an unrelated `defaultData` prop
    can't shadow us. Validates the parsed array's shape before returning.
    """
    m = _DEFAULT_DATA_RE.search(stream)
    if m is None:
        raise RuntimeError(
            "Anchored defaultData marker not found - AA page structure changed?"
        )
    start = m.end() - 1  # position of '['
    decoder = json.JSONDecoder()
    arr, _end = decoder.raw_decode(stream, start)
    if not isinstance(arr, list):
        raise RuntimeError(f"defaultData is not a list (got {type(arr).__name__})")

    # Schema gate: refuse to ship if the items don't look like model rows.
    if len(arr) < min_models:
        raise RuntimeError(
            f"Parsed only {len(arr)} models (expected >= {MIN_MODELS}). "
            f"Either AA shrank the catalog or we latched onto the wrong array."
        )
    first = arr[0] if arr else {}
    missing = [k for k in REQUIRED_KEYS if k not in first]
    if missing:
        raise RuntimeError(
            f"Parsed array's first item is missing expected keys {missing}. "
            f"We probably latched onto the wrong `defaultData`."
        )
    return arr


# Flat per-model columns for the CSV. The JSON file keeps every original field.
CSV_FIELDS = [
    # Identity
    "name",
    "short_name",
    "slug",
    "model_family_slug",
    "creator_name",
    "creator_slug",
    "model_creator_id",
    "release_date",
    "knowledge_cutoff_date",
    "deprecated",
    "deleted",
    "deprecated_to",
    # The two chart axes
    "intelligence_index",
    "intelligence_index_cost_usd",
    # Companion intelligence-index fields
    "intelligence_index_is_estimated",
    "estimated_intelligence_index",
    "intelligence_index_per_m_output_tokens",
    "intelligence_index_input_cost_usd",
    "intelligence_index_output_cost_usd",
    "intelligence_index_reasoning_cost_usd",
    # Total tokens AA needed to run the full Intelligence Index benchmark.
    # This is a token-usage metric, not a price field.
    "indexTokensTotal",
    # Composite sub-indexes
    "coding_index",
    "math_index",
    "agentic_index",
    # Individual benchmarks
    "gpqa",
    "hle",
    "mmlu_pro",
    "mmmu_pro",
    "livecodebench",
    "math_500",
    "aime",
    "aime25",
    "scicode",
    "humaneval",
    "tau2",
    "terminalbench_hard",
    "ifbench",
    "apex_agents",
    "lcr",
    "critpt",
    "gdpval",
    "gdpval_v2",
    "gdpval_normalized",
    "omniscience",
    "tau_banking",
    "terminalbench_v2_1",
    "it_bench_sre",
    "briefcase_normalized",
    # Pricing per 1M tokens, USD. AA publishes several blends; the
    # "_X_Y_1" names are AA-internal ratio identifiers, see their site.
    "price_1m_input_tokens",
    "price_1m_output_tokens",
    "price_1m_blended_0_100_1",
    "price_1m_blended_0_1_1",
    "price_1m_blended_0_3_1",
    "price_1m_blended_100_1_1",
    "price_1m_blended_7_2_1",
    "cache_hit_price",
    "cache_write_price",
    "cache_hit_rate",
    "cache_hit_discount_percent",
    "price_per_1k_1mp_images",
    "fallback_price_input",
    "fallback_price_output",
    "fallback_price_cache_hit",
    "fallback_price_cache_write",
    # Capability flags
    "reasoning_model",
    "reasoning_style",
    "reasoning_varied",
    "reasoning_starts_thinking_by_default",
    "reasoning_pass_back_reasoning",
    "frontier_model",
    "is_open_weights",
    "commercial_allowed",
    "input_modality_text",
    "input_modality_image",
    "input_modality_speech",
    "input_modality_video",
    "output_modality_text",
    "output_modality_image",
    "output_modality_speech",
    "output_modality_video",
    # Size & context
    "context_window_tokens",
    "context_window_formatted",
    "parameters_billions",
    "active_parameters_billions",
    "inference_parameters_active_billions",
    "size_class",
    "output_tokens",
    "model_id",
    "tokenizer_id",
    "display_order",
    "model_url",
    "hosts_url",
    "computed_performance_host_model_id",
    "performance_data_source_type",
    "performance_data_source_provider_name",
    "performance_data_source_provider_url",
    "show_host_model_evals",
    "open_source_categorization",
    "license_name",
    "license_url",
    "model_weights_source_url",
    "openness_index",
    "openness_model_availability",
    "openness_model_transparency",
    "openness_data_pretrain_access",
    "openness_data_pretrain_license",
    "openness_data_posttrain_access",
    "openness_data_posttrain_license",
    "training_tokens_trillions",
    # Measured response latency, seconds (AA's standardized run). Lower = faster.
    # For reasoning models both include thinking time, so they read slower.
    "ttft_seconds",
    "e2e_response_seconds",
    "intelligence_index_time_per_task_seconds",
    "index_compute",
    "output_speed_median_tokens_per_second",
    "output_speed_p05_tokens_per_second",
    "output_speed_p25_tokens_per_second",
    "output_speed_p75_tokens_per_second",
    "output_speed_p95_tokens_per_second",
    "ttfc_median_seconds",
    "ttfc_p05_seconds",
    "ttfc_p25_seconds",
    "ttfc_p75_seconds",
    "ttfc_p95_seconds",
    "ttfrc_median_seconds",
    "estimated_seconds_for_100_output_tokens_median",
    "canonical_answer_output_speed_median_tokens_per_second",
    # Intelligence Index v4.1 and detailed benchmark-run accounting.
    "intelligence_index_v4_1",
    "estimated_intelligence_index_v4_1",
    "index_input_tokens",
    "index_output_tokens",
    "index_answer_tokens",
    "index_reasoning_tokens",
    "index_answer_tokens_per_task",
    "index_reasoning_tokens_per_task",
    "index_output_tokens_per_task",
    "index_cost_per_task_usd",
    "index_input_cost_per_task_usd",
    "index_output_cost_per_task_usd",
    "index_cache_read_cost_per_task_usd",
    "index_cache_write_cost_per_task_usd",
    "index_reasoning_cost_per_task_usd",
    "index_answer_cost_per_task_usd",
    # Long-horizon and multilingual aggregates.
    "briefcase_elo",
    "briefcase_lower_95ci",
    "briefcase_upper_95ci",
    "briefcase_rubric_elo",
    "briefcase_analytical_quality_elo",
    "briefcase_presentation_elo",
    "briefcase_rubric_pass_rate",
    "briefcase_avg_turns_per_task",
    "briefcase_total_tool_calls",
    "briefcase_total_tool_ms",
    "briefcase_cost_total_usd",
    "briefcase_cost_input_usd",
    "briefcase_cost_non_cache_input_usd",
    "briefcase_cost_cache_read_usd",
    "briefcase_cost_cache_write_usd",
    "briefcase_cost_output_usd",
    "briefcase_cost_reasoning_usd",
    "briefcase_cost_answer_usd",
    "multilingual_average",
    "multilingual_average_global_mmlu_lite",
    "multilingual_average_mgsm",
    "multilingual_average_mmlu",
    # Lab-claimed scores are not AA-run benchmark results.
    "lab_claimed_gpqa",
    "lab_claimed_hle",
    "lab_claimed_mmlu_pro",
    "lab_claimed_math_500",
    "lab_claimed_livecodebench",
    "lab_claimed_aime",
    "lab_claimed_humaneval",
    # Representative non-index query accounting when AA publishes it.
    "representative_query_count",
    "representative_input_tokens",
    "representative_answer_tokens",
    "representative_output_tokens",
    "representative_reasoning_tokens",
    "representative_tokens_updated_at",
    "additional_text",
    # Prompt-length performance slices.
    "prompt_100k_output_speed_tokens_per_second",
    "prompt_100k_ttfc_seconds",
    "prompt_100k_ttft_seconds",
    "prompt_100k_e2e_response_seconds",
    "prompt_long_output_speed_tokens_per_second",
    "prompt_long_ttfc_seconds",
    "prompt_long_ttft_seconds",
    "prompt_long_e2e_response_seconds",
    "prompt_medium_output_speed_tokens_per_second",
    "prompt_medium_ttfc_seconds",
    "prompt_medium_ttft_seconds",
    "prompt_medium_e2e_response_seconds",
    "prompt_medium_coding_output_speed_tokens_per_second",
    "prompt_medium_coding_ttfc_seconds",
    "prompt_medium_coding_ttft_seconds",
    "prompt_medium_coding_e2e_response_seconds",
    "prompt_vision_single_image_output_speed_tokens_per_second",
    "prompt_vision_single_image_ttfc_seconds",
    "prompt_vision_single_image_ttft_seconds",
    "prompt_vision_single_image_e2e_response_seconds",
]


HOST_CSV_FIELDS = [
    "model_slug",
    "model_name",
    "model_creator_slug",
    "host_model_slug",
    "host_model_id",
    "host_api_id",
    "host_id",
    "host_model_string",
    "model_name_appendage",
    "price_1m_input_tokens",
    "price_1m_output_tokens",
    "cache_hit_price",
    "cache_write_price",
    "cache_storage_price_per_hour_per_1m_tokens",
    "host_cache_hit_rate",
    "price_per_1k_1mp_images",
    "context_window_if_different_to_model",
    "json_mode",
    "function_calling",
    "override_supports_images_input",
    "supports_images_input_note",
    "cache_pricing_notes",
    "image_input_pricing_notes",
    "gpqa_16x_min",
    "gpqa_16x_max",
    "gpqa_16x_quartile_25",
    "gpqa_16x_median",
    "gpqa_16x_quartile_75",
    "aime25_32x_min",
    "aime25_32x_max",
    "aime25_32x_quartile_25",
    "aime25_32x_median",
    "aime25_32x_quartile_75",
    "ifbench_8x_min",
    "ifbench_8x_max",
    "ifbench_8x_quartile_25",
    "ifbench_8x_median",
    "ifbench_8x_quartile_75",
]

BENCHMARK_TOKENS_CSV_FIELDS = [
    "model_slug",
    "model_name",
    "model_creator_slug",
    "benchmark",
    "input_tokens",
    "answer_tokens",
    "reasoning_tokens",
    "cacheable_input_tokens",
]

INDEX_COST_CSV_FIELDS = [
    "model_slug",
    "model_name",
    "model_creator_slug",
    "evaluation_slug",
    "weighted_cost_per_task_usd",
]

PROMPT_PERFORMANCE_CSV_FIELDS = [
    "model_slug",
    "model_name",
    "model_creator_slug",
    "prompt_length_type",
    "median_output_speed_tokens_per_second",
    "median_time_to_first_chunk_seconds",
    "median_time_to_first_reasoning_chunk_seconds",
    "median_estimated_total_seconds_for_100_output_tokens",
    "median_time_to_first_answer_token_seconds",
    "median_end_to_end_response_time_seconds",
]

MULTILINGUAL_CSV_FIELDS = [
    "model_slug",
    "model_name",
    "model_creator_slug",
    "language",
    "score",
    "input_tokens",
    "answer_tokens",
    "output_tokens",
    "reasoning_tokens",
    "total_input_tokens_api",
    "total_answer_tokens_api",
    "total_reasoning_tokens_api",
]

OMNISCIENCE_CSV_FIELDS = [
    "model_slug",
    "model_name",
    "model_creator_slug",
    "category",
    "subcategory",
    "split",
    "accuracy",
    "omniscience",
    "attempt_rate",
    "hallucination_rate",
    "non_hallucination_rate",
    "num_correct",
    "num_incorrect",
    "total_questions",
    "num_not_attempted",
    "num_partial_answer",
]

PROMPT_LENGTH_TYPES = [
    "100k",
    "long",
    "medium",
    "medium_coding",
    "vision_single_image",
]

PROMPT_LENGTH_METRICS = {
    "median_output_speed": "output_speed_tokens_per_second",
    "median_time_to_first_chunk": "ttfc_seconds",
    "median_time_to_first_answer_token": "ttft_seconds",
    "median_end_to_end_response_time": "e2e_response_seconds",
}


def _clean(v):
    """Coerce RSC sentinels ('$undefined', '$null', '$<hex>') to None.

    These appear because the React Server Component stream uses '$N' to mark
    references and '$undefined'/'$null' for missing values. None of our target
    fields legitimately start with '$', so this is safe.
    """
    if isinstance(v, str):
        if v.startswith("$"):
            return None
        if "\n" in v or "\r" in v:
            return " ".join(v.splitlines())
    return v


def _f(m: dict, key: str):
    return _clean(m.get(key))


def _d(v) -> dict:
    v = _clean(v)
    return v if isinstance(v, dict) else {}


def _identity(m: dict) -> dict:
    creators = _d(m.get("model_creators"))
    return {
        "model_slug": _f(m, "slug"),
        "model_name": _f(m, "name"),
        "model_creator_slug": _clean(creators.get("slug")),
    }


def _prompt_metrics(m: dict) -> dict:
    by_type = {
        item.get("prompt_length_type"): item
        for item in (_clean(m.get("performanceByPromptLength")) or [])
        if isinstance(item, dict)
    }
    out = {}
    for prompt_type in PROMPT_LENGTH_TYPES:
        item = _d(by_type.get(prompt_type))
        for raw_key, suffix in PROMPT_LENGTH_METRICS.items():
            out[f"prompt_{prompt_type}_{suffix}"] = _clean(item.get(raw_key))
    return out


def extra_fields(m: dict) -> dict:
    timescale = _d(m.get("timescaleData"))
    index_token_count = _d(m.get("canonicalIntelligenceIndexTokenCount"))
    index_tokens_per_task = _d(m.get("intelligenceIndexOutputTokensPerTask"))
    index_cost_per_task = _d(_d(m.get("intelligenceIndexCostPerTask")).get("cost"))
    briefcase = _d(m.get("briefcase"))
    briefcase_rubric = _d(briefcase.get("rubric"))
    briefcase_analytical = _d(briefcase.get("analyticalQuality"))
    briefcase_presentation = _d(briefcase.get("presentation"))
    briefcase_turns = _d(briefcase.get("turns"))
    briefcase_cost = _d(m.get("briefcaseCost"))
    multilingual = _d(m.get("multilingual_aa"))
    openness = _d(m.get("openness"))
    training = _d(m.get("training_information"))
    reasoning = _d(m.get("reasoning_properties"))
    representative = _d(m.get("representative_query_token_counts"))
    performance_source = _d(m.get("performanceDataSource"))
    fallback_price = _d(m.get("fallbackPrice"))

    return {
        "gdpval_v2": _f(m, "gdpval_v2"),
        "gdpval_normalized": _f(m, "gdpval_normalized"),
        "tau_banking": _f(m, "tau_banking"),
        "terminalbench_v2_1": _f(m, "terminalbench_v2_1"),
        "it_bench_sre": _f(m, "it_bench_sre"),
        "briefcase_normalized": _f(m, "briefcase_normalized"),
        "cache_write_price": _f(m, "cacheWritePrice"),
        "cache_hit_rate": _f(m, "cacheHitRate"),
        "cache_hit_discount_percent": _f(m, "cache_hit_discount_percent"),
        "price_per_1k_1mp_images": _f(m, "price_per_1k_1mp_images"),
        "fallback_price_input": _clean(fallback_price.get("input")),
        "fallback_price_output": _clean(fallback_price.get("output")),
        "fallback_price_cache_hit": _clean(fallback_price.get("cacheHit")),
        "fallback_price_cache_write": _clean(fallback_price.get("cacheWrite")),
        "reasoning_style": _clean(reasoning.get("style")),
        "reasoning_varied": _clean(reasoning.get("varied_reasoning")),
        "reasoning_starts_thinking_by_default": _clean(
            reasoning.get("starts_thinking_by_default")
        ),
        "reasoning_pass_back_reasoning": _clean(reasoning.get("pass_back_reasoning")),
        "output_tokens": _f(m, "output_tokens"),
        "model_id": _f(m, "id"),
        "tokenizer_id": _f(m, "tokenizer_id"),
        "display_order": _f(m, "display_order"),
        "model_url": _f(m, "model_url"),
        "hosts_url": _f(m, "hosts_url"),
        "computed_performance_host_model_id": _f(m, "computed_performance_host_model_id"),
        "performance_data_source_type": _clean(performance_source.get("type")),
        "performance_data_source_provider_name": _clean(
            performance_source.get("providerName")
        ),
        "performance_data_source_provider_url": _clean(
            performance_source.get("providerUrl")
        ),
        "show_host_model_evals": _f(m, "show_host_model_evals"),
        "open_source_categorization": _f(m, "open_source_categorization"),
        "license_name": _f(m, "license_name"),
        "license_url": _f(m, "license_url"),
        "model_weights_source_url": _f(m, "model_weights_source_url"),
        "openness_index": _clean(openness.get("opennessIndex")),
        "openness_model_availability": _clean(openness.get("modelAvailability")),
        "openness_model_transparency": _clean(openness.get("modelTransparency")),
        "openness_data_pretrain_access": _clean(openness.get("dataPretrainAccess")),
        "openness_data_pretrain_license": _clean(openness.get("dataPretrainLicense")),
        "openness_data_posttrain_access": _clean(openness.get("dataPosttrainAccess")),
        "openness_data_posttrain_license": _clean(openness.get("dataPosttrainLicense")),
        "training_tokens_trillions": _clean(training.get("training_tokens_trillions")),
        "intelligence_index_time_per_task_seconds": _f(m, "intelligenceIndexTimePerTask"),
        "index_compute": _f(m, "indexCompute"),
        "output_speed_median_tokens_per_second": _clean(timescale.get("median_output_speed")),
        "output_speed_p05_tokens_per_second": _clean(timescale.get("percentile_05_output_speed")),
        "output_speed_p25_tokens_per_second": _clean(timescale.get("quartile_25_output_speed")),
        "output_speed_p75_tokens_per_second": _clean(timescale.get("quartile_75_output_speed")),
        "output_speed_p95_tokens_per_second": _clean(timescale.get("percentile_95_output_speed")),
        "ttfc_median_seconds": _clean(timescale.get("median_time_to_first_chunk")),
        "ttfc_p05_seconds": _clean(timescale.get("percentile_05_time_to_first_chunk")),
        "ttfc_p25_seconds": _clean(timescale.get("quartile_25_time_to_first_chunk")),
        "ttfc_p75_seconds": _clean(timescale.get("quartile_75_time_to_first_chunk")),
        "ttfc_p95_seconds": _clean(timescale.get("percentile_95_time_to_first_chunk")),
        "ttfrc_median_seconds": _clean(timescale.get("median_time_to_first_reasoning_chunk")),
        "estimated_seconds_for_100_output_tokens_median": _clean(
            timescale.get("median_estimated_total_seconds_for_100_output_tokens")
        ),
        "canonical_answer_output_speed_median_tokens_per_second": _clean(
            timescale.get("median_canonical_answer_output_speed")
        ),
        "intelligence_index_v4_1": _f(m, "intelligence_index_v4_1"),
        "estimated_intelligence_index_v4_1": _f(m, "estimated_intelligence_index_v4_1"),
        "index_input_tokens": _clean(index_token_count.get("input")),
        "index_output_tokens": _clean(index_token_count.get("output")),
        "index_answer_tokens": _clean(index_token_count.get("answer")),
        "index_reasoning_tokens": _clean(index_token_count.get("reasoning")),
        "index_answer_tokens_per_task": _clean(index_tokens_per_task.get("answer")),
        "index_reasoning_tokens_per_task": _clean(index_tokens_per_task.get("reasoning")),
        "index_output_tokens_per_task": _clean(index_tokens_per_task.get("output")),
        "index_cost_per_task_usd": _clean(index_cost_per_task.get("total")),
        "index_input_cost_per_task_usd": _clean(index_cost_per_task.get("input")),
        "index_output_cost_per_task_usd": _clean(index_cost_per_task.get("output")),
        "index_cache_read_cost_per_task_usd": _clean(index_cost_per_task.get("cacheRead")),
        "index_cache_write_cost_per_task_usd": _clean(index_cost_per_task.get("cacheWrite")),
        "index_reasoning_cost_per_task_usd": _clean(index_cost_per_task.get("reasoning")),
        "index_answer_cost_per_task_usd": _clean(index_cost_per_task.get("answer")),
        "briefcase_elo": _clean(briefcase.get("elo")),
        "briefcase_lower_95ci": _clean(briefcase.get("lower95ci")),
        "briefcase_upper_95ci": _clean(briefcase.get("upper95ci")),
        "briefcase_rubric_elo": _clean(briefcase_rubric.get("elo")),
        "briefcase_analytical_quality_elo": _clean(briefcase_analytical.get("elo")),
        "briefcase_presentation_elo": _clean(briefcase_presentation.get("elo")),
        "briefcase_rubric_pass_rate": _clean(briefcase.get("rubricPassRate")),
        "briefcase_avg_turns_per_task": _clean(briefcase_turns.get("avgPerTask")),
        "briefcase_total_tool_calls": _clean(briefcase.get("totalToolCalls")),
        "briefcase_total_tool_ms": _clean(briefcase.get("totalToolMs")),
        "briefcase_cost_total_usd": _clean(briefcase_cost.get("total")),
        "briefcase_cost_input_usd": _clean(briefcase_cost.get("input")),
        "briefcase_cost_non_cache_input_usd": _clean(briefcase_cost.get("nonCacheInput")),
        "briefcase_cost_cache_read_usd": _clean(briefcase_cost.get("cacheRead")),
        "briefcase_cost_cache_write_usd": _clean(briefcase_cost.get("cacheWrite")),
        "briefcase_cost_output_usd": _clean(briefcase_cost.get("output")),
        "briefcase_cost_reasoning_usd": _clean(briefcase_cost.get("reasoning")),
        "briefcase_cost_answer_usd": _clean(briefcase_cost.get("answer")),
        "multilingual_average": _clean(multilingual.get("average")),
        "multilingual_average_global_mmlu_lite": _clean(
            multilingual.get("average_global_mmlu_lite")
        ),
        "multilingual_average_mgsm": _clean(multilingual.get("average_mgsm")),
        "multilingual_average_mmlu": _clean(multilingual.get("average_mmlu")),
        "lab_claimed_gpqa": _f(m, "lab_claimed_gpqa"),
        "lab_claimed_hle": _f(m, "lab_claimed_hle"),
        "lab_claimed_mmlu_pro": _f(m, "lab_claimed_mmlu_pro"),
        "lab_claimed_math_500": _f(m, "lab_claimed_math_500"),
        "lab_claimed_livecodebench": _f(m, "lab_claimed_livecodebench"),
        "lab_claimed_aime": _f(m, "lab_claimed_aime"),
        "lab_claimed_humaneval": _f(m, "lab_claimed_humaneval"),
        "representative_query_count": _clean(representative.get("n_queries")),
        "representative_input_tokens": _clean(representative.get("input_tokens")),
        "representative_answer_tokens": _clean(representative.get("answer_tokens")),
        "representative_output_tokens": _clean(representative.get("output_tokens")),
        "representative_reasoning_tokens": _clean(representative.get("reasoning_tokens")),
        "representative_tokens_updated_at": _clean(representative.get("updated_at")),
        "additional_text": _f(m, "additional_text"),
        **_prompt_metrics(m),
    }


def _pos(v):
    """Latency sentinel: AA reports an all-zero metrics dict for models it
    hasn't benchmarked for speed. A real run always has input_time > 0, so a
    non-positive total_time means 'not measured'. Return None, not 0."""
    v = _clean(v)
    try:
        return v if v is not None and float(v) > 0 else None
    except (TypeError, ValueError):
        return None


def previous_model_count() -> int | None:
    """Return prior tracked row count for the catastrophic-drop guard."""
    snapshot = ENRICHED_CSV_PATH if ENRICHED_CSV_PATH.exists() else CSV_PATH
    if not snapshot.exists():
        return None
    try:
        with snapshot.open(encoding="utf-8", newline="") as handle:
            return sum(1 for _row in csv.DictReader(handle))
    except (OSError, csv.Error):
        return None


def flatten(m: dict) -> dict:
    creators = m.get("model_creators") or {}
    cost = _clean(m.get("intelligence_index_cost")) or {}
    if not isinstance(cost, dict):
        cost = {}
    ttft = _clean(m.get("time_to_first_answer_token_metrics")) or {}
    if not isinstance(ttft, dict):
        ttft = {}
    e2e = _clean(m.get("end_to_end_response_time_metrics")) or {}
    if not isinstance(e2e, dict):
        e2e = {}
    # The "_3_1" blended ratio isn't directly exposed; price_1m_blended_7_2_1
    # is the closest standard ratio AA publishes. Keep the raw fields they expose.
    return {
        "name": _f(m, "name"),
        "short_name": _f(m, "short_name"),
        "slug": _f(m, "slug"),
        "model_family_slug": _f(m, "model_family_slug"),
        "creator_name": _clean(creators.get("name")),
        "creator_slug": _clean(creators.get("slug")),
        "model_creator_id": _f(m, "model_creator_id"),
        "release_date": _f(m, "release_date"),
        "knowledge_cutoff_date": _f(m, "knowledge_cutoff_date"),
        "deprecated": _f(m, "deprecated"),
        "deleted": _f(m, "deleted"),
        "deprecated_to": _f(m, "deprecated_to"),

        "intelligence_index": _f(m, "intelligence_index"),
        "intelligence_index_cost_usd": _clean(cost.get("total_cost")),
        "intelligence_index_is_estimated": _f(m, "intelligence_index_is_estimated"),
        "estimated_intelligence_index": _f(m, "estimated_intelligence_index"),
        "intelligence_index_per_m_output_tokens": _f(m, "intelligence_index_per_m_output_tokens"),
        "intelligence_index_input_cost_usd": _clean(cost.get("input_cost")),
        "intelligence_index_output_cost_usd": _clean(cost.get("output_cost")),
        "intelligence_index_reasoning_cost_usd": _clean(cost.get("reasoning_cost")),
        "indexTokensTotal": _f(m, "indexTokensTotal"),

        "coding_index": _f(m, "coding_index"),
        "math_index": _f(m, "math_index"),
        "agentic_index": _f(m, "agentic_index"),

        "gpqa": _f(m, "gpqa"),
        "hle": _f(m, "hle"),
        "mmlu_pro": _f(m, "mmlu_pro"),
        "mmmu_pro": _f(m, "mmmu_pro"),
        "livecodebench": _f(m, "livecodebench"),
        "math_500": _f(m, "math_500"),
        "aime": _f(m, "aime"),
        "aime25": _f(m, "aime25"),
        "scicode": _f(m, "scicode"),
        "humaneval": _f(m, "humaneval"),
        "tau2": _f(m, "tau2"),
        "terminalbench_hard": _f(m, "terminalbench_hard"),
        "ifbench": _f(m, "ifbench"),
        "apex_agents": _f(m, "apex_agents"),
        "lcr": _f(m, "lcr"),
        "critpt": _f(m, "critpt"),
        "gdpval": _f(m, "gdpval"),
        "omniscience": _f(m, "omniscience"),

        "price_1m_input_tokens": _f(m, "price_1m_input_tokens"),
        "price_1m_output_tokens": _f(m, "price_1m_output_tokens"),
        "price_1m_blended_0_100_1": _f(m, "price_1m_blended_0_100_1"),
        "price_1m_blended_0_1_1": _f(m, "price_1m_blended_0_1_1"),
        "price_1m_blended_0_3_1": _f(m, "price_1m_blended_0_3_1"),
        "price_1m_blended_100_1_1": _f(m, "price_1m_blended_100_1_1"),
        "price_1m_blended_7_2_1": _f(m, "price_1m_blended_7_2_1"),
        "cache_hit_price": _f(m, "cache_hit_price"),

        "reasoning_model": _f(m, "reasoning_model"),
        "frontier_model": _f(m, "frontier_model"),
        "is_open_weights": _f(m, "is_open_weights"),
        "commercial_allowed": _f(m, "commercial_allowed"),
        "input_modality_text": _f(m, "input_modality_text"),
        "input_modality_image": _f(m, "input_modality_image"),
        "input_modality_speech": _f(m, "input_modality_speech"),
        "input_modality_video": _f(m, "input_modality_video"),
        "output_modality_text": _f(m, "output_modality_text"),
        "output_modality_image": _f(m, "output_modality_image"),
        "output_modality_speech": _f(m, "output_modality_speech"),
        "output_modality_video": _f(m, "output_modality_video"),

        "context_window_tokens": _f(m, "context_window_tokens"),
        "context_window_formatted": _f(m, "contextWindowFormatted"),
        "parameters_billions": _f(m, "parameters"),
        "active_parameters_billions": _f(m, "activeParams"),
        "inference_parameters_active_billions": _f(
            m,
            "inference_parameters_active_billions",
        ),
        "size_class": _f(m, "size_class"),

        "ttft_seconds": _pos(ttft.get("total_time")),
        "e2e_response_seconds": _pos(e2e.get("total_time")),
        **extra_fields(m),
    }


def flatten_host_models(models: list[dict]) -> list[dict]:
    rows = []
    for m in models:
        creators = _d(m.get("model_creators"))
        for h in _clean(m.get("host_models")) or []:
            if not isinstance(h, dict) or h.get("deleted"):
                continue
            host_cache = _d(h.get("host_model_cache_hit_rate"))
            gpqa = _d(h.get("gpqa_16x"))
            aime25 = _d(h.get("aime25_32x"))
            ifbench = _d(h.get("ifbench_8x"))
            rows.append({
                "model_slug": _f(m, "slug"),
                "model_name": _f(m, "name"),
                "model_creator_slug": _clean(creators.get("slug")),
                "host_model_slug": _f(h, "slug"),
                "host_model_id": _f(h, "id"),
                "host_api_id": _f(h, "host_api_id"),
                "host_id": _f(h, "host_id"),
                "host_model_string": _f(h, "host_model_string"),
                "model_name_appendage": _f(h, "model_name_appendage"),
                "price_1m_input_tokens": _f(h, "price_1m_input_tokens"),
                "price_1m_output_tokens": _f(h, "price_1m_output_tokens"),
                "cache_hit_price": _f(h, "cache_hit_price"),
                "cache_write_price": _f(h, "cache_write_price"),
                "cache_storage_price_per_hour_per_1m_tokens": _f(
                    h,
                    "cache_storage_price_per_hour_per_1m_tokens",
                ),
                "host_cache_hit_rate": _clean(host_cache.get("cache_hit_rate")),
                "price_per_1k_1mp_images": _f(h, "price_per_1k_1mp_images"),
                "context_window_if_different_to_model": _f(
                    h,
                    "context_window_if_different_to_model",
                ),
                "json_mode": _f(h, "json_mode"),
                "function_calling": _f(h, "function_calling"),
                "override_supports_images_input": _f(h, "override_supports_images_input"),
                "supports_images_input_note": _f(h, "supports_images_input_note"),
                "cache_pricing_notes": _f(h, "cache_pricing_notes"),
                "image_input_pricing_notes": _f(h, "image_input_pricing_notes"),
                "gpqa_16x_min": _clean(gpqa.get("min")),
                "gpqa_16x_max": _clean(gpqa.get("max")),
                "gpqa_16x_quartile_25": _clean(gpqa.get("quartile_25")),
                "gpqa_16x_median": _clean(gpqa.get("median")),
                "gpqa_16x_quartile_75": _clean(gpqa.get("quartile_75")),
                "aime25_32x_min": _clean(aime25.get("min")),
                "aime25_32x_max": _clean(aime25.get("max")),
                "aime25_32x_quartile_25": _clean(aime25.get("quartile_25")),
                "aime25_32x_median": _clean(aime25.get("median")),
                "aime25_32x_quartile_75": _clean(aime25.get("quartile_75")),
                "ifbench_8x_min": _clean(ifbench.get("min")),
                "ifbench_8x_max": _clean(ifbench.get("max")),
                "ifbench_8x_quartile_25": _clean(ifbench.get("quartile_25")),
                "ifbench_8x_median": _clean(ifbench.get("median")),
                "ifbench_8x_quartile_75": _clean(ifbench.get("quartile_75")),
            })
    return rows


def flatten_benchmark_token_counts(models: list[dict]) -> list[dict]:
    rows = []
    for m in models:
        identity = _identity(m)
        counts = _d(m.get("canonical_eval_token_counts"))
        for benchmark, values in sorted(counts.items()):
            values = _d(values)
            rows.append({
                **identity,
                "benchmark": benchmark,
                "input_tokens": _clean(values.get("input")),
                "answer_tokens": _clean(values.get("answer")),
                "reasoning_tokens": _clean(values.get("reasoning")),
                "cacheable_input_tokens": _clean(values.get("cacheable_input")),
            })
    return rows


def flatten_index_costs(models: list[dict]) -> list[dict]:
    rows = []
    for m in models:
        identity = _identity(m)
        costs = _d(m.get("intelligenceIndexCostPerTask"))
        for item in costs.get("evaluations") or []:
            if not isinstance(item, dict):
                continue
            rows.append({
                **identity,
                "evaluation_slug": _clean(item.get("slug")),
                "weighted_cost_per_task_usd": _clean(
                    item.get("weightedCostPerTask")
                ),
            })
    return rows


def flatten_prompt_performance(models: list[dict]) -> list[dict]:
    rows = []
    for m in models:
        identity = _identity(m)
        for item in _clean(m.get("performanceByPromptLength")) or []:
            if not isinstance(item, dict):
                continue
            rows.append({
                **identity,
                "prompt_length_type": _clean(item.get("prompt_length_type")),
                "median_output_speed_tokens_per_second": _clean(
                    item.get("median_output_speed")
                ),
                "median_time_to_first_chunk_seconds": _clean(
                    item.get("median_time_to_first_chunk")
                ),
                "median_time_to_first_reasoning_chunk_seconds": _clean(
                    item.get("median_time_to_first_reasoning_chunk")
                ),
                "median_estimated_total_seconds_for_100_output_tokens": _clean(
                    item.get("median_estimated_total_seconds_for_100_output_tokens")
                ),
                "median_time_to_first_answer_token_seconds": _clean(
                    item.get("median_time_to_first_answer_token")
                ),
                "median_end_to_end_response_time_seconds": _clean(
                    item.get("median_end_to_end_response_time")
                ),
            })
    return rows


def flatten_multilingual_scores(models: list[dict]) -> list[dict]:
    rows = []
    for m in models:
        identity = _identity(m)
        multilingual = _d(m.get("multilingual_aa"))
        for language, values in sorted(multilingual.items()):
            values = _d(values)
            if "score" not in values:
                continue
            rows.append({
                **identity,
                "language": language,
                "score": _clean(values.get("score")),
                "input_tokens": _clean(values.get("input_tokens")),
                "answer_tokens": _clean(values.get("answer_tokens")),
                "output_tokens": _clean(values.get("output_tokens")),
                "reasoning_tokens": _clean(values.get("reasoning_tokens")),
                "total_input_tokens_api": _clean(values.get("total_input_tokens_api")),
                "total_answer_tokens_api": _clean(values.get("total_answer_tokens_api")),
                "total_reasoning_tokens_api": _clean(
                    values.get("total_reasoning_tokens_api")
                ),
            })
    return rows


def _omniscience_metric_row(identity: dict, path: list[str], split: str, values: dict):
    return {
        **identity,
        "category": path[0] if path else "",
        "subcategory": "/".join(path[1:]),
        "split": split,
        "accuracy": _clean(values.get("accuracy")),
        "omniscience": _clean(values.get("omniscience")),
        "attempt_rate": _clean(values.get("attempt_rate")),
        "hallucination_rate": _clean(values.get("hallucination_rate")),
        "non_hallucination_rate": _clean(values.get("non_hallucination_rate")),
        "num_correct": _clean(values.get("num_correct")),
        "num_incorrect": _clean(values.get("num_incorrect")),
        "total_questions": _clean(values.get("total_questions")),
        "num_not_attempted": _clean(values.get("num_not_attempted")),
        "num_partial_answer": _clean(values.get("num_partial_answer")),
    }


def _collect_omniscience_rows(identity: dict, path: list[str], node, rows: list[dict]):
    node = _clean(node)
    if not isinstance(node, dict):
        return
    if "accuracy" in node:
        rows.append(_omniscience_metric_row(identity, path, "", node))
        return
    total = node.get("total")
    if isinstance(total, dict) and "accuracy" in total:
        rows.append(_omniscience_metric_row(identity, path, "total", total))
    for key, value in sorted(node.items()):
        if key == "total":
            continue
        _collect_omniscience_rows(identity, [*path, key], value, rows)


def flatten_omniscience_breakdown(models: list[dict]) -> list[dict]:
    rows = []
    for m in models:
        identity = _identity(m)
        breakdown = _d(m.get("omniscience_breakdown"))
        for category, values in sorted(breakdown.items()):
            _collect_omniscience_rows(identity, [category], values, rows)
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path} ({path.stat().st_size:,} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch the AA payload")
    args = ap.parse_args()

    stream = fetch_rsc_stream(args.refresh)
    models = find_default_data(stream)
    print(f"Parsed {len(models)} models from defaultData")

    # Catastrophic-drop guard: if we already have a known-good tracked CSV and
    # the new parse comes back with <80% of that count, refuse to overwrite.
    # Almost always means AA changed page structure and we're parsing garbage.
    prior_count = previous_model_count()
    if prior_count:
        ratio = len(models) / prior_count
        if ratio < 0.8:
            print(
                f"ABORT: parsed {len(models)} models, previous snapshot "
                f"had {prior_count} ({ratio:.0%}). Refusing to overwrite. "
                f"Investigate before re-running.",
                file=sys.stderr,
            )
            return 2

    ART.mkdir(parents=True, exist_ok=True)

    JSON_PATH.write_text(
        json.dumps(models, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote {JSON_PATH} ({JSON_PATH.stat().st_size:,} bytes)")

    rows = [flatten(m) for m in models]
    write_csv(CSV_PATH, CSV_FIELDS, rows)
    write_csv(HOST_CSV_PATH, HOST_CSV_FIELDS, flatten_host_models(models))
    write_csv(
        BENCHMARK_TOKENS_CSV_PATH,
        BENCHMARK_TOKENS_CSV_FIELDS,
        flatten_benchmark_token_counts(models),
    )
    write_csv(INDEX_COST_CSV_PATH, INDEX_COST_CSV_FIELDS, flatten_index_costs(models))
    write_csv(
        PROMPT_PERFORMANCE_CSV_PATH,
        PROMPT_PERFORMANCE_CSV_FIELDS,
        flatten_prompt_performance(models),
    )
    write_csv(MULTILINGUAL_CSV_PATH, MULTILINGUAL_CSV_FIELDS, flatten_multilingual_scores(models))
    write_csv(
        OMNISCIENCE_CSV_PATH,
        OMNISCIENCE_CSV_FIELDS,
        flatten_omniscience_breakdown(models),
    )

    # Spot-check a few chart-visible models against the screenshot.
    print("\n--- Spot checks against the Intelligence-vs-Cost chart ---")
    targets = [
        "claude-opus-4-7",
        "gpt-5-4-xhigh",
        "gpt-5-5-xhigh",
        "deepseek-v3-2",
        "gemini-3-5-flash",
    ]
    by_slug = {r["slug"]: r for r in rows if r.get("slug")}
    for slug in targets:
        r = by_slug.get(slug)
        if not r:
            print(f"  {slug}: NOT FOUND")
            continue
        print(
            f"  {r['name']:55s}  index={r['intelligence_index']!s:>6}  "
            f"cost=${r['intelligence_index_cost_usd']!s:>10}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
