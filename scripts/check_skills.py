# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.3"]
# ///
"""Check the skills in skills/, and build the catalog the FinOps Agent reads them from.

    uv run scripts/check_skills.py                 check every skill
    uv run scripts/check_skills.py --build <dir>   check, then write the catalog into <dir>

The catalog is index.json, a map of every skill, one bundle per skill in skills/ with its SKILL.md and references,
and evals.json, every eval case, the ones generated from each template included. A workflow builds it on every merge
to main and pushes it to the catalog branch, so nothing generated is committed next to the skills.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import groupby
from pathlib import Path

import yaml

MAX_FILE_CHARS = 64_000  # the agent's cap on each file in a skill, counted like JavaScript string length
MAX_INDEX_CHARS = 200_000  # the agent's cap on index.json, the map that names and describes every skill
MAX_BUNDLE_CHARS = 500_000  # the agent's cap on one skill's bundle, its SKILL.md and every file under references/
HASH_CHARS = 12  # hex digits of the content hash in a bundle's name
MAX_DESCRIPTION_CHARS = 1_024
MAX_COMPATIBILITY_CHARS = 500
SPEC_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
SKILL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# The agent's built-in skills. It keeps its own, and drops a catalog skill that takes one of their names.
BUILT_IN_SKILLS = frozenset({"anomaly-investigation", "autopilot", "terraform"})
TOOL_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}")
SCOPE_NAME = re.compile(r"[a-z][a-z0-9_]*")
REFERENCE_PATH = re.compile(r"references/(?:[A-Za-z0-9_-][A-Za-z0-9_.-]*/)*[A-Za-z0-9_-][A-Za-z0-9_.-]*")
FRONTMATTER = re.compile(r"---\n(.*?)\n---\n", re.DOTALL)
SECTION = re.compile(r"^## (.+?)\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
YAML_BLOCK = re.compile(r"```yaml\n(.*?)\n```", re.DOTALL)
TEMPLATE_ROW = re.compile(
    r"^\|\s*\[(?P<title>[^\]]+)\]\((?P<file>[^)]+)\)\s*\|\s*(?P<description>[^|]*?)\s*\|\s*$", re.MULTILINE
)
PROVIDER_CLAUSE = re.compile(r"costs\.provider\s*=\s*'([^']*)'")
# Vantage's costs.provider keys. VQL returns no costs and no error for any other key, so add new providers here.
PROVIDER_KEYS = frozenset(
    "aws azure gcp snowflake databricks mongo datadog fastly new_relic opencost open_ai oracle confluent planetscale"
    " coralogix kubernetes custom_provider github linode grafana clickhouse temporal twilio azure_csp kubernetes_agent"
    " anthropic anyscale cursor elastic vercel redis_cloud circle_ci modal eleven_labs baseten cloudflare fireworks_ai"
    " cartesia depot xai digital_ocean together_ai coreweave devin openrouter deepgram crusoe sentry_billing ramp"
    " dynatrace".split()
)

EVAL_PATH = re.compile(r"evals/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.ya?ml")
CASE_ID = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*")  # one path segment, since results are saved under the id
MAX_CASE_ID_CHARS = 250  # the harness saves a case's result as <id>.json, and file systems cap a name at 255 bytes
CASE_TEXT = ("description", "prompt", "referenceAnswer")
CASE_LISTS = ("followUps", "tags", "requiredTools")
CASE_FIELDS = {"id", *CASE_TEXT, *CASE_LISTS, "responses"}
FIXTURE_FIELDS = {"tool", "arguments", "absent", "result"}
# evals.json carries every eval case and each template's fields, so both hold only what JSON can.
JSON_ONLY = (
    "must hold only JSON data: text, numbers, true, false, null, lists, and mappings with text keys (quote a date)"
)

DASHBOARD_TEMPLATES = "dashboard-templates"  # the one skill whose Templates table lists dashboard templates
# The periods a report may use, the ones Step 3 covers from the first day of the month four months ago, for a scope's
# searches and a filter's check alike. Vantage starts last_3_months on the first of the month three months before
# the day two days ago, so during a month's first two days it starts four months back.
SEARCHED_INTERVALS = (
    "this_month",
    "last_7_days",
    "last_14_days",
    "last_30_days",
    "last_month",
    "last_3_months",
)
# The fields a template's report can set, each passed to create-cost-report as written, with scope standing in for
# filter. It leaves out start_date and end_date, since Vantage gives a report with either one a fixed range in place of
# its date_interval, which can reach back past what Step 3 searched.
REPORT_FIELDS = ("title", "scope", "filter", "groupings", "date_interval", "date_bin", "chart_type")

# The fake account a template's eval cases run against: one workspace, no dashboards, and four rows of costs.
SAMPLE_WORKSPACE = "wrkspc_eval"
SAMPLE_AMOUNTS = ("4120.55", "2875.10", "1960.40", "312.25")
SAMPLE_TOTAL = "9268.30"
SAMPLE_VALUES = {"provider": ("cursor", "anthropic", "open_ai", "aws")}
SAMPLE_SCOPE = "ai_spend"  # the one scope the fake account's searches below are written for
# What Step 3's two searches find for ai_spend in the fake account, as (provider, service, amount) and (provider,
# amount). The agent should count cursor, anthropic and open_ai whole, count aws by its one tagged service, and leave
# datadog out. Nothing tags cartesia, so the agent asks about it, and a plain yes builds without it. That makes
# SAMPLE_FILTER the scope's filter, and the preview's four rows above follow it.
SAMPLE_FOUND = (
    ("cursor", "Claude Sonnet 4.5", "3388.20"),
    ("anthropic", "Claude Opus 4.1", "2875.10"),
    ("open_ai", "GPT-5", "1960.40"),
    ("aws", "AmazonBedrock", "312.25"),
)
SAMPLE_PROVIDERS = (
    ("aws", "48210.70"),
    ("cursor", "4120.55"),
    ("anthropic", "2875.10"),
    ("open_ai", "1960.40"),
    ("datadog", "1404.00"),
    ("cartesia", "640.00"),
)
NO_DATA_PROVIDERS = (("datadog", "1404.00"),)  # the no-data account has costs, but none a scope's search finds
SAMPLE_FILTER = (
    "costs.provider = 'cursor' OR costs.provider = 'anthropic' OR costs.provider = 'open_ai'"
    " OR (costs.provider = 'aws' AND costs.service IN ('AmazonBedrock'))"
)
SAMPLE_SORT = (
    "The agent counts cursor, anthropic and open_ai whole and only AmazonBedrock from aws, and asks whether to add"
    " cartesia."
)
EVERY_PROVIDER = "costs.provider = '*'"
# Step 3's search start, written the way the eval harness reads a date relative to the day it runs: the first day of
# the month four months back.
SEARCH_START = "$monthStart-4"
DASHBOARD_RANGE = ["date_interval", "start_date", "end_date", "date_bin"]
ONE_WORKSPACE = {
    "tool": "list-workspaces",
    "result": {"workspaces": [{"token": SAMPLE_WORKSPACE, "name": "Acme Corp"}], "pagination": {"hasNextPage": False}},
}
NO_DASHBOARDS = {
    "tool": "list-dashboards",
    "arguments": {"workspace_token": SAMPLE_WORKSPACE},
    "result": {"dashboards": [], "pagination": {"hasNextPage": False}},
}


@dataclass(frozen=True)
class Skill:
    """One skill folder as read from disk, evals included. Text is None for a file that's missing or isn't UTF-8."""

    name: str
    text: str | None
    files: dict[str, str | None]
    evals: dict[str, str | None] = field(default_factory=dict)
    links: tuple[str, ...] = ()  # each symbolic link by its path in the folder, "." for the folder itself


class _UniqueKeyLoader(yaml.SafeLoader):
    """A safe YAML loader that refuses a repeated key, as the agent's parser does, and an alias."""

    def compose_node(self, parent: yaml.Node | None, index: object) -> yaml.Node | None:
        """Return the next node, refusing an alias, since one can make a list hold itself or repeat a value millions
        of times, and neither can be written to the catalog."""
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("an alias repeats an anchored value")
        return super().compose_node(parent, index)

    def construct_scalar(self, node: yaml.ScalarNode) -> str:
        """Return a scalar, rejecting Unicode that cannot be published as UTF-8."""
        value = super().construct_scalar(node)
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise yaml.YAMLError("a scalar contains invalid Unicode") from error
        return value


