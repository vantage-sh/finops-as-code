# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.3", "pytest>=8"]
# ///
"""Tests for check_skills.py, run with `uv run scripts/test_check_skills.py`."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from check_skills import (
    BUILT_IN_SKILLS,
    CHART_TYPES,
    DASHBOARD_TEMPLATES,
    DISPLAY_TYPES,
    SAMPLE_FILTER,
    SAMPLE_SORT,
    SAMPLE_WORKSPACE,
    Skill,
    all_problems,
    catalog_files,
    parse_yaml,
    read_skill,
    skill_problems,
)

TOOLS = "list-workspaces, query-costs"
TEMPLATE_TOOLS = (
    "list-workspaces, query-costs, list-dashboards, create-folder, create-cost-report, create-dashboard, get-dashboard"
)
SCOPES = "## Scopes\n\n```yaml\nai_spend: costs.provider = 'aws'\n```\n"
TABLE = "## Templates\n\n| Template | What it builds |\n|---|---|\n| [Demo](references/demo.yaml) | One report |\n\n"
SETTINGS = "{ display_type: chart, grid: { x: 0, y: 0, w: 6, h: 3 } }"
TEMPLATE = """\
id: demo
title: Demo
description: One report
preview: { scope: ai_spend, groupings: [provider], if_empty: Connect a provider. }
folder: { title: Demo }
cost_reports:
  only: { title: Only, scope: ai_spend, groupings: [provider], date_interval: this_month, chart_type: bar }
dashboard:
  title: Demo
  widgets:
    - { report: only, settings: SETTINGS }
""".replace("SETTINGS", SETTINGS)
CASE = """\
- id: forecast-notes-explain
  description: Explains the forecast
  prompt: Why is my forecast up?
  referenceAnswer: Compute grew.
  requiredTools: [query-costs]
  responses:
    - { tool: query-costs, arguments: { groupings: [service] }, result: { costs: [] } }
"""
JSON_ONLY = (
    "must hold only JSON data: text, numbers, true, false, null, lists, and mappings with text keys (quote a date)"
)


def skill_md(name: str = "demo", description: str = "Builds a demo.", tools: str = TOOLS, body: str = "") -> str:
    """Return a SKILL.md with the given frontmatter values and body."""
    return f"---\nname: {name}\ndescription: {description}\nmetadata:\n  vantage-tools: {tools}\n---\n\n# Skill\n\n{body}"


def template_skill(template: str = TEMPLATE, table: str = TABLE, scopes: str = SCOPES) -> Skill:
    """Return the dashboard-templates skill with one template file."""
    source = skill_md(DASHBOARD_TEMPLATES, tools=TEMPLATE_TOOLS, body=table + scopes)
    return Skill(DASHBOARD_TEMPLATES, source, {"references/demo.yaml": template})


def with_text(field: str, value: str, text: str) -> Skill:
    """Return the demo template skill with one field's text changed, in its file and its Templates row alike."""
    template = TEMPLATE.replace(f"{field}: {value}\n", f"{field}: {text}\n", 1)
    return template_skill(template, TABLE.replace(value, text))


def renamed_template_skill(stem: str) -> Skill:
    """Return the demo template skill with its file, its id and its Templates row all named for the stem."""
    template, table = TEMPLATE.replace("id: demo", f"id: {stem}"), TABLE.replace("demo.yaml", f"{stem}.yaml")
    return replace(template_skill(table=table), files={f"references/{stem}.yaml": template})


def widget_skill(kind: str, height: int) -> Skill:
    """Return the demo template skill with its one widget drawn as the kind, at the height."""
    template = TEMPLATE.replace("display_type: chart", f"display_type: {kind}").replace("h: 3", f"h: {height}")
    return template_skill(template)


def published_rules() -> dict:
    """Return the rules the map publishes: the limits Scout and the console compare with their own."""
    return json.loads(catalog_files([template_skill()])["index.json"])["rules"]


def eval_skill(source: str = CASE, path: str = "evals/explain.yaml") -> Skill:
    """Return a skill that isn't about dashboards, with one eval file."""
    return Skill("forecast-notes", skill_md(name="forecast-notes"), {}, {path: source})


def bundle_of(skills: list[Skill]) -> str:
    """Return the path the map gives the first skill's bundle, in the catalog built from these skills."""
    entries = json.loads(catalog_files(skills)["index.json"])["skills"]
    return next(entry["bundle"] for entry in entries if entry["name"] == skills[0].name)


def problems_with_sizes_hidden(skills: list[Skill]) -> list[str]:
    """Return the problems the check finds, with each size in characters written as N."""
    return [re.sub(r"\d+ characters", "N characters", problem) for problem in all_problems(skills)]


def test_passes_a_template_skill_and_a_skill_that_isnt_about_dashboards() -> None:
    """A dashboard template skill and a forecasting-shaped skill with a reference file and eval cases both pass."""
    forecast = replace(eval_skill(), files={"references/method.md": "# Method\n"})
    assert all_problems([template_skill(), forecast]) == []


