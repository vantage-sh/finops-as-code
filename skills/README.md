# FinOps Agent Skills

Each folder here is one skill for the [Vantage FinOps Agent](https://docs.vantage.sh/vantage_finops_agent): a `SKILL.md` with the steps the agent follows, plus any files it reads when it needs them. On every merge to `main`, a workflow builds the agent's catalog from these folders and pushes it to this repository's `catalog` branch, so a merged skill or template reaches the agent without an agent release.

| Skill | What it does |
|---|---|
| [`dashboard-templates`](dashboard-templates/SKILL.md) | Builds a ready-made dashboard from a template, such as the AI spend overview: AI spend this month, a three-month trend by provider, and this month by model |

## Use a skill

Ask the FinOps Agent in plain words, for example "Set up an AI spend dashboard for me." It shows a preview and asks before it creates anything.

The skills follow the open [Agent Skills](https://agentskills.io/specification) format, so other agents can run them once they're connected to the [Vantage MCP server](https://docs.vantage.sh/vantage_mcp). Copy a skill's folder to where your agent looks for skills:

| Agent | For you | For one project |
|---|---|---|
| [Claude Code](https://code.claude.com/docs/en/skills) | `~/.claude/skills/` | `.claude/skills/` |
| [Codex](https://developers.openai.com/codex/skills) | `~/.agents/skills/` | `.agents/skills/` |
| [Cursor](https://cursor.com/docs/skills) | `~/.cursor/skills/` or `~/.agents/skills/` | `.cursor/skills/` or `.agents/skills/` |

```bash
git clone https://github.com/vantage-sh/finops-as-code.git
mkdir -p ~/.claude/skills
cp -R finops-as-code/skills/dashboard-templates ~/.claude/skills/
```

All three pick up a new skill on their own. If Codex doesn't list it, restart Codex. Cursor also reads the Claude Code and Codex folders, so one copy can serve two agents.

## Add a template or a skill

A template is one more instance of work a skill already does. A new dashboard is a YAML file in `dashboard-templates/references/` plus one row in that skill's Templates table. Templates belong to `dashboard-templates`: the check reads only its Templates table as dashboard templates, so a `## Templates` section in another skill is just part of its steps. A skill is a new kind of work, such as explaining a forecast or triaging an anomaly, and gets its own folder.

Everything a skill needs lives in its folder, so a change touches that folder and nothing else. There's nothing to regenerate or commit next to it: the build makes the rest. A skill folder holds only regular files, and the check fails on a symbolic link anywhere in it, since the build would publish whatever the link points at.

```
skills/
├── dashboard-templates/
│   ├── SKILL.md                       frontmatter, steps, Templates table, Scopes
│   └── references/
│       └── ai-spend-overview.yaml     one template, read when the agent builds it
└── <another-skill>/
    ├── SKILL.md
    ├── references/                    files the steps tell the agent to read
    └── evals/                         eval cases, as YAML
```

There's no preview image to add: a template's thumbnail is drawn from its widgets, as [Template thumbnails](#template-thumbnails) describes.

### Frontmatter

```markdown
---
name: dashboard-templates
description: What the skill does and when to use it.
compatibility: Needs the Vantage MCP server's cost and dashboard tools.
metadata:
  vantage-tools: list-workspaces, query-costs, create-dashboard
---
```

- The frontmatter starts on the first line and uses only the spec's fields: `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools`.
- `name` matches the folder name: lowercase letters, digits and single hyphens, at most 64 characters. It can't be `anomaly-investigation`, `autopilot` or `terraform`, the agent's built-in skills, since the agent keeps those instead.
- `description` says what the skill does and when to use it, in at most 1,024 characters. Every FinOps Agent session that can run the skill sees it, and it's how the agent decides to load the skill.
- `vantage-tools` lists every Vantage MCP tool the skill calls, by exact name, comma-separated on one line. It can't be empty. The agent offers the skill only to sessions that have all of them.

### The steps

- Name tools exactly, and point at other files by their path in the folder, such as `references/ai-spend-overview.yaml`. The FinOps Agent can load only the files in `references/`.
- Don't depend on `scripts/`. Claude Code can run a script, but the FinOps Agent can't.
- Keep each file under 64,000 characters, and a skill's `SKILL.md` and `references/` under 500,000 together.
- Nothing account-specific, because this repository is public: no customer names, tokens, amounts or screenshots of real accounts.

### Scopes

A scope names a search for the costs a template covers. A skill defines its scopes in a ```` ```yaml ```` block under `## Scopes`, and a template's preview and every one of its reports set `scope: ai_spend` instead of a `filter`. The agent runs the scope's VQL, sorts what it finds by provider and service, asks the user to confirm, and builds with a filter for just those. `ai_spend` finds the costs Vantage tags with the AI model that ran them (`vntg:ai:model`), so a provider Vantage starts tagging shows up with no change here. Step 3 looks back to the first day of the month four months ago, for a scope's searches and a filter's check alike. That covers `last_3_months` even in a month's first two days, when Vantage's two-day cost delay starts it a month earlier, so a report can use `last_3_months` at most, and the check fails a longer period. A template's eval cases run against a sample account that `scripts/check_skills.py` writes for `ai_spend`, so a template with another scope fails the check until the script gets a sample for it. A scope name means the same VQL in every skill that defines it, and the check fails if two skills disagree.

### The check and the catalog

`scripts/check_skills.py` checks every skill: the frontmatter rules above, file names and sizes, each template against its Templates row and the Scopes block, scope names across skills, provider keys in VQL, and every eval case. A template's folder takes only a `title`, and each report only a `title`, a `scope` or `filter`, `groupings`, a `date_interval`, and optionally `date_bin` and `chart_type`, since the agent passes them to Vantage. A report never sets `start_date` or `end_date`, which would replace its `date_interval` with fixed dates that can reach back past what Step 3 searched. A template and every eval case hold only JSON data, since `evals.json` carries them: quote a date, and any key YAML would read as something other than text, like `on`, `~` or `1`. A provider a template names has to be in the script's `PROVIDER_KEYS`, since VQL returns no costs and no error for a key it doesn't know. Run it with [uv](https://docs.astral.sh/uv/):

```bash
uv run scripts/check_skills.py
```

With `--build`, it also writes the catalog into a folder, once every check passes. The workflow runs exactly this on every merge to `main`, and pushes the folder to the `catalog` branch as one commit that names the `main` commit it was built from:

```bash
uv run scripts/check_skills.py --build /tmp/catalog
```

| File | What it holds | Who reads it |
|---|---|---|
| `index.json` | Each skill's name, description and tools, its file paths, the path of its bundle, each template's thumbnail, and the rules the check holds them to | The agent, when a session starts, and anything that draws the templates |
| `skills/<skill>.<hash>.json` | One skill's bundle: its `SKILL.md` and every file under its `references/` | The agent, the first time a session loads that skill |
| `evals.json` | Every eval case, with the cases generated from each template | The test harness only |

A bundle's name carries a hash of its content, so it changes whenever the skill does, and the map never points at a stale copy. The branch keeps every bundle it has published, a few KB per skill edit, so an agent still holding an older map can always load what it names. Only the workflow writes to `catalog`.

A pull request that touches `skills/` runs the check's tests (`uv run scripts/test_check_skills.py`) and the same build into a temporary folder, so a pull request that passes is one that builds.

To try a change before it merges, copy or link your working folder into one of the agent folders above, with the Vantage MCP server connected.

### Template thumbnails

A template's thumbnail is drawn from its widgets, so the check holds each one to what both the dashboard and the drawing need: `settings.display_type` is `kpi`, `chart` or `table`, `settings.grid` sets whole numbers `x`, `y`, `w` and `h` on the dashboard's 12 columns and within its first 100 rows, at least 2 wide and 2 high (1 high for a KPI), no two widgets overlap, and a chart's report sets `chart_type` to `area`, `line`, `bar`, `multi_bar` or `pie`.

The build copies them into the `dashboard-templates` entry in `index.json`, in the Templates table's order:

```json
"templates": [
  {
    "id": "ai-spend-overview",
    "title": "AI spend overview",
    "description": "AI spend this month, a three-month trend by provider, and this month by model",
    "widgets": [
      { "title": "Total AI Spend This Month", "display_type": "kpi", "grid": { "x": 0, "y": 0, "w": 4, "h": 1 } },
      { "title": "AI Spend by Provider, Last 3 Months", "display_type": "chart", "chart_type": "bar", "grid": { "x": 0, "y": 1, "w": 6, "h": 3 } },
      { "title": "AI Spend by Model, This Month", "display_type": "table", "grid": { "x": 6, "y": 1, "w": 6, "h": 3 } }
    ]
  }
]
```

To draw one, lay out 12 equal columns and as many equal rows as the lowest widget reaches, place each widget from column `x + 1` across `w` columns and from row `y + 1` down `h` rows, and draw its kind. The agent ignores `templates`. A template's `id` runs to 240 characters, since its eval case ids add up to 10 and stop at 250, and its `title` to 200, since the console's Set up link carries both. Its `description` runs to 1,024, like a skill's. Whatever draws them reads a public repository over the network, so it shows every title and description as text, skips a template whose id, title or description runs longer, and skips a widget whose kind or numbers fall outside these rules.

### The rules in the map

`index.json` also carries `rules`, the limits the check holds every skill and template to. The apps that read the catalog compare their own limits with these instead of copying them:

```json
"rules": {
  "max_index_chars": 200000,
  "max_file_chars": 64000,
  "max_bundle_chars": 500000,
  "max_description_chars": 1024,
  "reserved_names": ["anomaly-investigation", "autopilot", "terraform"],
  "templates": {
    "display_types": ["kpi", "chart", "table"],
    "chart_types": ["area", "line", "bar", "multi_bar", "pie"],
    "grid_columns": 12,
    "max_grid_rows": 100,
    "min_grid_width": 2,
    "min_grid_height": { "kpi": 1, "chart": 2, "table": 2 },
    "max_id_chars": 240,
    "max_title_chars": 200,
    "max_description_chars": 1024
  }
}
```

Characters count the way JavaScript counts a string's length. The agent and the console check `rules` every time they fetch the map, and report any rule they can't take: a maximum past their own, a minimum under it, a grid that isn't 12 columns, a kind they don't draw, or a bundled skill's name the list leaves out. They keep serving what they can either way. Their own limits stay in their code, so this file can't raise them, which means loosening a rule past one of them takes a change to that app first.

### Eval cases

An eval case is a conversation the FinOps Agent's test harness plays against a fake Vantage account, then grades. A skill keeps its cases in `evals/`, as a YAML list in one or more files:

```yaml
- id: forecast-notes-top-service
  description: Names the service that drives this month's costs
  prompt: What's driving my costs this month?
  referenceAnswer: Amazon EC2, at $1,200.00 of this month's $1,500.00.
  requiredTools: [query-costs]
  responses:
    - tool: query-costs
      arguments: { groupings: [service] }
      result:
        costs:
          - { service: Amazon EC2, amount: "1200.00", currency: USD }
          - { service: Amazon S3, amount: "300.00", currency: USD }
        total_cost: { amount: "1500.00", currency: USD }
```

- `id`, `description`, `prompt`, `referenceAnswer` and `responses` are required, and an `id` is used once across every skill. `followUps` sends more messages in the same session, such as a yes at a confirm step, and a judge grades the last reply against `referenceAnswer`. `tags` are optional labels.
- Each fixture under `responses` answers a call to its `tool` whose arguments include everything in `arguments`, and `absent` names arguments the call must not set. Any other Vantage call fails the case, and so does a create, update or delete tool running more often than the case has fixtures for it. An argument written `$monthStart-N` matches the first day of the month N months before the day the case runs, which is how a template's cases pin Step 3's search start.
- Name tools as `vantage-tools` lists them. `requiredTools` are the tools the agent must call. The harness also checks that the agent loaded the skill, and answers `get-myself` itself.

A template's cases are generated, so nobody writes or commits them: the build turns each `dashboard-templates` template into three cases in `evals.json`, a plain ask that stops at the confirm, an account with no matching costs, and the build after a yes. The check validates them like any other case. The agent never loads `evals/`, since a bundle carries only `SKILL.md` and `references/`.

Evals call a model, so they cost money and don't run in this repository's CI. Vantage engineers run them from the FinOps Agent's repository, pointing it at a checkout of this one to test a branch before it merges. The harness runs `--build` in that checkout first, so it tests the catalog the branch would publish:

```bash
FINOPS_AS_CODE_DIR=~/src/finops-as-code pnpm eval -- --category skills --model claude-opus-5-5
```

## From a merge to the FinOps Agent

The build takes a minute or two after a merge. GitHub then serves the `catalog` branch with up to 5 minutes of caching, and the agent refreshes its copy of `index.json` every 10 minutes, waiting for a fresh one once its copy is 30 minutes old. A change usually reaches it within about 15 minutes of the build, and at most about 35.

A broken change doesn't take the agent down. If the build fails, `catalog` stays on the last good build and the failure shows on the merge commit. If GitHub fails or `index.json` doesn't parse, the agent keeps its last good copy. If one entry is invalid, the agent drops that skill and keeps the rest, and if a skill's bundle won't load, that skill says so in the chat while the others keep working.

Every change here reaches FinOps Agent sessions without a release, so each one needs an approving review before it merges.