def _unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    """Build a mapping, refusing it when a key repeats."""
    mapping = loader.construct_mapping(node, deep=True)
    if len(mapping) < len(node.value):
        raise yaml.YAMLError(f"a key repeats in the mapping on line {node.start_mark.line + 1}")
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def parse_yaml(source: str | None) -> object:
    """Return the YAML value, or None when it's missing, isn't valid YAML, repeats a key or uses an alias. A value
    PyYAML can't build, like a 5,000-digit number, the date 2026-13-45 or `!!bool maybe`, isn't valid either."""
    try:
        return yaml.load(source, Loader=_UniqueKeyLoader) if source is not None else None
    except Exception:  # PyYAML raises more than YAMLError on a value it can't build, and each one means bad input
        return None


def text(value: object) -> str:
    """Return the value when it's text, otherwise an empty string."""
    return value if isinstance(value, str) else ""


def mapping(value: object) -> dict:
    """Return the value when it's a mapping, otherwise an empty one."""
    return value if isinstance(value, dict) else {}


def one_line(value: object) -> str:
    """Return the text with every run of whitespace as one space, the way the catalog stores a description."""
    return " ".join(text(value).split())


def js_length(value: str) -> int:
    """Return the length JavaScript would report, in UTF-16 code units, which is how the agent caps files."""
    return len(value.encode("utf-16-le")) // 2


def lf(source: str) -> str:
    """Return the text with CRLF and CR line endings as LF, so a Windows checkout writes the same catalog."""
    return source.replace("\r\n", "\n").replace("\r", "\n")


def split_frontmatter(source: str) -> tuple[object, str]:
    """Return the parsed frontmatter (None when it's missing or invalid) and the body after it, with LF line endings."""
    match = FRONTMATTER.match(lf(source))
    return (parse_yaml(match.group(1)), lf(source)[match.end() :]) if match else (None, lf(source))


def sections(body: str) -> dict[str, str]:
    """Return each `## ` section of a SKILL.md body by its heading."""
    return {heading.strip(): content for heading, content in SECTION.findall(body)}


def tool_list(value: object) -> list[str]:
    """Return the tools a `vantage-tools` value lists, separated by commas or spaces, each once."""
    return list(dict.fromkeys(tool for tool in re.split(r"[\s,]+", text(value)) if tool))


