"""One Anthropic call, one Vantage token allocation record, shipped.

Requires ANTHROPIC_API_KEY. Set VANTAGE_TELEMETRY_BUCKET to write to S3;
without it, records land in ./out for inspection.
"""
from __future__ import annotations

import os

from anthropic import Anthropic

from emitter import TelemetryWriter, record_from_anthropic, utc_now_iso


def main() -> None:
    """Call Anthropic once and write the resulting record as spec .jsonl.gz."""
    response = Anthropic().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=64,
        messages=[{"role": "user", "content": "Say hello in five words."}],
    )
    record = record_from_anthropic(
        response.model_dump(),
        timestamp=utc_now_iso(),
        tags={"team": "growth", "purpose": "cold-start-demo"},
    )

    bucket = os.environ.get("VANTAGE_TELEMETRY_BUCKET")
    writer = TelemetryWriter(bucket, dry_run_dir=None if bucket else "out")
    writer.add(record)
    print("wrote:", *writer.flush())


if __name__ == "__main__":
    main()
