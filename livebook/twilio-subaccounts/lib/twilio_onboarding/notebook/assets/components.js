export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

export function button(label, action, { primary = false, disabled = false } = {}) {
  const node = element("button", label, primary ? "button primary" : "button");
  node.dataset.focusKey = `button:${label}`;
  node.type = "button";
  node.disabled = disabled;
  node.addEventListener("click", action);
  return node;
}

export function link(label, href) {
  const node = element("a", label);
  node.href = href;
  node.dataset.focusKey = `link:${href}`;
  node.target = "_blank";
  node.rel = "noopener noreferrer";
  return node;
}

export function identifier(value) {
  return element("code", value, "identifier");
}

export function badge(label, tone = "neutral") {
  return element("span", label, `badge ${tone}`);
}

export function table(headers, rows, caption) {
  const wrapper = element("div", undefined, "table-scroll");
  wrapper.dataset.focusKey = `table:${caption}`;
  wrapper.tabIndex = 0;
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-label", caption);
  const node = element("table");
  node.append(element("caption", caption, "visually-hidden"));
  const heading = element("tr");
  headers.forEach(text => {
    const cell = element("th", text);
    cell.scope = "col";
    heading.append(cell);
  });
  const head = element("thead");
  head.append(heading);
  const body = element("tbody");
  rows.forEach(values => {
    const row = element("tr");
    values.forEach(value => {
      const cell = element("td");
      if (value instanceof Node) cell.append(value);
      else cell.textContent = String(value ?? "");
      row.append(cell);
    });
    body.append(row);
  });
  if (!rows.length) {
    const cell = element("td", "No accounts match this view.", "empty-row");
    cell.colSpan = headers.length;
    const row = element("tr");
    row.append(cell);
    body.append(row);
  }
  node.append(head, body);
  wrapper.append(node);
  return wrapper;
}

function image(file, alt, className) {
  const node = element("img", undefined, className);
  node.src = new URL(file, import.meta.url).href;
  node.alt = alt;
  return node;
}

export function header() {
  const node = element("header", undefined, "brand-header");
  const brand = element("div", undefined, "brand");
  brand.append(image("vantage.svg", "Vantage", "vantage-logo"), element("span", "FinOps as code", "brand-label"));
  node.append(brand, link("Integration guide ↗", "https://docs.vantage.sh/connecting_twilio/"));
  return node;
}

export function introduction() {
  const node = element("div", undefined, "introduction");
  const icon = element("div", undefined, "provider-icon");
  icon.append(image("twilio.svg", "Twilio", "twilio-logo"));
  const text = element("div");
  const heading = element("h2", "Connect Twilio subaccounts");
  heading.tabIndex = -1;
  text.append(heading);
  text.append(element("p", "Bring each subaccount’s costs into your Vantage workspace.", "muted"));
  node.append(icon, text);
  return node;
}

export function snapshotView(root) {
  return {
    focus: root.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null,
    tables: [...root.querySelectorAll(".table-scroll")].map(table => ({
      key: table.dataset.focusKey, top: table.scrollTop, left: table.scrollLeft,
    })),
  };
}

export function restoreView(root, previous) {
  const nodes = [...root.querySelectorAll("[data-focus-key]")];
  nodes.find(node => node.dataset.focusKey === previous.focus)?.focus({ preventScroll: true });
  previous.tables.forEach(position => {
    const table = nodes.find(node => node.dataset.focusKey === position.key);
    if (table) table.scrollTo({ top: position.top, left: position.left });
  });
}

export function steps(phase) {
  const current = { ready: 0, discovering: 0, identification: 1, identifying: 1, selection: 2, review: 3, connecting: 4, finished: 4 }[phase] ?? 0;
  const node = element("ol", undefined, "steps");
  node.setAttribute("aria-label", "Connection steps");
  ["Validate access", "Identify connections", "Select accounts", "Review", "Connect"].forEach((label, index) => {
    const item = element("li", undefined, index === current ? "current" : index < current ? "complete" : "");
    if (index === current) item.setAttribute("aria-current", "step");
    item.append(element("span", String(index + 1), "step-number"), element("span", label));
    node.append(item);
  });
  return node;
}