@pytest.mark.parametrize(
    ("source", "problem"),
    [
        (skill_md(name="other"), "name must be demo"),
        (skill_md(description='""'), "description must be text"),
        (skill_md(description="x" * 1_025), "description must be text"),
        (skill_md(tools='""'), "metadata.vantage-tools must list"),
        (skill_md(tools="[a, b]"), "metadata must map names to text"),
        (skill_md().replace("metadata:\n", "metadata:\n  2026-11-14: x\n"), "metadata must map names to text"),
        (skill_md().replace("metadata:", "tools: [a]\nmetadata:"), "the Agent Skills spec doesn't define: tools"),
        (skill_md().replace("name: demo", "name: demo\nname: demo"), "must start with YAML frontmatter"),
        ("# No frontmatter\n", "must start with YAML frontmatter"),
        (skill_md(description='"\\uD800"'), "must start with YAML frontmatter"),
    ],
)
def test_frontmatter(source: str, problem: str) -> None:
    """Each broken frontmatter gets the problem that names it."""
    assert any(problem in found for found in skill_problems(Skill("demo", source, {})))


def test_frontmatter_that_isnt_valid_yaml_is_the_only_problem_named() -> None:
    """An unquoted ': ' breaks the YAML, and no case checked against the tools it would have listed piles on."""
    source = skill_md(DASHBOARD_TEMPLATES, "Use when: someone asks.", TEMPLATE_TOOLS, TABLE + SCOPES)
    skill = replace(template_skill(), text=source, evals={"evals/mine.yaml": CASE})
    assert list(skill_problems(skill)) == [
        "SKILL.md must start with YAML frontmatter between --- lines, written as valid YAML with no repeated keys or"
        " aliases (quote a value that has ': ' in it)"
    ]


def test_deeply_nested_yaml_reports_invalid_input_without_a_traceback() -> None:
    """A nesting error is invalid YAML input, so the check can report it instead of crashing."""
    assert parse_yaml("[" * 1_000 + "0" + "]" * 1_000) is None


@pytest.mark.parametrize(
    "source",
    ["&a [*a]", "a: &x 1\nb: *x", "x: " + "1" * 5_000, "x: 2026-13-45", "x: !!bool maybe", "x: !!timestamp foo"],
)
def test_an_alias_or_a_value_pyyaml_cant_build_is_invalid_yaml_without_a_traceback(source: str) -> None:
    """An alias can make a list hold itself, and PyYAML can't build a 5,000-digit number, 2026-13-45 as a date, or
    an explicit tag on a value it doesn't fit."""
    assert parse_yaml(source) is None


def test_an_eval_file_that_holds_itself_gets_its_problem_instead_of_a_traceback() -> None:
    """`&a [*a]` is a list that holds itself, which the build can't write as JSON, so the check names the file."""
    assert all_problems([eval_skill("&a [*a]\n")]) == [
        "skills/forecast-notes: evals/explain.yaml must be a valid YAML list of eval cases, with no repeated keys or"
        " aliases"
    ]


def test_an_eval_case_with_a_date_key_gets_its_problem_instead_of_a_traceback() -> None:
    """The size check builds only the map and bundles the agent loads, so a date key in a result reaches its problem."""
    source = CASE.replace("result: { costs: [] }", "result: { 2026-11-14: 100 }")
    assert all_problems([eval_skill(source)]) == [
        f"skills/forecast-notes: evals/explain.yaml: forecast-notes-explain {JSON_ONLY}"
    ]


