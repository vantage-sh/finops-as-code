"""Compatibility imports; new callers use bedrock_demo.core modules."""
from __future__ import annotations

from bedrock_demo.core.logs import (
    REQUIRED_RECORD_FIELDS,
    log_prefix,
    vantage_connect_values,
    object_key_pattern,
    day_prefixes,
    record_problems,
    record_warnings,
    records_from_gz,
    resolved_region,
    logging_status_line,
)
from bedrock_demo.core.planning import (
    bedrock_service_names,
    deployable_region,
    spend_by_account_region,
    rollout_plan,
    stackset_create_command,
    stackset_instances_command,
    targeted_instance_commands,
    management_account_note,
    deployment_blocks,
    plan_lines,
)