def text_list(value: object) -> bool:
    """Return whether the value is a list of text."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def unknown_providers(vql: str) -> list[str]:
    """Return each provider key the VQL names that Vantage doesn't have, `*` aside."""
    return [key for key in PROVIDER_CLAUSE.findall(vql) if key != "*" and key not in PROVIDER_KEYS]


def frontmatter_problems(folder: str, fields: object) -> Iterator[str]:
    """Yield what's wrong with a SKILL.md's frontmatter, by the Agent Skills spec and the agent's own rules."""
    if not isinstance(fields, dict):
        yield (
            "SKILL.md must start with YAML frontmatter between --- lines, written as valid YAML with no repeated"
            " keys or aliases (quote a value that has ': ' in it)"
        )
        return
    extra = sorted(str(key) for key in fields if key not in SPEC_FIELDS)
    if extra:
        yield f"frontmatter has fields the Agent Skills spec doesn't define: {', '.join(extra)}"
    if not SKILL_NAME.fullmatch(folder) or len(folder) > 64:
        yield "the folder name must be 1 to 64 lowercase letters, digits and single hyphens"
    if folder in BUILT_IN_SKILLS:
        yield f"the folder name {folder} is one of the agent's built-in skills, which it keeps instead of this one"
    if fields.get("name") != folder:
        yield f"name must be {folder}, the folder's name"
    description = one_line(fields.get("description"))
    if not description or js_length(description) > MAX_DESCRIPTION_CHARS:
        yield f"description must be text of 1 to {MAX_DESCRIPTION_CHARS} characters"
    compatibility = fields.get("compatibility")
    if compatibility is not None and not 1 <= js_length(text(compatibility)) <= MAX_COMPATIBILITY_CHARS:
        yield f"compatibility must be text of 1 to {MAX_COMPATIBILITY_CHARS} characters"
    metadata = fields.get("metadata", {})
    if not isinstance(metadata, dict) or not all(isinstance(item, str) for item in (*metadata, *metadata.values())):
        yield "metadata must map names to text, so write vantage-tools as one comma-separated line"
        return
    tools = tool_list(metadata.get("vantage-tools"))
    if not tools:
        yield "metadata.vantage-tools must list the Vantage MCP tools the skill calls"
    unnamed = [tool for tool in tools if not TOOL_NAME.fullmatch(tool)]
    if unnamed:
        yield f"metadata.vantage-tools has entries that aren't tool names: {', '.join(unnamed)}"


def scope_block(body: str) -> object:
    """Return the parsed ```yaml block under `## Scopes`, or None when there isn't a valid one."""
    block = YAML_BLOCK.search(sections(body).get("Scopes", ""))
    return parse_yaml(block.group(1) if block else None)


def scope_problems(block: object) -> Iterator[str]:
    """Yield what's wrong with a Scopes block, which maps snake_case names to VQL."""
    if not isinstance(block, dict) or not block:
        yield "Scopes needs one ```yaml block that maps each scope name to its VQL"
        return
    yield from (f"scope {name!r} must be a snake_case name" for name in block if not SCOPE_NAME.fullmatch(text(name)))
    yield from (f"scope {name!r} must be VQL text" for name, vql in block.items() if not one_line(vql))
    yield from (
        f"scope {name!r} names provider {key!r}, which isn't a Vantage provider key"
        for name, vql in block.items()
        for key in unknown_providers(text(vql))
    )


def scope_conflicts(scopes_by_skill: dict[str, object]) -> Iterator[str]:
    """Yield each scope name that two skills define with different VQL, since a name means one thing everywhere."""
    definitions = sorted(
        (name, one_line(vql), skill)
        for skill, block in scopes_by_skill.items()
        for name, vql in mapping(block).items()
        if isinstance(name, str)
    )
    for name, group in groupby(definitions, key=lambda definition: definition[0]):
        entries = list(group)
        if len({vql for _, vql, _ in entries}) > 1:
            yield f"scope {name} means different VQL in {', '.join(sorted({skill for _, _, skill in entries}))}"


def filter_problems(where: str, part: object, scopes: dict) -> Iterator[str]:
    """Yield what's wrong with the filter of a preview or a report: one of scope or filter, naming a real scope."""
    if not isinstance(part, dict):
        yield f"{where} must be a mapping"
    elif ("scope" in part) == ("filter" in part):
        yield f"{where} needs one of scope or filter"
    elif "scope" in part and text(part["scope"]) not in scopes:
        yield f"{where} names scope {part['scope']!r}, which isn't in Scopes"
    elif "filter" in part and not one_line(part["filter"]):
        yield f"{where}.filter must be VQL text"
    yield from (
        f"{where}.filter names provider {key!r}, which isn't a Vantage provider key"
        for key in unknown_providers(text(mapping(part).get("filter")))
    )


