---
name: dashboard-templates
description: Builds a ready-made dashboard in the user's Vantage account from one of its templates, such as the AI spend overview (AI spend this month, a three-month trend by provider, and this month by model). Shows a preview and asks before creating anything. Use when a user asks to set up, create or install a ready-made dashboard, such as an AI spend or AI costs dashboard, or asks which dashboards can be set up for them.
compatibility: Needs the Vantage MCP server's workspace, cost, folder, cost report and dashboard tools.
metadata:
  vantage-tools: list-workspaces, query-costs, list-dashboards, create-folder, create-cost-report, create-dashboard, get-dashboard, delete-dashboard, delete-cost-report, delete-folder
---

# Skill: Build a dashboard from a template

Each template below describes one dashboard exactly. Build exactly what the template says: same titles, filters, groupings, periods, widgets, order and grid, with a scope's filter as the user confirms it. Don't add, drop, rename or restyle anything. If a step fails, go to Step 7 instead of trying something else.

For `list-workspaces`, `list-dashboards` and every `query-costs`, start at page 1. While `pagination.hasNextPage` is true, repeat the call with `page` set to `pagination.nextPage` and all other arguments unchanged. Combine every page's records before choosing a workspace, deciding which providers and services count, showing the top costs, or checking for an existing dashboard. A cost query's `total_cost` covers the whole query, so use it once rather than adding it across pages.

## Templates

| Template | What it builds |
|---|---|
| [AI spend overview](references/ai-spend-overview.yaml) | AI spend this month, a three-month trend by provider, and this month by model |

## Step 1: Pick the template

Pick the template that matches the ask, and read its file. If none matches, list the templates and stop. If more than one could, ask which.

## Step 2: Pick the workspace

Call `list-workspaces`. If there's more than one, ask which to use. Pass its token as `workspace_token` on every tool below that accepts it.

## Step 3: Find the costs and show a preview

If the preview has a `filter`, call `query-costs` with it as written, `groupings` from `preview.groupings`, `date_bin` set to `month`, `start_date` the first day of the month four months ago and `end_date` today. No costs: tell the user `preview.if_empty` and stop. Create nothing.

If it has a `scope`, write its filter from what the account has:

1. Call `query-costs` with `filter` set to the scope's VQL, `groupings` set to `[provider, service]`, `date_bin` set to `month`, `start_date` the first day of the month four months ago (on November 14, July 1) and `end_date` today, so the search covers every report's period. Each row is spend Vantage tags as part of the scope.
2. Call `query-costs` with `filter` set to `costs.provider = '*'`, `groupings` set to `[provider]`, and the same `date_bin` and dates, for every provider with costs.
3. Every provider from the first call counts. Count it whole when all it sells is in the scope, like an AI model API or an AI coding tool, even when the second call shows more spend for it than the first. For a cloud or a platform that also sells other things, count only the services the first call found for it.
4. A provider only the second call found doesn't count. Note any whose name says it belongs, like an AI company Vantage doesn't tag, to ask about in Step 5.
5. Write the filter with one `OR` branch per provider that counts: `costs.provider = '<provider>'` for a whole one, and `(costs.provider = '<provider>' AND costs.service IN ('<service>', ...))` for one counted by service. Copy names exactly as the calls returned them, and double any `'` inside a name.
6. If nothing counts, ask about the providers you noted. If there are none, or the user adds none, tell the user `preview.if_empty` and stop. Create nothing.

Then call `query-costs` with the filter, `groupings` from `preview.groupings`, `date_bin` set to `month`, `start_date` the first day of this month and `end_date` today. Show this month's total and the top five rows with their amounts. If this month has no costs yet, say the dashboard fills in as they arrive.

## Step 4: Check for an existing copy

Call `list-dashboards`. If this workspace already has a dashboard with the template's dashboard title, share its link and ask before building another.

## Step 5: Confirm

For a scope, list the providers that count, with the services for each one counted by service, and ask whether to add any you noted in Step 3. Say what you'll create: one folder, one cost report per entry under `cost_reports`, and one dashboard with one widget per entry under `dashboard.widgets`. Create nothing until the user says yes. A plain yes builds with the providers that count, without the ones you noted. If the user adds or removes providers, write the filter again, rerun this month's preview, and ask again. Only add a provider the second call in Step 3 found.

## Step 6: Build

1. `create-folder` with `type: CostFolder` and the template's folder title.
2. `create-cost-report` for each entry under `cost_reports`, with `folder_token` set to the new folder, `filter` set to the entry's filter, or the confirmed one for a `scope`, and every other field exactly as written. Keep each returned token by its key.
3. `create-dashboard` with the template's dashboard title and its widgets in order. For each widget, set `widgetable_token` to the token of the report named in `report`, and copy `title` and `settings` as written. Don't set `date_interval`, `start_date`, `end_date` or `date_bin` on the dashboard, because a dashboard range overrides every widget's own period.
4. Call `get-dashboard` and check every widget in the template is there.

## Step 7: If anything fails

Delete only what this run created, using the tokens you kept, newest first: the dashboard (`delete-dashboard`), each report (`delete-cost-report`), then the folder (`delete-folder`). Never delete anything this run didn't create. Tell the user in one sentence what failed, and stop.

## Step 8: Finish

Share `https://console.vantage.sh/go/<dashboard token>` and name the widgets in one line.

## Scopes

The preview and each cost report have a filter: either `filter`, which is VQL to pass as written, or `scope`, which names a search below. When the preview has a `scope`, every report has the same one. Step 3 runs the search and writes a filter from what it finds, the user confirms it in Step 5, and the preview and every report use it.

In a search, `costs.provider = '*'` matches every provider. `ai_spend` finds the costs Vantage tags with the AI model that ran them.

```yaml
ai_spend: costs.provider = '*' AND tags.name = 'vntg:ai:model'
```

## Template format

Each template is one YAML file in `references/`:

- `id` matches the file name, and `title` and `description` match its row in Templates.
- `preview` holds the data check: a `scope` or `filter`, the `groupings` to show, and `if_empty`, the message for an account with no matching costs.
- `folder.title` names the folder the reports go in.
- `cost_reports` maps a key to one cost report. Every field goes to `create-cost-report` as written, except `scope`, which goes as its confirmed filter. Every report covers `last_3_months` at most, the longest period Step 3 looks back over, and when the preview has a `scope`, every report has the same one.
- `dashboard` has the dashboard's `title` and its `widgets` in order. Each widget's `report` names a key under `cost_reports`, and its `title` and `settings` go to `create-dashboard` as written.
