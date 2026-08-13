# Step 0: Emit Token Cost Allocation records from OpenAI and Anthropic

[Custom LLM Telemetry Enrichment](https://docs.vantage.sh/custom_telemetry) uses the **Token Cost Allocation Specification**: write one JSON record per LLM request to an S3 bucket you own, and Vantage splits the matching provider bill across the tags those records carry (team, feature, customer, and so on). The docs pick up once you already have records in that schema. This demo is Step 0 — starting from an API key, capture usage from each call and produce spec-conformant `YYYY/MM/DD/*.jsonl.gz` objects Vantage can read.

Three files:

- `emitter.py` builds Token Cost Allocation records from raw API responses, validates them, and writes date-partitioned gzipped NDJSON. The mapping functions are pure and copy-paste portable.
- `openai_cold_start.py` and `anthropic_cold_start.py` are complete worked examples: one API call, one record, one object.

## Prerequisites

- A Vantage account with your OpenAI and/or Anthropic cost integration connected. Enrichment splits the real bill; no bill connected, nothing to split.
- Python 3.9+.
- For the real-bucket step only: an S3 bucket you own, AWS credentials with `s3:PutObject` on it, and `pip install boto3`.

## Quick start

Dry run first. Without a bucket configured, records land in `./out` so you can see exactly what Vantage would receive:

```bash
pip install openai
export OPENAI_API_KEY=sk-proj-...
python3 openai_cold_start.py
```

```bash
gunzip -c out/llm/*/*/*/*.jsonl.gz
```

You should see one JSON line per request. These two lines are genuine output from running both scripts (response ids truncated):

```json
{"event_id": "chatcmpl-EC870XwPBvp9wTb...", "timestamp": "2026-08-12T18:37:06.904876Z", "provider": "openai", "model": "gpt-4o-2024-08-06", "usage": {"input_tokens": 13, "output_tokens": 7}, "service_tier": "priority", "tags": {"team": "growth", "purpose": "cold-start-demo"}}
{"event_id": "msg_011CdyLe2wDgAWvjmX...", "timestamp": "2026-08-12T18:37:19.505301Z", "provider": "anthropic", "model": "claude-sonnet-4-6", "usage": {"input_tokens": 13, "output_tokens": 11}, "tags": {"team": "growth", "purpose": "cold-start-demo"}}
```

Worth noticing: the model is the provider's resolved id (`gpt-4o` resolved to a dated snapshot), and the OpenAI record picked up `service_tier` straight off the live response. Both matter later, because Vantage joins records to your bill by model, and OpenAI costs are tier-priced.

Then write to a real bucket:

```bash
pip install boto3
export VANTAGE_TELEMETRY_BUCKET=my-llm-telemetry-bucket
python3 openai_cold_start.py
```

Connect it in Vantage:

1. On the [Integrations page](https://console.vantage.sh/settings/integrations), add a **Custom LLM Enrichment Source** and pick your bucket.
2. Enter `llm` as the prefix. That is where the writer puts objects. (Different prefix? Pass `prefix=` to `TelemetryWriter` to match.)
3. Apply the read-only grant the flow gives you (CloudFormation, CLI, or Terraform; it attaches to your existing Vantage cross-account AWS role — no new role or credentials), then click **Check Permissions**.

The Anthropic variant is identical with `pip install anthropic` and `ANTHROPIC_API_KEY`.

## What a record looks like

One JSON object per request, matching the Token Cost Allocation Specification:

```json
{
  "event_id": "chatcmpl-AbC123",
  "timestamp": "2026-08-12T12:30:45.123456Z",
  "provider": "openai",
  "model": "gpt-4o-2024-08-06",
  "service_tier": "default",
  "usage": {
    "input_tokens": 2129,
    "output_tokens": 112,
    "cache_read_input_tokens": 572
  },
  "tags": {"team": "growth", "purpose": "cold-start-demo"}
}
```

The tags are the whole point. They become cost dimensions in Vantage, so you can group, filter, budget, and alert by `team` or `purpose` like any other tag.

**`resource_account_id`.** Recommended whenever one bucket carries logs for multiple integrations of the same provider, so each request matches the right costs (for example an OpenAI project or org id). Records are plain dicts — set it before `writer.add()`:

```python
record["resource_account_id"] = "proj_abc123"
```

See the schema section in the [Custom Telemetry docs](https://docs.vantage.sh/custom_telemetry) for the full field list.

## The mapping, and the one trap

OpenAI maps straight through. `usage.prompt_tokens` already includes cached tokens, which is the inclusive total the spec expects; `prompt_tokens_details.cached_tokens` becomes `cache_read_input_tokens`, and `response.id` is a ready-made `event_id`.

Anthropic has the trap. Its `usage.input_tokens` EXCLUDES cached tokens, so the spec total must be reassembled:

```
spec input_tokens = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
```

Send Anthropic's raw `input_tokens` and the cache-priced portion of your spend is misallocated. `record_from_anthropic` does the addition; `test_emitter.py` pins it.

## What you'll see in Vantage

Enrichment runs with your provider's regular cost refresh. Expect your tag keys in Cost Report filters within about a day of connecting, not minutes. Late records are fine: recent days are reprocessed on a rolling three-day window.

A single demo record will render as a near-invisible sliver next to the untagged remainder of that day's real spend. That is expected; coverage grows as you instrument real traffic. Costs with no matching telemetry pass through unchanged, and partially covered days show an untagged leftover row, so totals always reconcile against the bill.

If splits are missing after a refresh cycle, the usual causes are skipped records (see the validation table below), a prefix mismatch between the writer and the source configuration, or a missing provider cost integration. The [troubleshooting docs](https://docs.vantage.sh/custom_telemetry) cover the rest.

---

# Going further

Everything below is for taking the demo into a real codebase.

## Streaming calls

Production apps stream, and streamed responses deliver usage differently. The mapping functions need no changes; the work is getting a complete usage object out of the stream.

OpenAI only sends usage if you ask, on a final extra chunk whose `choices` list is empty:

```python
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    stream=True,
    stream_options={"include_usage": True},  # required, or usage never arrives
)
final_usage = None
for chunk in stream:
    event_id, model = chunk.id, chunk.model   # identical on every chunk
    # ...render chunk.choices deltas...
    if chunk.usage is not None:               # only the final chunk carries usage
        final_usage = chunk.usage

if final_usage is not None:                   # aborted streams have no usage: skip
    record = record_from_openai(
        {"id": event_id, "model": model, "usage": final_usage.model_dump()},
        timestamp=utc_now_iso(),
        tags={"team": "growth"},
    )
```

Note: the SDK's `client.chat.completions.stream()` helper does NOT set `include_usage` for you. Pass `stream_options` there too, then use `stream.get_final_completion().model_dump()`. On the Responses API, the `response.completed` event carries the full response, so `record_from_openai(event.response.model_dump(), ...)` works as-is.

Anthropic's SDK does the merge for you:

```python
with client.messages.stream(model="claude-sonnet-4-6", max_tokens=1024,
                            messages=messages) as stream:
    for text in stream.text_stream:
        ...  # render incrementally
    message = stream.get_final_message()

record = record_from_anthropic(message.model_dump(), timestamp=utc_now_iso(),
                               tags={"team": "growth"})
```

One rule for both providers: do not emit a record from an aborted stream. OpenAI never delivers usage for it, and Anthropic's snapshot would carry a 1-to-3-token partial output count that skews the proportional split.

## Where this goes in a real codebase

Nobody adds three lines after every call site. Pick the single choke point your LLM traffic already flows through and record there: a shared completion helper or client factory if you have one, otherwise a thin wrapper around the SDK call:

```python
def recorded(create: Callable, writer: TelemetryWriter,
             tags: dict | None = None) -> Callable:
    """Wrap an SDK create call so every completion emits a telemetry record."""
    def wrapped(*args: object, **kwargs: object) -> object:
        response = create(*args, **kwargs)
        try:
            writer.add(record_from_openai(response.model_dump(), utc_now_iso(), tags))
        except Exception:
            log.warning("telemetry record dropped", exc_info=True)
        return response
    return wrapped

chat = recorded(client.chat.completions.create, writer, {"team": "growth"})
```

The `try/except` is not optional decoration: telemetry must never break the serving path. An odd provider response should cost you one record, not a 500.

Async works the same way. `AsyncOpenAI` and `AsyncAnthropic` return the same response types, so the pure mapping functions are shared unchanged. Keep the S3 flush off the event loop (`asyncio.to_thread(writer.flush)` or a background thread), and flush on shutdown via your framework's lifespan hook or `atexit`.

## Validation before you connect

`validate_record` returns every reason Vantage would skip a record, so a bad pipeline fails in your terminal instead of silently in ingestion. The rules:

| Record property | Verdict |
|---|---|
| `event_id`, `timestamp`, `provider`, `model`, `usage` present and non-empty | required, or the record is skipped |
| `timestamp` as ISO 8601 UTC with an explicit `Z` | epoch numbers are rejected |
| `provider` one of `openai`, `anthropic`, `aws`/`bedrock`, `gcp`/`gemini`/`google`/`vertex`, `azure`/`azure_openai` | anything else is skipped |
| usage counts as JSON integers | string counts like `"2129"` are dropped by ingestion |
| at least one usage field a positive integer | all-zero usage is skipped |
| `status` absent or `success` | any other value skips the record |
| `uncached_input_tokens` omitted | Vantage derives it; a malformed explicit value silently drops the input row |

Run the checks yourself: `python3 test_emitter.py` (stdlib only).

## Production notes

- **Batching.** One object per request is the anti-pattern; buffer and flush on thresholds. Reasonable defaults: ~1,000 records or ~60 seconds, whichever comes first, and always at shutdown. Multiple web workers each holding their own writer is fine: object names are uuid-suffixed so keys never collide, and Vantage dedups per `event_id` per day.
- **Failure semantics, stated honestly.** The buffer is in memory; a crash loses whatever was not yet flushed. That is usually acceptable here, because lost telemetry degrades allocation precision, never billing accuracy: uncovered spend lands in the untagged leftover row and totals still reconcile. If you need better, spool records to local disk first. `flush()` is safe to retry: a partial failure keeps the buffer, and re-written days deduplicate by `event_id`.
- **Retries are already safe.** Re-sending the same records is harmless: Vantage keeps one record per `event_id` per day.
- **Timestamps.** The writer partitions by the record timestamp's UTC date. The timestamp is when you received the response; if you backfill from stored responses, convert the response's own `created` time (OpenAI) or your logged receipt time instead of `now()`.
- **Tags hygiene.** Prefer stable, low-cardinality keys (`team`, `environment`, `purpose`). Keep request ids, user emails, and conversation ids out of `tags`; they are high-cardinality and some are PII. Tags are case-sensitive (`team` ≠ `Team`). Never put API keys or secrets in any field.
- **`resource_account_id`.** Set it when one bucket serves multiple accounts of the same provider so each request joins the right bill (see the callout under [What a record looks like](#what-a-record-looks-like)). Other optional top-level fields (`provider_region`, `api_key_id`, `is_batch`, …) work the same way: assign on the dict before `writer.add()`.

## Other providers and languages

This demo maps the direct OpenAI and Anthropic APIs, in Python. Azure OpenAI responses are shape-compatible with `record_from_openai`; set `provider` to `azure_openai` so records match the billed integration. Bedrock and Vertex use different response field names and are not mapped here. The record example, the validation table, and the Anthropic formula are the language-neutral spec: porting the two mapping functions to another provider or language (TypeScript, Go) is a ~30-line exercise against that table.