@pytest.mark.parametrize(
    ("template", "table", "problem"),
    [
        (TEMPLATE.replace("{ scope: ai_spend", "{ scope: gpu_spend"), TABLE, "preview names scope 'gpu_spend'"),
        (TEMPLATE.replace("title: Only, scope", "title: Only, filter: x, scope"), TABLE, "needs one of scope or filter"),
        (TEMPLATE.replace("report: only", "report: gone"), TABLE, "widgets[0] must name a report"),
        (TEMPLATE.replace("id: demo", "id: other"), TABLE, "id must be demo"),
        (TEMPLATE, TABLE.replace("| One report |", "| Two reports |"), "Templates row for references/demo.yaml"),
        (TEMPLATE, TABLE.replace("references/demo.yaml", "references/gone.yaml"), "demo.yaml needs a row"),
        (TEMPLATE.replace(", date_interval: this_month", ""), TABLE, "cost_reports.only.date_interval must be text"),
        (TEMPLATE.replace("[provider], date", "provider, date"), TABLE, "cost_reports.only.groupings must be a list"),
        (TEMPLATE.replace("{ report: only,", "{ report: only, title: [x],"), TABLE, "widgets[0].title must be text"),
        (TEMPLATE.replace(SETTINGS, "chart"), TABLE, "widgets[0].settings must be a mapping"),
        (TEMPLATE.replace("display_type: chart", "display_type: typo"), TABLE, "settings.display_type must be one of"),
        (TEMPLATE.replace(SETTINGS, "{ display_type: chart }"), TABLE, "settings.grid must set x, y, w and h"),
        (TEMPLATE.replace("x: 0", "x: true"), TABLE, "settings.grid must set x, y, w and h"),
        (TEMPLATE.replace("w: 6", "w: 6.0"), TABLE, "settings.grid must set x, y, w and h"),
        (TEMPLATE.replace("h: 3", "h: 3, z: 1"), TABLE, "settings.grid must set x, y, w and h"),
        (TEMPLATE.replace("x: 0", "1: 0"), TABLE, "settings.grid must set x, y, w and h"),
        (TEMPLATE.replace("x: 0", "x: 7"), TABLE, "settings.grid must fit the dashboard's 12 columns"),
        (TEMPLATE.replace("y: 0", "y: -1"), TABLE, "settings.grid must fit the dashboard's 12 columns"),
        (TEMPLATE.replace("h: 3", "h: 1"), TABLE, "settings.grid must be at least 2 wide and 2 high for a chart"),
        (TEMPLATE.replace("w: 6", "w: 1"), TABLE, "settings.grid must be at least 2 wide and 2 high for a chart"),
        (
            TEMPLATE.replace("display_type: chart", "display_type: table").replace("h: 3", "h: 1"),
            TABLE,
            "settings.grid must be at least 2 wide and 2 high for a table",
        ),
        (
            TEMPLATE.replace("display_type: chart", "display_type: kpi").replace("h: 3", "h: 0"),
            TABLE,
            "settings.grid must be at least 2 wide and 1 high for a kpi",
        ),
        (TEMPLATE.replace(", chart_type: bar", ""), TABLE, "is a chart, so its report must set chart_type"),
        (TEMPLATE.replace("chart_type: bar", "chart_type: typo"), TABLE, "cost_reports.only.chart_type must be one of"),
        (
            TEMPLATE + f"    - {{ report: only, settings: {SETTINGS} }}\n",
            TABLE,
            "widgets[0] and dashboard.widgets[1] overlap on the grid",
        ),
        (
            TEMPLATE.replace("dashboard:\n  title: Demo\n", "dashboard:\n  title: Demo\n  date_interval: this_month\n"),
            TABLE,
            "dashboard.date_interval isn't a field a template's dashboard takes",
        ),
        (
            TEMPLATE.replace("{ report: only,", "{ report: only, chart_type: bar,"),
            TABLE,
            "dashboard.widgets[0].chart_type isn't a field a widget takes",
        ),
        (
            TEMPLATE.replace("title: Only, scope: ai_spend", "title: Only, filter: \"costs.provider = 'openai'\""),
            TABLE,
            "cost_reports.only.filter names provider 'openai', which isn't a Vantage provider key",
        ),
        (
            TEMPLATE.replace("{ scope: ai_spend, groupings", "{ filter: \"costs.provider = 'aws'\", groupings"),
            TABLE,
            "cost_reports.only must use the preview's scope, since Step 3 searches and confirms only that one",
        ),
        (
            TEMPLATE.replace("title: Only, scope: ai_spend", "title: Only, filter: \"costs.provider = 'aws'\""),
            TABLE,
            "cost_reports.only must use the preview's scope, since Step 3 searches and confirms only that one",
        ),
        (
            TEMPLATE.replace("date_interval: this_month", "date_interval: last_6_months"),
            TABLE,
            "cost_reports.only.date_interval must be one of the periods Step 3 looks back over",
        ),
        (
            TEMPLATE.replace("scope: ai_spend", "filter: x").replace("this_month", "last_6_months"),
            TABLE,
            "cost_reports.only.date_interval must be one of the periods Step 3 looks back over",
        ),
        (
            TEMPLATE.replace("this_month", "this_month, settings: { include_credits: true }"),
            TABLE,
            "cost_reports.only.settings isn't a field a template's report takes",
        ),
        (
            TEMPLATE.replace("folder: { title: Demo }", "folder: { title: Demo, description: Costs }"),
            TABLE,
            "folder.description isn't a field a template's folder takes",
        ),
    ],
)
def test_templates(template: str, table: str, problem: str) -> None:
    """Each broken template, or a table that disagrees with the files, gets the problem that names it."""
    assert any(problem in found for found in skill_problems(template_skill(template, table)))


@pytest.mark.parametrize(("field", "value", "limit"), [("title", "Demo", 200), ("description", "One report", 1_024)])
def test_a_title_runs_to_200_characters_and_a_description_to_1024(field: str, value: str, limit: int) -> None:
    """The console's Set up link carries a template's title, so it stops at 200, and a description stops at 1,024."""
    assert all_problems([with_text(field, value, "x" * limit)]) == []
    assert all_problems([with_text(field, value, "x" * (limit + 1))]) == [
        f"skills/dashboard-templates: references/demo.yaml: {field} must be text of 1 to {limit} characters"
    ]


def test_a_template_id_runs_to_240_characters() -> None:
    """A template's eval case ids add up to 10 characters to its id, and the harness stops a case id at 250."""
    assert all_problems([renamed_template_skill("x" * 240)]) == []
    too_long = "x" * 241
    assert all_problems([renamed_template_skill(too_long)]) == [
        f"skills/dashboard-templates: references/{too_long}.yaml: id must be at most 240 characters, so its eval case"
        " ids fit in 250"
    ]


