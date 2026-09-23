import { badge, button, element, header, identifier, introduction, link, restoreView, snapshotView, steps, table } from "./components.js";
import { identification } from "./identification.js";

export async function init(ctx, initial) {
  await ctx.importCSS("main.css");
  let state = initial;
  let selection = new Set();
  let priorPhase = null;
  const identityDrafts = new Map();

  function accountPicker(root) {
    const destinationLabel = element("label", "Vantage workspace", "field");
    const destination = element("select");
    state.workspaces.forEach(workspace => {
      const option = element("option", `${workspace.name} (${workspace.token})`);
      option.value = workspace.token;
      destination.append(option);
    });
    destinationLabel.append(destination);
    const parent = element("p", "Twilio parent: ", "metadata");
    parent.append(identifier(state.parent_sid));
    root.append(destinationLabel, parent);
    if (state.integrations.length) {
      root.append(button("Review existing connections", () => ctx.pushEvent("review_identities", {})));
    }

    const filter = element("input");
    filter.type = "search";
    filter.placeholder = "Search accounts by name or SID";
    filter.setAttribute("aria-label", "Search accounts by name or SID");
    const summary = element("p", undefined, "selection-summary");
    summary.setAttribute("role", "status");
    const rows = element("div");
    const preview = button("Review selected accounts", () => ctx.pushEvent("preview", {
      selected: [...selection], workspace: destination.value,
    }), { primary: true });
    const updateCount = () => {
      summary.textContent = `${selection.size} of ${state.accounts.length} accounts selected`;
      preview.disabled = selection.size === 0;
    };
    const drawRows = () => {
      const query = filter.value.toLocaleLowerCase();
      const accounts = state.accounts.filter(account => `${account.name} ${account.sid}`.toLocaleLowerCase().includes(query));
      const data = accounts.map(account => {
        const checkbox = element("input");
        checkbox.type = "checkbox";
        checkbox.checked = selection.has(account.sid);
        checkbox.disabled = !account.eligible;
        checkbox.setAttribute("aria-label", `Select ${account.name} (${account.sid})`);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) selection.add(account.sid);
          else selection.delete(account.sid);
          updateCount();
        });
        return [checkbox, element("span", account.name, "account-name"), identifier(account.sid),
          badge(account.status, account.status === "active" ? "success" : "neutral"),
          badge(account.existing ? "Connected" : "Not connected", account.existing ? "success" : "neutral")];
      });
      rows.replaceChildren(table(["Select", "Account", "Account SID", "Twilio status", "Vantage"], data, "Twilio subaccounts"));
      updateCount();
    };
    const selectAll = button("Select all eligible", () => {
      selection = new Set(state.accounts.filter(account => account.eligible).map(account => account.sid));
      drawRows();
    });
    const clear = button("Clear selection", () => { selection.clear(); drawRows(); });
    filter.addEventListener("input", drawRows);
    const toolbar = element("div", undefined, "toolbar");
    toolbar.append(filter, selectAll, clear);
    const actions = element("div", undefined, "actions");
    actions.append(element("p", "Existing connections keep their workspace access.", "muted"), preview);
    root.append(toolbar, summary, rows, actions);
    drawRows();
  }

  function review(root) {
    const count = state.entries.filter(entry => entry.action === "connect").length;
    const destination = element("div", undefined, "destination");
    destination.append(element("span", "Destination workspace", "muted"));
    destination.append(element("strong", state.workspace.name), identifier(state.workspace.token));
    root.append(destination, element("h3", `${count} new connections to review`));
    root.append(table(["Account", "Account SID", "Action"], state.entries.map(entry => [
      element("span", entry.name, "account-name"), identifier(entry.sid),
      badge(entry.action === "skip" ? "Skip existing connection" : "Create key and connection", entry.action === "skip" ? "neutral" : "accent"),
    ]), "Proposed connections"));
    const label = element("label", undefined, "confirmation");
    const confirm = element("input");
    confirm.type = "checkbox";
    label.append(confirm, element("span", "I reviewed this destination and selection. Subaccount costs exclude parent-only usage. A parent integration would overlap. Each new Standard key has broad permissions within its subaccount."));
    const apply = button(`Connect ${count} new accounts / reconcile selected`, () => {
      apply.disabled = true;
      ctx.pushEvent("apply", { review_id: state.review_id, confirmed: confirm.checked });
    }, { primary: true, disabled: true });
    confirm.addEventListener("change", () => { apply.disabled = !confirm.checked; });
    const actions = element("div", undefined, "actions");
    actions.append(link("Key permissions ↗", "https://www.twilio.com/docs/iam/api-keys/key-resource-v1"), apply);
    root.append(label, actions);
  }

  function results(root) {
    root.append(element("h3", "Connection results"));
    root.append(table(["Account SID", "Outcome", "Integration", "Next step"], state.results.map(result => [
      identifier(result.sid), badge(result.status, result.status === "Connected; importing costs" || result.status === "Already connected" ? "success" : "warning"),
      identifier(result.integration_token ?? ""), result.message,
    ]), "Connection results"));
    root.append(element("p", "Connected means onboarding has started. Check Vantage for import status and workspace access. Existing connections were not reassigned.", "muted"));
    const links = element("div", undefined, "resource-links");
    links.append(link("Open Twilio integrations ↗", "https://console.vantage.sh/settings/twilio"));
    links.append(link("Import and workspace guidance ↗", "https://docs.vantage.sh/connecting_twilio/"));
    root.append(links);
  }

  function ready(root) {
    root.append(element("h3", "Start with your credentials"));
    root.append(element("p", "Open Secrets using the lock icon in Livebook’s left sidebar, then choose New secret. Add each name below without the LB_ prefix, enter its value, select only this session, and click Add.", "muted"));
    const secrets = element("div", undefined, "secret-names");
    ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "VANTAGE_API_TOKEN"].forEach(name => secrets.append(identifier(name)));
    root.append(secrets);
    root.append(element("p", "New session secrets are available immediately. If you use an existing workspace secret, enable its switch to grant this notebook access. Then click Validate credentials. No password manager or terminal is required.", "muted"));
    const note = element("div", undefined, "information");
    note.append(element("strong", "Review before connecting"));
    note.append(element("p", "Validation only reads accounts. Keys and Vantage connections are created after you select accounts, review the destination, and confirm."));
    root.append(note);
  }

  function render(next) {
    const changedPhase = priorPhase !== null && priorPhase !== next.phase;
    const previous = changedPhase ? null : snapshotView(ctx.root);
    state = next;
    if (["ready", "discovering"].includes(state.phase)) identityDrafts.clear();
    if (state.phase === "selection" && priorPhase !== "selection") {
      selection = new Set(state.accounts.filter(account => account.eligible && !account.existing).map(account => account.sid));
    }
    priorPhase = state.phase;
    const root = element("section", undefined, "onboarding");
    root.setAttribute("aria-label", "Twilio onboarding");
    root.append(header());
    const content = element("div", undefined, "content");
    content.append(introduction(), steps(state.phase));
    const busy = ["discovering", "identifying", "connecting"].includes(state.phase);
    if (busy) {
      const messages = {
        discovering: "Checking access and loading accounts…",
        identifying: "Checking this Account SID with Twilio. No changes are being made…",
        connecting: "Connecting accounts. Progress is saved locally before each change…",
      };
      const progress = element("p", messages[state.phase], "progress");
      progress.setAttribute("role", "status");
      content.append(progress);
    }
    if (state.message) {
      const message = element("div", undefined, "attention");
      message.setAttribute("role", "alert");
      message.append(element("strong", "Needs your attention"), element("p", state.message));
      message.append(link("Credential and permission help ↗", "https://docs.vantage.sh/connecting_twilio/"));
      content.append(message);
    }
    if (state.phase === "ready") ready(content);
    if (["identification", "identifying"].includes(state.phase)) {
      identification(content, state, (event, payload) => ctx.pushEvent(event, payload), identityDrafts, busy);
    }
    if (state.phase === "selection") accountPicker(content);
    if (state.phase === "review") review(content);
    if (state.results.length) results(content);
    if (!busy) {
      const actions = element("div", undefined, "session-actions");
      actions.append(button(state.phase === "ready" ? "Validate credentials" : "Refresh accounts", () => ctx.pushEvent("discover", {}), { primary: state.phase === "ready" }));
      actions.append(button("Clear view", () => ctx.pushEvent("clear", {})));
      content.append(actions);
    }
    const footer = element("footer", undefined, "footer");
    footer.append(element("p", "Credentials are sent only to Twilio and Vantage. Close the session and remove its secrets after use."));
    const docs = element("div", undefined, "resource-links");
    docs.append(link("Twilio documentation ↗", "https://www.twilio.com/docs/iam/api-keys/key-resource-v1"), link("Vantage documentation ↗", "https://docs.vantage.sh/connecting_twilio/"));
    footer.append(docs);
    root.append(content, footer);
    ctx.root.replaceChildren(root);
    if (changedPhase) root.querySelector("h2").focus({ preventScroll: true });
    else restoreView(root, previous);
  }

  ctx.handleEvent("state", render);
  render(initial);
}