def dashboard_template_problems(stem: str, template: object, scopes: dict) -> Iterator[str]:
    """Yield what's wrong with one dashboard template: its id, text fields, filters, reports and widgets."""
    if not isinstance(template, dict):
        yield "must be a valid YAML mapping, with no repeated keys or aliases"
        return
    if not json_data(template):
        yield JSON_ONLY
    if template.get("id") != stem:
        yield f"id must be {stem}, the file's name"
    yield from (f"{field} must be text" for field in ("title", "description") if not one_line(template.get(field)))

    preview = mapping(template.get("preview"))
    yield from filter_problems("preview", template.get("preview"), scopes)
    if text(preview.get("scope")) in scopes and preview["scope"] != SAMPLE_SCOPE:
        yield (
            f"preview.scope {preview['scope']} has no sample account to generate eval cases from: check_skills.py's"
            f" sample searches are written for {SAMPLE_SCOPE}"
        )
    if not text_list(preview.get("groupings")):
        yield "preview.groupings must be a list of text"
    if not one_line(preview.get("if_empty")):
        yield "preview.if_empty must be text"
    if not one_line(mapping(template.get("folder")).get("title")):
        yield "folder.title must be text"
    yield from (
        f"folder.{key} isn't a field a template's folder takes"
        for key in mapping(template.get("folder"))
        if key != "title"
    )

    reports = mapping(template.get("cost_reports"))
    if not reports:
        yield "cost_reports must map a key to each report"
    yield from (
        problem for key, report in reports.items() for problem in filter_problems(f"cost_reports.{key}", report, scopes)
    )
    yield from (
        f"cost_reports.{key}.{name} isn't a field a template's report takes"
        for key, report in reports.items()
        for name in mapping(report)
        if name not in REPORT_FIELDS
    )
    yield from (
        f"cost_reports.{key} must use the preview's scope, since Step 3 searches and confirms only that one"
        for key, report in reports.items()
        if ("scope" in mapping(report) or "scope" in preview)
        and text(mapping(report).get("scope")) != text(preview.get("scope"))
    )
    yield from (
        f"cost_reports.{key}.date_interval must be one of the periods Step 3 looks back over:"
        f" {', '.join(SEARCHED_INTERVALS)}"
        for key, report in reports.items()
        if one_line(mapping(report).get("date_interval"))
        and text(mapping(report)["date_interval"]) not in SEARCHED_INTERVALS
    )
    yield from (
        f"cost_reports.{key}.{name} must be text"
        for key, report in reports.items()
        for name in ("title", "date_interval")
        if not one_line(mapping(report).get(name))
    )
    yield from (
        f"cost_reports.{key}.{name} must be text"
        for key, report in reports.items()
        for name in ("date_bin", "chart_type")
        if name in mapping(report) and not one_line(mapping(report)[name])
    )
    yield from (
        f"cost_reports.{key}.groupings must be a list of text"
        for key, report in reports.items()
        if not text_list(mapping(report).get("groupings"))
    )

    dashboard = mapping(template.get("dashboard"))
    widgets = dashboard.get("widgets") if isinstance(dashboard.get("widgets"), list) else []
    yield from (
        f"dashboard.{key} isn't a field a template's dashboard takes"
        for key in dashboard
        if key not in ("title", "widgets")
    )
    yield from (
        f"dashboard.widgets[{index}].{key} isn't a field a widget takes"
        for index, widget in enumerate(widgets)
        for key in mapping(widget)
        if key not in ("report", "title", "settings")
    )
    if not one_line(dashboard.get("title")):
        yield "dashboard.title must be text"
    if not widgets:
        yield "dashboard.widgets must list the widgets in order"
    yield from (
        f"dashboard.widgets[{index}] must name a report under cost_reports"
        for index, widget in enumerate(widgets)
        if text(mapping(widget).get("report")) not in reports
    )
    yield from (
        f"dashboard.widgets[{index}].title must be text"
        for index, widget in enumerate(widgets)
        if "title" in mapping(widget) and not one_line(mapping(widget)["title"])
    )
    yield from (
        f"dashboard.widgets[{index}].settings must be a mapping"
        for index, widget in enumerate(widgets)
        if "settings" in mapping(widget) and not isinstance(mapping(widget)["settings"], dict)
    )


def template_rows(body: str) -> list[dict[str, str]]:
    """Return the rows of the Templates table: each template's linked title, file and description."""
    return [match.groupdict() for match in TEMPLATE_ROW.finditer(sections(body).get("Templates", ""))]


def table_problems(rows: list[dict[str, str]], templates: dict[str, object]) -> Iterator[str]:
    """Yield where the Templates table and the template files disagree: one row per file, matching its title and text."""
    listed = [row["file"] for row in rows]
    yield from (f"Templates lists {file} twice" for file in sorted({file for file in listed if listed.count(file) > 1}))
    yield from (f"Templates lists {file}, which isn't a template file" for file in listed if file not in templates)
    yield from (f"{file} needs a row in Templates" for file in templates if file not in listed)
    for row in rows:
        template = mapping(templates.get(row["file"]))
        title, description = text(template.get("title")), one_line(template.get("description"))
        if template and (row["title"], row["description"]) != (title, description):
            yield f"the Templates row for {row['file']} must read [{title}]({row['file']}) | {description}"


def skill_templates(skill: Skill) -> dict[str, object]:
    """Return the dashboard templates by path, parsed: none unless it's dashboard-templates with a Templates table."""
    if skill.name != DASHBOARD_TEMPLATES or "Templates" not in sections(split_frontmatter(skill.text or "")[1]):
        return {}
    return {path: parse_yaml(source) for path, source in skill.files.items() if path.endswith((".yaml", ".yml"))}


def json_data(value: object) -> bool:
    """Return whether the value is plain JSON: text, finite numbers, true, false, null, and lists and maps of them."""
    if isinstance(value, dict):
        return all(isinstance(key, str) and json_data(item) for key, item in value.items())
    if isinstance(value, list):
        return all(json_data(item) for item in value)
    return value is None or isinstance(value, (str, bool, int)) or (isinstance(value, float) and math.isfinite(value))