def test_a_widget_ends_by_row_100() -> None:
    """The gallery draws a template's first 100 rows, so a widget can end on the last one and no further down."""
    assert all_problems([template_skill(TEMPLATE.replace("y: 0", "y: 97"))]) == []
    assert all_problems([template_skill(TEMPLATE.replace("y: 0", "y: 98"))]) == [
        "skills/dashboard-templates: references/demo.yaml: dashboard.widgets[0].settings.grid must fit the dashboard's"
        " 12 columns and the gallery's 100 rows, from x 0 and y 0"
    ]


def test_the_map_publishes_its_rules_under_the_keys_scout_and_the_console_read() -> None:
    """Scout and the console look each rule up by name, so a renamed key hides that rule from them."""
    rules = published_rules()
    assert set(rules) == {
        "max_index_chars", "max_file_chars", "max_bundle_chars", "max_description_chars", "reserved_names", "templates"
    }
    assert set(rules["templates"]) == {
        "display_types", "chart_types", "grid_columns", "max_grid_rows", "min_grid_width", "min_grid_height",
        "max_id_chars", "max_title_chars", "max_description_chars",
    }
    assert set(rules["templates"]["min_grid_height"]) == set(rules["templates"]["display_types"])


# Each published template limit, a template at that limit, and the step that takes it one past: the check takes the
# first and refuses the second, so the published number is where the check really stops.
PUBLISHED_LIMITS = [
    (("grid_columns",), lambda n: template_skill(TEMPLATE.replace("x: 0", f"x: {n - 6}")), 1),
    (("max_grid_rows",), lambda n: template_skill(TEMPLATE.replace("y: 0", f"y: {n - 3}")), 1),
    (("max_id_chars",), lambda n: renamed_template_skill("x" * n), 1),
    (("max_title_chars",), lambda n: with_text("title", "Demo", "x" * n), 1),
    (("max_description_chars",), lambda n: with_text("description", "One report", "x" * n), 1),
    (("min_grid_width",), lambda n: template_skill(TEMPLATE.replace("w: 6", f"w: {n}")), -1),
    (("min_grid_height", "kpi"), lambda n: widget_skill("kpi", n), -1),
    (("min_grid_height", "chart"), lambda n: widget_skill("chart", n), -1),
    (("min_grid_height", "table"), lambda n: widget_skill("table", n), -1),
]


@pytest.mark.parametrize(("path", "at", "step"), PUBLISHED_LIMITS, ids=[".".join(row[0]) for row in PUBLISHED_LIMITS])
def test_each_published_template_limit_is_where_the_check_stops(
    path: tuple[str, ...], at: Callable[[int], Skill], step: int
) -> None:
    """A template at a published limit passes and one a step past fails, so the map publishes the check's own rules."""
    limit = published_rules()["templates"]
    for key in path:
        limit = limit[key]
    assert all_problems([at(limit)]) == []
    assert all_problems([at(limit + step)]) != []


def test_the_map_publishes_every_kind_the_check_takes_and_every_name_it_refuses() -> None:
    """The published lists are the check's own, so none can shrink unseen, and each kind passes and each name fails."""
    rules = published_rules()
    assert rules["templates"]["display_types"] == list(DISPLAY_TYPES)
    assert rules["templates"]["chart_types"] == list(CHART_TYPES)
    assert set(rules["reserved_names"]) == BUILT_IN_SKILLS
    kinds = [widget_skill(kind, 3) for kind in rules["templates"]["display_types"]]
    charts = [
        template_skill(TEMPLATE.replace("chart_type: bar", f"chart_type: {chart}"))
        for chart in rules["templates"]["chart_types"]
    ]
    assert [all_problems([skill]) for skill in kinds + charts] == [[] for _ in kinds + charts]
    refused = [list(skill_problems(Skill(name, skill_md(name=name), {}))) for name in rules["reserved_names"]]
    assert all(any("built-in skills" in problem for problem in problems) for problems in refused)


def test_a_kpi_can_be_one_row_high() -> None:
    """The console permits a KPI one row high, while a chart or table needs two."""
    template = TEMPLATE.replace("display_type: chart", "display_type: kpi").replace("h: 3", "h: 1")
    assert all_problems([template_skill(template)]) == []


def test_a_chart_type_typo_is_reported_once_on_its_report() -> None:
    """A misspelled chart_type gets one problem, on its report, and none on the chart that uses it."""
    template = TEMPLATE.replace("chart_type: bar", "chart_type: typo")
    assert [problem for problem in skill_problems(template_skill(template)) if "chart_type" in problem] == [
        "references/demo.yaml: cost_reports.only.chart_type must be one of area, line, bar, multi_bar, pie"
    ]


