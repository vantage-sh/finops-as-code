import { badge, button, element, identifier, link } from "./components.js";

export function identification(root, state, pushEvent, drafts, busy) {
  root.append(element("h3", "Identify existing Vantage connections"));
  root.append(element("p", "Open each connection in Vantage, find Account Details, and copy its Account SID below. Names and suggested SIDs are hints; they do not establish which account Vantage uses.", "muted"));
  root.append(element("p", "Twilio checks the account and its parent. Your confirmation links that SID to this exact Vantage connection. Confirmations last for this session; refreshing accounts clears them.", "muted"));
  const list = element("div", undefined, "identity-list");
  const known = state.integrations.every(integration => integration.account_sid !== null);
  const continueButton = button("Continue to account selection", () => pushEvent("continue_selection", {}), { primary: true });
  const updateContinue = () => {
    const edited = state.integrations.some(integration => drafts.get(integration.token)?.sid !== integration.account_sid);
    continueButton.disabled = busy || !known || state.identity_blocker || edited;
  };

  state.integrations.forEach(integration => {
    if (!drafts.has(integration.token)) {
      drafts.set(integration.token, { sid: integration.account_sid ?? integration.identity_hint ?? "", confirmed: false });
    }
    const draft = drafts.get(integration.token);
    const card = element("section", undefined, "identity-card");
    card.setAttribute("aria-label", `Identify ${integration.token}`);
    const heading = element("div", undefined, "identity-heading");
    heading.append(element("strong", integration.label ?? "Twilio connection"), badge(integration.status));
    const address = `https://console.vantage.sh/settings/twilio/${encodeURIComponent(integration.token)}`;
    card.append(heading, identifier(integration.token), link("Open Account Details ↗", address));

    if (integration.account_sid) {
      const evidence = element("p", undefined, "identity-evidence");
      evidence.append(badge(integration.source, "success"), element("span", integration.relationship));
      card.append(evidence);
    } else if (integration.identity_hint) {
      card.append(element("p", "Suggested SID from the connection label. Confirm it against Account Details before continuing.", "identity-hint"));
    }

    const field = element("label", "Account SID from Vantage", "field");
    const input = element("input");
    input.type = "text";
    input.value = draft.sid;
    input.maxLength = 34;
    input.autocomplete = "off";
    input.spellcheck = false;
    input.disabled = busy;
    input.placeholder = "AC followed by 32 hexadecimal characters";
    input.dataset.focusKey = `identity:${integration.token}`;
    input.setAttribute("aria-label", `Account SID for ${integration.token}`);
    field.append(input);
    const label = element("label", undefined, "identity-confirmation");
    const confirm = element("input");
    confirm.type = "checkbox";
    confirm.checked = draft.confirmed;
    confirm.disabled = busy;
    label.append(confirm, element("span", "I copied this SID from this exact connection’s Account Details in Vantage."));
    const submit = button(integration.account_sid ? "Confirm corrected SID" : "Confirm Account SID", () => {
      submit.disabled = true;
      const confirmed = draft.confirmed;
      draft.confirmed = false;
      pushEvent("confirm_identity", {
        identification_id: state.identification_id, token: integration.token, sid: draft.sid, confirmed,
      });
    }, { disabled: true });
    const update = () => {
      submit.disabled = busy || !draft.confirmed || !/^AC[0-9a-fA-F]{32}$/.test(draft.sid);
      updateContinue();
    };
    input.addEventListener("input", () => {
      draft.sid = input.value;
      draft.confirmed = false;
      confirm.checked = false;
      update();
    });
    confirm.addEventListener("change", () => { draft.confirmed = confirm.checked; update(); });
    card.append(field, label, submit);
    list.append(card);
    update();
  });

  root.append(list);
  const actions = element("div", undefined, "actions");
  actions.append(element("p", "Every connection needs a verified SID before selection. An inaccessible account remains unresolved.", "muted"), continueButton);
  root.append(actions);
  updateContinue();
}