def fixture_problems(where: str, fixture: object, tools: list[str]) -> Iterator[str]:
    """Yield what's wrong with one fixture: its fields, a tool the skill lists, and its arguments, absent and result."""
    if not isinstance(fixture, dict):
        yield f"{where} must be a mapping"
        return
    extra = sorted(str(key) for key in fixture if key not in FIXTURE_FIELDS)
    if extra:
        yield f"{where} has fields the harness doesn't read: {', '.join(extra)}"
    if fixture.get("tool") not in tools:
        yield f"{where}.tool must be one of the skill's vantage-tools"
    if "arguments" in fixture and not isinstance(fixture["arguments"], dict):
        yield f"{where}.arguments must be a mapping"
    if "absent" in fixture and not text_list(fixture["absent"]):
        yield f"{where}.absent must be a list of argument names"
    if "result" not in fixture:
        yield f"{where} needs a result"


def case_problems(where: str, case: object, tools: list[str]) -> Iterator[str]:
    """Yield what's wrong with one eval case: its fields, the tools it requires, and each fixture."""
    if not isinstance(case, dict):
        yield f"{where} must be a mapping"
        return
    extra = sorted(str(key) for key in case if key not in CASE_FIELDS)
    if extra:
        yield f"{where} has fields the harness doesn't read: {', '.join(extra)}"
    case_id = text(case.get("id"))
    if not CASE_ID.fullmatch(case_id) or len(case_id) > MAX_CASE_ID_CHARS:
        yield f"{where}.id must be 1 to {MAX_CASE_ID_CHARS} letters, digits, '.', '_' and '-'"
    yield from (f"{where}.{name} must be text" for name in CASE_TEXT if not one_line(case.get(name)))
    yield from (
        f"{where}.{name} must be a list of text" for name in CASE_LISTS if name in case and not text_list(case[name])
    )
    required = case["requiredTools"] if text_list(case.get("requiredTools")) else []
    unlisted = [tool for tool in required if tool not in tools]
    if unlisted:
        yield f"{where}.requiredTools has tools the skill's vantage-tools doesn't list: {', '.join(unlisted)}"
    fixtures = case.get("responses")
    if not isinstance(fixtures, list):
        yield f"{where}.responses must be a list of fixtures"
    else:
        yield from (
            problem
            for index, fixture in enumerate(fixtures)
            for problem in fixture_problems(f"{where}.responses[{index}]", fixture, tools)
        )
    if not json_data(case):
        yield f"{where} {JSON_ONLY}"


def case_label(case: object, number: int) -> str:
    """Return how a problem names an eval case: its id, or its place in the file."""
    return text(mapping(case).get("id")) or f"case {number}"


def eval_file_problems(path: str, source: str, tools: list[str]) -> Iterator[str]:
    """Yield what's wrong with one eval file: its name, its YAML, and each case in it."""
    if not EVAL_PATH.fullmatch(path):
        yield f"{path} must be a .yaml file of eval cases, named with letters, digits, '.', '_' and '-'"
        return
    cases = parse_yaml(source)
    if not isinstance(cases, list) or not cases:
        yield f"{path} must be a valid YAML list of eval cases, with no repeated keys or aliases"
        return
    yield from cases_problems(path, cases, tools)


def cases_problems(path: str, cases: list, tools: list[str]) -> Iterator[str]:
    """Yield what's wrong with each case in a list of eval cases, naming it by the file it came from and its id."""
    yield from (
        problem
        for number, case in enumerate(cases, start=1)
        for problem in case_problems(f"{path}: {case_label(case, number)}", case, tools)
    )


def skill_problems(skill: Skill) -> Iterator[str]:
    """Yield everything wrong with one skill folder: links, frontmatter, files, scopes, templates and evals."""
    yield from (
        f"{'the folder' if path == '.' else path} is a symbolic link, and a skill folder holds only regular files"
        for path in skill.links
    )
    if skill.text is None:
        yield "needs a SKILL.md in UTF-8"
        return
    fields, body = split_frontmatter(skill.text)
    yield from frontmatter_problems(skill.name, fields)

    sizes = {"SKILL.md": js_length(lf(skill.text))} | {
        path: js_length(lf(text(source))) for path, source in skill.files.items()
    }
    yield from (
        f"{path} is {size} characters, over the {MAX_FILE_CHARS} limit"
        for path, size in sizes.items()
        if size > MAX_FILE_CHARS
    )
    yield from (f"{path} isn't UTF-8 text" for path, source in skill.files.items() if source is None)
    yield from (
        f"{path} may only use letters, digits, '.', '_' and '-'"
        for path in skill.files
        if not REFERENCE_PATH.fullmatch(path)
    )

    scopes = scope_block(body)
    if "Scopes" in sections(body):
        yield from scope_problems(scopes)
    if skill.name == DASHBOARD_TEMPLATES and "Templates" in sections(body):
        templates = skill_templates(skill)
        yield from table_problems(template_rows(body), templates)
        yield from (
            f"{path}: {problem}"
            for path, template in templates.items()
            for problem in dashboard_template_problems(Path(path).stem, template, mapping(scopes))
        )

    tools = tool_list(mapping(mapping(fields).get("metadata")).get("vantage-tools"))
    yield from (f"{path} isn't UTF-8 text" for path, source in skill.evals.items() if source is None)
    if not tools:
        return  # the frontmatter's problem is above, and checking every case against no tools would bury it
    yield from (
        problem
        for path, source in sorted(skill.evals.items())
        if source is not None
        for problem in eval_file_problems(path, source, tools)
    )
    yield from (
        problem for path, cases in generated_cases(skill).items() for problem in cases_problems(path, cases, tools)
    )