def test_the_map_carries_thumbnails_in_table_order_with_only_the_fields_a_tile_needs() -> None:
    """The table orders thumbnails, widget titles fall back to reports, and only charts carry a chart type."""
    template = parse_yaml(TEMPLATE)
    widgets = [
        {"report": "only", "settings": {"display_type": "chart", "grid": {"x": 0, "y": 0, "w": 6, "h": 2}}},
        {"report": "only", "title": "Total", "settings": {
            "display_type": "kpi", "kpi_calculation": "sum", "grid": {"x": 6, "y": 0, "w": 6, "h": 1},
        }},
        {"report": "only", "settings": {"display_type": "table", "grid": {"x": 6, "y": 1, "w": 6, "h": 2}}},
    ]
    template = {**template, "dashboard": {**template["dashboard"], "widgets": widgets}}
    other = {**template, "id": "other", "title": "Other"}
    table = TABLE.replace("| [Demo]", "| [Other](references/other.yaml) | One report |\n| [Demo]")
    skill = replace(template_skill(table=table), files={
        "references/demo.yaml": yaml.safe_dump(template), "references/other.yaml": yaml.safe_dump(other),
    })
    assert all_problems([skill]) == []
    catalog = catalog_files([skill])
    entry = json.loads(catalog["index.json"])["skills"][0]
    expected = [
        {"title": "Only", "display_type": "chart", "chart_type": "bar", "grid": {"x": 0, "y": 0, "w": 6, "h": 2}},
        {"title": "Total", "display_type": "kpi", "grid": {"x": 6, "y": 0, "w": 6, "h": 1}},
        {"title": "Only", "display_type": "table", "grid": {"x": 6, "y": 1, "w": 6, "h": 2}},
    ]
    assert entry["templates"] == [
        {"id": "other", "title": "Other", "description": "One report", "widgets": expected},
        {"id": "demo", "title": "Demo", "description": "One report", "widgets": expected},
    ]
    assert set(json.loads(catalog[entry["bundle"]])) == {"name", "body", "files"}


def test_a_broken_template_gets_its_problem_and_no_thumbnail() -> None:
    """The size check can build the map for a broken template without indexing into its missing grid."""
    skill = template_skill(TEMPLATE.replace(SETTINGS, "{ display_type: chart }"))
    assert any("settings.grid must set x, y, w and h" in problem for problem in all_problems([skill]))
    assert "templates" not in json.loads(catalog_files([skill])["index.json"])["skills"][0]


def test_a_report_sets_its_period_only_as_a_date_interval() -> None:
    """Vantage gives a report with a start_date or end_date a fixed range in place of its date_interval, which can reach
    back past what Step 3 searched, so either one fails, quoted or as a YAML date, which isn't JSON data either."""
    template = TEMPLATE.replace("this_month", 'this_month, start_date: "2020-01-01", end_date: 2026-11-14')
    fields = [
        f"cost_reports.only.{name} isn't a field a template's report takes" for name in ("start_date", "end_date")
    ]
    assert all_problems([template_skill(template)]) == [
        f"skills/dashboard-templates: references/demo.yaml: {problem}" for problem in (JSON_ONLY, *fields)
    ]


@pytest.mark.parametrize(
    ("settings", "problems"),
    [
        (SETTINGS.replace("chart,", "chart, 2026-11-14: x,"), [JSON_ONLY]),
        (SETTINGS.replace("chart,", "chart, !!binary aGk=: x,"), [JSON_ONLY]),
        (SETTINGS.replace("chart,", "chart, on: x,"), [JSON_ONLY]),
        (
            SETTINGS.replace("chart,", "!!set { chart },"),
            [JSON_ONLY, "dashboard.widgets[0].settings.display_type must be one of kpi, chart, table"],
        ),
        (SETTINGS.replace("chart,", "chart, '2026-11-14': x, 'on': x,"), []),
    ],
)
def test_a_template_holds_only_json_data(settings: str, problems: list[str]) -> None:
    """A widget's settings go into the build case, so a key YAML reads as a date, bytes or true, or a set, fails with
    the template named instead of a traceback or a fixture the template doesn't spell, and a quoted key passes."""
    template = TEMPLATE.replace(SETTINGS, settings)
    assert all_problems([template_skill(template)]) == [
        f"skills/dashboard-templates: references/demo.yaml: {problem}" for problem in problems
    ]


def test_a_scope_without_a_sample_account_generates_no_eval_cases() -> None:
    """The fake account's searches are written for ai_spend, so a template with another scope fails the check."""
    skill = template_skill(TEMPLATE.replace("ai_spend", "gpu_spend"), scopes=SCOPES.replace("ai_spend", "gpu_spend"))
    assert any("preview.scope gpu_spend has no sample account" in problem for problem in skill_problems(skill))
    assert json.loads(catalog_files([skill])["evals.json"])["skills"] == {}


def test_a_skill_cant_take_the_name_of_one_the_agent_has_built_in() -> None:
    """The agent keeps its built-in skill and drops a catalog skill with the same name, so the check refuses it."""
    problem = "the folder name terraform is one of the agent's built-in skills, which it keeps instead of this one"
    assert problem in skill_problems(Skill("terraform", skill_md(name="terraform"), {}))


