"""Plan and resume original Bedrock logging buckets with a central replication copy."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from botocore.exceptions import BotoCoreError, ClientError

from bedrock_demo.aws.deployment import describe_owned_stack, inspect_unit, start_or_resume_stack
from bedrock_demo.core.deployment import (
    TEMPLATE_NAMES,
    config_problems,
    deployment_units,
    manifest_problems,
    new_manifest,
    original_bucket_handoff,
    resolved_parameters,
    template_hashes,
)

DEMO_ROOT = Path(__file__).resolve().parents[2]
RUNNING = ("CREATE_IN_PROGRESS", "REVIEW_IN_PROGRESS")
POLL_SECONDS = 15


def parse_args() -> argparse.Namespace:
    """Return an explicit read-only plan or a resumable apply command."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser(
        "plan", help="Inspect AWS and write a deployment manifest without changing AWS")
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--manifest", type=Path, required=True)
    apply = commands.add_parser(
        "apply", help="Create the stacks in a saved plan, or resume that deployment")
    apply.add_argument("--manifest", type=Path, required=True)
    apply.add_argument("--timeout", type=int, default=1800,
                       help="Maximum seconds per stack before saving and returning")
    args = parser.parse_args()
    if getattr(args, "timeout", 1) < 1:
        parser.error("--timeout must be positive")
    return args


def read_json(path: Path) -> dict:
    """Read a JSON object without resolving or storing credentials."""
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save_manifest(path: Path, manifest: dict) -> None:
    """Atomically save deployment progress so an interrupted command can resume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = {**manifest, "updated_at": datetime.now(timezone.utc).isoformat()}
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def read_templates() -> dict:
    """Read template snapshots once so every stack uses the saved, reviewed version."""
    return {name: (DEMO_ROOT / name).read_text() for name in TEMPLATE_NAMES}


def plan_rollout(config_path: Path, manifest_path: Path) -> None:
    """Inspect account identities and conflicts before saving an unexecuted plan."""
    if manifest_path.exists():
        raise ValueError(f"{manifest_path} already exists; apply it to resume, "
                         "or choose a new manifest path")
    config = read_json(config_path)
    problems = config_problems(config)
    if problems:
        raise ValueError("\n".join(problems))
    templates = read_templates()
    observations = [inspect_unit(unit, config["deployment_id"], templates[unit["template"]])
                    for unit in deployment_units(config)]
    manifest = new_manifest(config, template_hashes(templates), observations,
                            datetime.now(timezone.utc).isoformat(), templates)
    save_manifest(manifest_path, manifest)
    print(f"Plan saved: {manifest_path}\nNo AWS resources changed. Review these exact targets:")
    print_targets(manifest)
    print(f"\nTo deploy: python3 deploy.py apply --manifest {manifest_path}")


def apply_rollout(manifest_path: Path, timeout: int) -> None:
    """Deploy the central stack before sources and save every observed transition."""
    manifest = read_json(manifest_path)
    problems = manifest_problems(manifest)
    if problems:
        raise ValueError("\n".join(problems))
    for index in range(len(manifest["units"])):
        manifest = apply_one(manifest_path, manifest, index, timeout)
    print("\nAWS stacks are ready. Vantage end-to-end verification is still required.")
    print_targets(manifest)
    print("Run verify.py, then use the original buckets in "
          "Settings -> Integrations -> AWS Bedrock.")
    print("Complete Check Permissions, inspect Import History, and verify account/tag costs.")


def apply_one(manifest_path: Path, previous: dict, index: int, timeout: int) -> dict:
    """Persist one stack's identity before waiting, including timeout and failure states."""
    manifest = deepcopy(previous)
    unit = manifest["units"][index]
    deployment_id = manifest["config"]["deployment_id"]
    central_outputs = manifest["units"][0].get("outputs", {})
    parameters = resolved_parameters(unit, central_outputs)
    result = start_or_resume_stack(unit, deployment_id,
                                   manifest["template_bodies"][unit["template"]], parameters)
    unit.update(result)
    save_manifest(manifest_path, manifest)
    deadline = time.monotonic() + timeout
    while True:
        unit.update(describe_owned_stack(unit, deployment_id))
        save_manifest(manifest_path, manifest)
        print(f"{unit['account_id']}/{unit['region']} {unit['stack_name']}: {unit['status']}",
              flush=True)
        if unit["status"] == "CREATE_COMPLETE":
            return manifest
        if unit["status"] not in RUNNING:
            raise ValueError(f"Stack {unit['stack_name']} ended in {unit['status']}: "
                             f"{unit.get('reason', '')}. Inspect CloudFormation events; "
                             "no unrelated resources were deleted.")
        if time.monotonic() >= deadline:
            raise TimeoutError("Stack is still running. Progress was saved; "
                               "rerun apply with the same manifest.")
        time.sleep(min(POLL_SECONDS, max(0, deadline - time.monotonic())))


def print_targets(manifest: dict) -> None:
    """Show source identities and original Vantage inputs next to the central destination."""
    central = manifest["units"][0]
    print(f"Central copy: s3://{central['bucket_name']} "
          f"({central['account_id']}/{central['region']})")
    for unit in manifest["units"][1:]:
        handoff = original_bucket_handoff(unit)
        print(f"Vantage source: {handoff['account_id']}/{handoff['region']} "
              f"s3://{handoff['bucket']}/{handoff['prefix']}")


def main() -> None:
    """Run the selected command and return actionable failures without a traceback."""
    args = parse_args()
    try:
        if args.command == "plan":
            plan_rollout(args.config, args.manifest)
        else:
            apply_rollout(args.manifest, args.timeout)
    except (ValueError, KeyError, TypeError, OSError, TimeoutError,
            BotoCoreError, ClientError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