def skill_scopes(skill: Skill) -> object:
    """Return the skill's parsed Scopes block, or None when it has none."""
    return scope_block(split_frontmatter(skill.text or "")[1])


def dollars(amount: str) -> str:
    """Return an amount the way a reference answer writes it, such as $4,120.55."""
    return f"${Decimal(amount):,.2f}"


def with_filter(part: dict) -> dict:
    """Return a preview or report with its scope swapped for the filter the agent writes for the fake account."""
    if "scope" not in part:
        return part
    return {**{key: value for key, value in part.items() if key != "scope"}, "filter": SAMPLE_FILTER}


def rows_of(values: tuple[tuple[str, ...], ...], groupings: list[str]) -> list[dict]:
    """Return query-costs rows from tuples that hold each grouping's value, then the amount."""
    return [{"amount": row[-1], "currency": "USD", **dict(zip(groupings, row[:-1]))} for row in values]


def total_of(rows: list[dict]) -> str:
    """Return the rows' amounts added up, the way query-costs gives a total."""
    return f"{sum((Decimal(row['amount']) for row in rows), Decimal(0)):.2f}"


def scope_searches(vql: str | None, found: list[dict], providers: list[dict]) -> list[dict]:
    """Return fixtures for Step 3's two searches, the scope's VQL by provider and service, then every provider."""
    if not vql:
        return []
    by_service = {
        "tool": "query-costs",
        "arguments": {
            "filter": vql,
            "groupings": ["provider", "service"],
            "date_bin": "month",
            "start_date": SEARCH_START,
            "workspace_token": SAMPLE_WORKSPACE,
        },
        "result": cost_result(found, total_of(found)),
    }
    every_provider = {
        "tool": "query-costs",
        "arguments": {
            "filter": EVERY_PROVIDER,
            "groupings": ["provider"],
            "date_bin": "month",
            "start_date": SEARCH_START,
            "workspace_token": SAMPLE_WORKSPACE,
        },
        "result": cost_result(providers, total_of(providers)),
    }
    return [by_service, every_provider]


def sample_rows(grouping: str | None) -> list[dict]:
    """Return four rows of costs by the preview's first grouping, so every template's preview has something to show."""
    values = SAMPLE_VALUES.get(grouping or "", [f"{grouping}-{letter}" for letter in "abcd"])
    return [
        {"amount": amount, "currency": "USD", **({grouping: value} if grouping else {})}
        for amount, value in zip(SAMPLE_AMOUNTS, values)
    ]


def row_text(row: dict) -> str:
    """Return a row the way a reference answer lists it: its grouping's value, then its amount."""
    label = next((value for key, value in row.items() if key not in ("amount", "currency")), None)
    return f"{label} {dollars(row['amount'])}" if label else dollars(row["amount"])


def cost_result(rows: list[dict], total: str) -> dict:
    """Return what query-costs answers with these rows and this total."""
    return {
        "costs": rows,
        "total_cost": {"amount": total, "currency": "USD"},
        "notes": "Costs records represent the requested date range.",
        "pagination": {"hasNextPage": False},
    }


def widget_title(widget: dict, reports: dict) -> str:
    """Return a widget's title as the dashboard shows it: its own, else its report's, else the report's key."""
    titles = (widget.get("title"), mapping(reports.get(widget["report"])).get("title"))
    return next((title for title in titles if title is not None), widget["report"])