def test_another_skill_can_keep_templates_of_its_own() -> None:
    """Only dashboard-templates lists dashboard templates, so another skill's Templates table and YAML pass as is."""
    table = TABLE.replace("[Demo](references/demo.yaml) | One report", "[Note](references/note.yaml) | A note")
    note = "id: note\ntitle: Note\nsubject: Costs jumped\nbody: Take a look.\n"
    skill = Skill("anomaly-triage", skill_md("anomaly-triage", body=table), {"references/note.yaml": note})
    assert all_problems([skill]) == []
    assert json.loads(catalog_files([skill])["evals.json"])["skills"] == {}


def test_a_scope_must_name_real_provider_keys() -> None:
    """VQL returns no costs and no error for a misspelled provider, so a scope that names one fails."""
    skill = template_skill(scopes=SCOPES.replace("'aws'", "'amazon'"))
    assert "scope 'ai_spend' names provider 'amazon', which isn't a Vantage provider key" in skill_problems(skill)


def test_a_template_generates_three_cases_that_build_exactly_what_it_says() -> None:
    """A plain ask, a no-data case and a build: the scope's two searches, the filter they lead to, then the writes."""
    skills = json.loads(catalog_files([template_skill()])["evals.json"])["skills"]
    plain_ask, no_data, build = cases = skills[DASHBOARD_TEMPLATES]
    assert [case["id"] for case in cases] == ["demo-plain-ask", "demo-no-data", "demo-build"]
    assert plain_ask["referenceAnswer"].startswith(
        "Acme Corp's costs in the template's preview come to $9,268.30: cursor $4,120.55, anthropic $2,875.10,"
    )
    assert SAMPLE_SORT in plain_ask["referenceAnswer"]
    reads = [
        {
            "filter": "costs.provider = 'aws'",
            "groupings": ["provider", "service"],
            "date_bin": "month",
            "start_date": "$monthStart-4",
            "workspace_token": SAMPLE_WORKSPACE,
        },
        {
            "filter": "costs.provider = '*'",
            "groupings": ["provider"],
            "date_bin": "month",
            "start_date": "$monthStart-4",
            "workspace_token": SAMPLE_WORKSPACE,
        },
        {
            "filter": SAMPLE_FILTER,
            "groupings": ["provider"],
            "date_bin": "month",
            "workspace_token": SAMPLE_WORKSPACE,
        },
    ]
    assert plain_ask["responses"][1]["arguments"] == {"workspace_token": SAMPLE_WORKSPACE}
    assert [fixture["arguments"] for fixture in plain_ask["responses"][2:]] == reads
    assert [fixture["arguments"] for fixture in no_data["responses"][2:]] == reads
    assert plain_ask["responses"][2]["result"]["total_cost"]["amount"] == "8535.95"
    no_data_costs = [fixture["result"]["costs"] for fixture in no_data["responses"][2:]]
    assert no_data_costs == [[], [{"amount": "1404.00", "currency": "USD", "provider": "datadog"}], []]

    assert [fixture["tool"] for fixture in build["responses"]] == [
        *("list-workspaces", "list-dashboards", "query-costs", "query-costs", "query-costs"),
        *("create-folder", "create-cost-report", "create-dashboard", "get-dashboard"),
    ]
    report, dashboard = build["responses"][6:8]
    assert report["arguments"] == {
        "title": "Only",
        "groupings": ["provider"],
        "date_interval": "this_month",
        "chart_type": "bar",
        "filter": SAMPLE_FILTER,
        "folder_token": "fldr_eval_demo",
        "workspace_token": SAMPLE_WORKSPACE,
    }
    assert report["absent"] == ["date_bin"]
    assert dashboard["arguments"]["widgets"] == [
        {
            "widgetable_token": "rprt_eval_demo_only",
            "settings": {"display_type": "chart", "grid": {"x": 0, "y": 0, "w": 6, "h": 3}},
        }
    ]
    assert dashboard["absent"] == ["date_interval", "start_date", "end_date", "date_bin"]
    assert build["followUps"] == ["Yes, go ahead."]
    assert build["requiredTools"] == ["create-folder", "create-cost-report", "create-dashboard", "get-dashboard"]


def test_a_template_with_a_filter_searches_for_nothing_and_passes_it_as_written() -> None:
    """A preview and a report that name a filter instead of a scope keep its VQL, so their cases run no searches."""
    template = TEMPLATE.replace("scope: ai_spend", "filter: \"costs.provider = 'gcp'\"")
    skills = json.loads(catalog_files([template_skill(template)])["evals.json"])["skills"]
    plain_ask, no_data, build = skills[DASHBOARD_TEMPLATES]
    query = {
        "filter": "costs.provider = 'gcp'",
        "groupings": ["provider"],
        "date_bin": "month",
        "workspace_token": SAMPLE_WORKSPACE,
    }
    assert [fixture["arguments"] for fixture in plain_ask["responses"][2:]] == [query]
    assert [fixture["arguments"] for fixture in no_data["responses"][2:]] == [query]
    assert SAMPLE_SORT not in plain_ask["referenceAnswer"]
    assert build["responses"][4]["arguments"]["filter"] == "costs.provider = 'gcp'"


def test_the_build_puts_template_cases_in_evals_json_after_the_skills_own() -> None:
    """Nobody commits a template's cases, a broken template has none, and a copy of them in evals/ fails on its ids."""
    skill = replace(template_skill(), evals={"evals/mine.yaml": CASE})
    cases = json.loads(catalog_files([skill])["evals.json"])["skills"][DASHBOARD_TEMPLATES]
    assert [case["id"] for case in cases] == ["forecast-notes-explain", "demo-plain-ask", "demo-no-data", "demo-build"]

    broken = template_skill(TEMPLATE.replace("report: only", "report: gone"))
    assert json.loads(catalog_files([broken])["evals.json"])["skills"] == {}
    copied = replace(skill, evals={"evals/copy.yaml": yaml.safe_dump(cases[1:2])})
    assert "skills: eval case id demo-plain-ask is used more than once, ignoring case" in all_problems([copied])


def test_generated_cases_are_checked_like_written_ones() -> None:
    """A template skill whose vantage-tools leaves out a tool its generated cases need fails, named at the template."""
    skill = template_skill()
    narrowed = replace(skill, text=skill.text.replace(" create-folder,", ""))
    assert (
        "skills/dashboard-templates: references/demo.yaml: demo-build.requiredTools has tools the skill's vantage-tools"
        " doesn't list: create-folder"
    ) in all_problems([narrowed])


@pytest.mark.parametrize(
    ("source", "path", "problem"),
    [
        (CASE.replace("  prompt: Why is my forecast up?\n", ""), "evals/explain.yaml", "explain.prompt must be text"),
        (CASE.replace("id: forecast-notes-explain", "id: ../escape"), "evals/explain.yaml", "id must be 1 to 250"),
        (CASE + "  strictFixtures: true\n", "evals/explain.yaml", "fields the harness doesn't read: strictFixtures"),
        (
            CASE.replace("[query-costs]", "[create-dashboard]"),
            "evals/explain.yaml",
            "requiredTools has tools the skill's vantage-tools doesn't list: create-dashboard",
        ),
        (CASE.replace("tool: query-costs", "tool: delete-folder"), "evals/explain.yaml", "responses[0].tool must be"),
        (CASE.replace(", result: { costs: [] }", ""), "evals/explain.yaml", "responses[0] needs a result"),
        (CASE.replace("[service]", "[2026-11-13]"), "evals/explain.yaml", "must hold only JSON data"),
        ("id: not-a-list\n", "evals/explain.yaml", "must be a valid YAML list of eval cases"),
        (CASE, "evals/explain.md", "must be a .yaml file of eval cases"),
    ],
)
def test_eval_cases(source: str, path: str, problem: str) -> None:
    """Each broken eval case or file gets the problem that names it."""
    assert any(problem in found for found in skill_problems(eval_skill(source, path)))


def test_an_eval_case_id_is_used_once_across_every_skill() -> None:
    """The harness finds a case by its id and saves its result as <id>.json, which macOS can't tell apart by case, so
    two skills can't share one, even with different capitals."""
    problem = "skills: eval case id forecast-notes-explain is used more than once, ignoring case"
    other = Skill("other", skill_md(name="other"), {}, {"evals/copy.yaml": CASE})
    assert problem in all_problems([eval_skill(), other])
    shouted = replace(other, evals={"evals/copy.yaml": CASE.replace("forecast-notes", "Forecast-Notes")})
    assert problem in all_problems([eval_skill(), shouted])


def test_an_eval_case_id_can_run_to_250_characters() -> None:
    """The harness saves a case's result as <id>.json and a file name holds 255 bytes, so 250 passes and 251 fails."""
    assert all_problems([eval_skill(CASE.replace("forecast-notes-explain", "x" * 250))]) == []
    too_long = "x" * 251
    assert all_problems([eval_skill(CASE.replace("forecast-notes-explain", too_long))]) == [
        f"skills/forecast-notes: evals/explain.yaml: {too_long}.id must be 1 to 250 letters, digits, '.', '_' and '-'"
    ]


def test_a_scope_means_the_same_vql_in_every_skill() -> None:
    """Two skills can share a scope name only with the same VQL."""
    other = Skill("other", skill_md(name="other", body=SCOPES.replace("'aws'", "'gcp'")), {})
    found = all_problems([template_skill(), other])
    assert "skills: scope ai_spend means different VQL in dashboard-templates, other" in found


def test_files_the_agent_cant_load_fail() -> None:
    """Oversized, non-UTF-8 and oddly named files fail."""
    files = {"references/big.md": "\N{GRINNING FACE}" * 32_001, "references/x.bin": None, "references/a b.md": "x"}
    found = all_problems([Skill("demo", skill_md(), files)])
    assert "skills/demo: references/big.md is 64002 characters, over the 64000 limit" in found
    assert "skills/demo: references/x.bin isn't UTF-8 text" in found
    assert "skills/demo: references/a b.md may only use letters, digits, '.', '_' and '-'" in found