def template_cases(template: dict, scopes: dict) -> list[dict]:
    """Return a valid template's three eval cases: a plain ask that stops at the confirm, an account with no matching
    costs, and the build after a yes. Only reads and the template's own writes have fixtures."""
    template_id, title = template["id"], template["title"]
    preview = with_filter(template["preview"])
    reports = {key: with_filter(report) for key, report in template["cost_reports"].items()}
    scope = template["preview"].get("scope")
    vql = one_line(scopes[scope]) if scope else None
    found, providers = rows_of(SAMPLE_FOUND, ["provider", "service"]), rows_of(SAMPLE_PROVIDERS, ["provider"])
    searches = scope_searches(vql, found, providers)
    no_data_searches = scope_searches(vql, [], rows_of(NO_DATA_PROVIDERS, ["provider"]))
    sort = f"{SAMPLE_SORT} " if vql else ""
    folder_title, dashboard_title = template["folder"]["title"], template["dashboard"]["title"]
    folder_token, dashboard_token = f"fldr_eval_{template_id}", f"dshbrd_eval_{template_id}"
    widgets = [
        {"widgetable_token": f"rprt_eval_{template_id}_{widget['report']}"}
        | {key: value for key, value in widget.items() if key != "report"}
        for widget in template["dashboard"]["widgets"]
    ]
    dashboard_fields = {key: value for key, value in template["dashboard"].items() if key != "widgets"}
    dashboard = dashboard_fields | {"token": dashboard_token, "workspace_token": SAMPLE_WORKSPACE, "widgets": widgets}
    folder = template["folder"] | {"type": "CostFolder", "workspace_token": SAMPLE_WORKSPACE}
    query = {
        "filter": preview["filter"],
        "groupings": preview["groupings"],
        "date_bin": "month",
        "workspace_token": SAMPLE_WORKSPACE,
    }
    rows = sample_rows(next(iter(preview["groupings"]), None))
    preview_query = {"tool": "query-costs", "arguments": query, "result": cost_result(rows, SAMPLE_TOTAL)}
    empty_query = {"tool": "query-costs", "arguments": query, "result": cost_result([], "0.00")}
    build = [
        {"tool": "create-folder", "arguments": folder, "result": folder | {"token": folder_token}},
        *(
            {
                "tool": "create-cost-report",
                "arguments": fields | {"folder_token": folder_token, "workspace_token": SAMPLE_WORKSPACE},
                "absent": [name for name in ("date_bin", "chart_type") if name not in fields],
                "result": {
                    "token": f"rprt_eval_{template_id}_{key}",
                    "title": fields["title"],
                    "folder_token": folder_token,
                },
            }
            for key, fields in reports.items()
        ),
        {
            "tool": "create-dashboard",
            "arguments": dashboard_fields | {"workspace_token": SAMPLE_WORKSPACE, "widgets": widgets},
            "absent": DASHBOARD_RANGE,
            "result": dashboard,
        },
        {"tool": "get-dashboard", "arguments": {"dashboard_token": dashboard_token}, "result": dashboard},
    ]
    report_titles = [report["title"] for report in reports.values()]
    widget_titles = [widget_title(widget, reports) for widget in template["dashboard"]["widgets"]]
    plan = (
        f"one {folder_title} folder, {len(report_titles)} cost reports and one {dashboard_title} dashboard"
        f" with {len(widget_titles)} widgets"
    )
    ask = f"Set up the {title} dashboard for me."
    return [
        {
            "id": f"{template_id}-plain-ask",
            "description": (
                f"Loads the dashboard-templates skill and its {title} template from a plain ask, previews the costs"
                " in the only workspace, and stops at the confirm without creating anything"
            ),
            "tags": [template_id],
            "prompt": ask,
            "referenceAnswer": (
                f"Acme Corp's costs in the template's preview come to {dollars(SAMPLE_TOTAL)}:"
                f" {', '.join(row_text(row) for row in rows)}. {sort}The agent says it will create {plan}, and asks"
                " the user to confirm before creating anything."
            ),
            "responses": [ONE_WORKSPACE, NO_DASHBOARDS, *searches, preview_query],
        },
        {
            "id": f"{template_id}-no-data",
            "description": (
                f"Loads the {title} template for an account with no matching costs, gives the template's empty-state"
                " message, and creates nothing"
            ),
            "tags": [template_id],
            "prompt": f"Can you build the {title} dashboard?",
            "referenceAnswer": f"There are no matching costs, so the dashboard isn't built: {preview['if_empty']}",
            "responses": [ONE_WORKSPACE, NO_DASHBOARDS, *no_data_searches, empty_query],
        },
        {
            "id": f"{template_id}-build",
            "description": (
                f"After the user confirms, builds the {title} template's folder, cost reports and dashboard exactly"
                " as the template says, checks it, and shares the link"
            ),
            "tags": [template_id],
            "prompt": ask,
            "followUps": ["Yes, go ahead."],
            "referenceAnswer": (
                f"The agent created the {folder_title} folder, the {len(report_titles)} cost reports"
                f" ({'; '.join(report_titles)}) and the {dashboard_title} dashboard with {len(widget_titles)} widgets"
                f" ({'; '.join(widget_titles)}), checked the dashboard, and shared"
                f" https://console.vantage.sh/go/{dashboard_token}."
            ),
            "requiredTools": ["create-folder", "create-cost-report", "create-dashboard", "get-dashboard"],
            "responses": [ONE_WORKSPACE, NO_DASHBOARDS, *searches, preview_query, *build],
        },
    ]


def generated_cases(skill: Skill) -> dict[str, list]:
    """Return the eval cases each of the skill's valid templates generates, by the template's path."""
    templates = skill_templates(skill)
    scopes = mapping(skill_scopes(skill))
    return {
        path: template_cases(template, scopes)
        for path, template in templates.items()
        if not any(dashboard_template_problems(Path(path).stem, template, scopes))
    }


def skill_cases(skill: Skill) -> list:
    """Return the skill's eval cases: each file in its evals/ in path order, then the ones its templates generate."""
    files = [parse_yaml(source) for path, source in sorted(skill.evals.items()) if EVAL_PATH.fullmatch(path)]
    written = [case for cases in files if isinstance(cases, list) for case in cases]
    return written + [case for cases in generated_cases(skill).values() for case in cases]


def bundle_text(skill: Skill) -> str:
    """Return the skill's bundle, all the agent loads of it: its name, its SKILL.md and each file under references/."""
    files = {path: lf(text(source)) for path, source in sorted(skill.files.items())}
    bundle = {"name": skill.name, "body": lf(skill.text or ""), "files": files}
    return json.dumps(bundle, indent=2, ensure_ascii=False) + "\n"


def bundle_path(name: str, bundle: str) -> str:
    """Return the bundle's path in the catalog, named for a hash of its text, so a new version never reuses a name."""
    return f"skills/{name}.{hashlib.sha256(bundle.encode()).hexdigest()[:HASH_CHARS]}.json"


def index_entry(skill: Skill, bundle: str) -> dict:
    """Return the skill's entry in the map: its description and tools, the files it can load, and its bundle's path."""
    fields = mapping(split_frontmatter(skill.text or "")[0])
    return {
        "name": skill.name,
        "description": one_line(fields.get("description")),
        "tools": tool_list(mapping(fields.get("metadata")).get("vantage-tools")),
        "files": sorted(skill.files),
        "bundle": bundle,
    }


def evals_text(skills: list[Skill]) -> str:
    """Return evals.json: every skill's eval cases, which only the test harness reads."""
    cases = {skill.name: skill_cases(skill) for skill in sorted(skills, key=lambda skill: skill.name)}
    found = {name: listed for name, listed in cases.items() if listed}
    return json.dumps({"version": 1, "skills": found}, indent=2, ensure_ascii=False) + "\n"


def agent_files(skills: list[Skill]) -> dict[str, str]:
    """Return the catalog files the agent reads, by path: the map and one bundle per skill."""
    ordered = sorted(skills, key=lambda skill: skill.name)
    bundles = {skill.name: bundle_text(skill) for skill in ordered}
    paths = {name: bundle_path(name, bundle) for name, bundle in bundles.items()}
    index = {"version": 2, "skills": [index_entry(skill, paths[skill.name]) for skill in ordered]}
    return {
        "index.json": json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        **{paths[name]: bundle for name, bundle in bundles.items()},
    }


def catalog_files(skills: list[Skill]) -> dict[str, str]:
    """Return every file in the catalog, by path: the map, one bundle per skill, and evals.json."""
    return agent_files(skills) | {"evals.json": evals_text(skills)}


def repeated_case_ids(skills: list[Skill]) -> list[str]:
    """Return each eval case id that more than one case uses, in any skill and ignoring case: the harness finds a case
    by its id and saves its result as <id>.json, and macOS doesn't tell file names apart by case."""
    counts = Counter(text(mapping(case).get("id")).lower() for skill in skills for case in skill_cases(skill))
    return sorted(case_id for case_id, count in counts.items() if case_id and count > 1)


def size_problems(skills: list[Skill]) -> list[str]:
    """Return why the agent would refuse part of the catalog for its size: the map, or one skill's bundle."""
    index = js_length(agent_files(skills)["index.json"])
    bundles = {skill.name: js_length(bundle_text(skill)) for skill in skills}
    index_problem = f"skills: index.json would be {index} characters, over the agent's {MAX_INDEX_CHARS} limit"
    return [
        *([index_problem] if index > MAX_INDEX_CHARS else []),
        *(
            f"skills/{name}: SKILL.md and references/ come to {size} characters in its bundle,"
            f" over the agent's {MAX_BUNDLE_CHARS} limit"
            for name, size in bundles.items()
            if size > MAX_BUNDLE_CHARS
        ),
    ]


def all_problems(skills: list[Skill]) -> list[str]:
    """Return every problem with the skills and the catalog built from them, each prefixed with the path it's about."""
    conflicts = scope_conflicts({skill.name: skill_scopes(skill) for skill in skills})
    return [
        *(f"skills/{skill.name}: {problem}" for skill in skills for problem in skill_problems(skill)),
        *(f"skills: {conflict}" for conflict in conflicts),
        *(
            f"skills: eval case id {case_id} is used more than once, ignoring case"
            for case_id in repeated_case_ids(skills)
        ),
        *size_problems(skills),
    ]


# Shell: everything above is pure. Below reads skills/ and writes the catalog built from it.

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


def read_text(path: Path) -> str | None:
    """Return a file's text without a byte-order mark, or None when it's missing or isn't UTF-8."""
    try:
        return path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def read_skill(folder: Path) -> Skill:
    """Read one skill folder: SKILL.md, each file under references/ and evals/ (hidden ones aside), and its links."""
    references = sorted(
        path for path in (folder / "references").rglob("*") if path.is_file() and not path.name.startswith(".")
    )
    evals = sorted(path for path in (folder / "evals").rglob("*") if path.is_file() and not path.name.startswith("."))
    paths = [folder, *folder.rglob("*")]
    return Skill(
        name=folder.name,
        text=read_text(folder / "SKILL.md"),
        files={path.relative_to(folder).as_posix(): read_text(path) for path in references},
        evals={path.relative_to(folder).as_posix(): read_text(path) for path in evals},
        links=tuple(sorted(path.relative_to(folder).as_posix() for path in paths if path.is_symlink())),
    )


def read_skills() -> list[Skill]:
    """Read every skill folder under skills/, hidden folders aside."""
    folders = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir() and not path.name.startswith("."))
    return [read_skill(folder) for folder in folders]


def write_catalog(folder: Path, files: dict[str, str]) -> None:
    """Write each catalog file under the folder, making the folders it needs."""
    for path, source in files.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8", newline="\n")


def main() -> int:
    """Check every skill, and with --build write the catalog into a folder once nothing's wrong. Return the status."""
    parser = argparse.ArgumentParser(description="Check skills/, and build the catalog the FinOps Agent reads.")
    parser.add_argument("--build", type=Path, metavar="DIR", help="write the catalog into DIR if every check passes")
    folder = parser.parse_args().build
    skills = read_skills()
    problems = all_problems(skills)
    if problems:
        print("\n".join(problems))
        return 1
    if folder:
        write_catalog(folder, catalog_files(skills))
    print(f"No problems in skills/. Built the catalog in {folder}." if folder else "No problems in skills/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