def test_each_file_is_measured_with_the_lf_line_endings_its_bundle_holds() -> None:
    """SKILL.md and a reference at the cap pass with CRLF line endings, since the agent gets them with LF."""
    lines = "x\n" * 32_000
    at_cap = skill_md(body=lines[: 64_000 - len(skill_md())])
    crlf = Skill("demo", at_cap.replace("\n", "\r\n"), {"references/notes.md": lines.replace("\n", "\r\n")})
    assert all_problems([crlf]) == []
    over = replace(crlf, files={"references/notes.md": f"{lines}x".replace("\n", "\r\n")})
    assert all_problems([over]) == ["skills/demo: references/notes.md is 64001 characters, over the 64000 limit"]


def test_the_map_and_each_bundle_must_fit_the_agents_caps() -> None:
    """A skill whose files outgrow its bundle's cap fails, though each file fits, and so does a map over its own cap."""
    files = {f"references/part-{number}.md": "x" * 63_000 for number in range(8)}
    assert problems_with_sizes_hidden([Skill("demo", skill_md(), files)]) == [
        "skills/demo: SKILL.md and references/ come to N characters in its bundle, over the agent's 500000 limit"
    ]
    many = [Skill(f"skill-{number}", skill_md(f"skill-{number}", "x" * 1_000), {}) for number in range(200)]
    assert problems_with_sizes_hidden(many) == [
        "skills: index.json would be N characters, over the agent's 200000 limit"
    ]


def test_the_map_names_each_skill_and_its_bundle_carries_the_skill_with_lf_line_endings() -> None:
    """The agent offers a skill from the map and loads its bundle on first use: SKILL.md and references, never evals."""
    files, evals = {"references/demo.yaml": "id: demo\r\n"}, {"evals/x.yaml": CASE}
    skill = Skill("demo", skill_md().replace("\n", "\r\n"), files, evals)
    catalog = catalog_files([skill])
    bundle = bundle_of([skill])
    assert re.fullmatch(r"skills/demo\.[0-9a-f]{12}\.json", bundle)
    assert list(catalog) == ["index.json", bundle, "evals.json"]
    entry = {
        "name": "demo",
        "description": "Builds a demo.",
        "tools": TOOLS.split(", "),
        "files": ["references/demo.yaml"],
        "bundle": bundle,
    }
    assert json.loads(catalog["index.json"]) == {"version": 2, "rules": published_rules(), "skills": [entry]}
    assert json.loads(catalog[bundle]) == {
        "name": "demo",
        "body": skill_md(),
        "files": {"references/demo.yaml": "id: demo\n"},
    }


def test_a_bundle_gets_a_new_name_when_its_skill_changes_and_only_then() -> None:
    """Editing SKILL.md or a reference renames the bundle. Its evals, another skill and CRLF line endings don't."""
    skill = template_skill()
    bundle = bundle_of([skill])
    assert bundle_of([replace(skill, text=f"{skill.text}\nOne more step.\n")]) != bundle
    assert bundle_of([replace(skill, files={"references/demo.yaml": f"{TEMPLATE}# Note\n"})]) != bundle
    assert bundle_of([replace(skill, evals={"evals/mine.yaml": CASE})]) == bundle
    assert bundle_of([skill, eval_skill()]) == bundle
    crlf = {path: source.replace("\n", "\r\n") for path, source in skill.files.items()}
    assert bundle_of([replace(skill, text=skill.text.replace("\n", "\r\n"), files=crlf)]) == bundle


def test_a_symbolic_link_anywhere_in_a_skill_folder_fails(tmp_path: Path) -> None:
    """The build would publish whatever a link points at, so reading a real folder names every link, its own too."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "config").write_text('[http "https://github.com/"]\n\textraheader = AUTHORIZATION: basic FAKE\n')
    (outside / "cases.yaml").write_text(CASE)
    (outside / "SKILL.md").write_text(skill_md())
    folder = tmp_path / "skills" / "demo"
    (folder / "references").mkdir(parents=True)
    (folder / "evals").mkdir()
    (folder / "SKILL.md").write_text(skill_md())
    (folder / "references" / "method.md").write_text("# Method\n")
    assert all_problems([read_skill(folder)]) == []

    linked_skill = tmp_path / "linked" / "demo"
    linked_skill.parent.mkdir()
    linked_skill.symlink_to(folder, target_is_directory=True)
    assert all_problems([read_skill(linked_skill)]) == [
        "skills/demo: the folder is a symbolic link, and a skill folder holds only regular files"
    ]

    (folder / "SKILL.md").unlink()
    (folder / "SKILL.md").symlink_to(outside / "SKILL.md")
    (folder / "references" / "notes.md").symlink_to(outside / "config")
    (folder / "references" / "linked").symlink_to(outside, target_is_directory=True)
    (folder / "evals" / "cases.yaml").symlink_to(outside / "cases.yaml")
    assert all_problems([read_skill(folder)]) == [
        f"skills/demo: {path} is a symbolic link, and a skill folder holds only regular files"
        for path in ("SKILL.md", "evals/cases.yaml", "references/linked", "references/notes.md")
    ]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
