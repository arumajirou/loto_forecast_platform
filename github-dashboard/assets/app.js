"use strict";

const STATUS_CLASSES = {
  UNASSESSED: "status-unassessed",
  RUNTIME_CERTIFIED: "status-certified",
  RUNTIME_FAILED: "status-failed",
  BLOCKED: "status-blocked",
  UNSUPPORTED: "status-unsupported",
  NON_ROUTABLE: "status-non-routable",
};

function text(node, value) {
  node.textContent = String(value);
  return node;
}

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (value !== undefined) {
    text(node, value);
  }
  return node;
}

function card(label, value, detail) {
  const node = element("div", "card");
  node.append(element("span", "card-label", label));
  node.append(element("strong", "card-value", value));
  if (detail) {
    node.append(element("span", "card-detail", detail));
  }
  return node;
}

function renderGates(data) {
  const container = document.getElementById("gate-cards");
  const gates = [
    ["Holdout", data.formal_gates.holdout],
    ["Prospective", data.formal_gates.prospective],
    ["Automatic promotion", data.formal_gates.automatic_promotion],
  ];
  for (const [label, value] of gates) {
    const node = card(label, value);
    node.classList.add("gate-card");
    container.append(node);
  }
}

function renderOverview(data) {
  const container = document.getElementById("overview-cards");
  const identity = data.identity_summary;
  const rows = [
    ["Models", identity.unified_catalog_identities, "canonical unified identities"],
    ["Games", identity.canonical_games.length, identity.canonical_games.join(", ")],
    ["Matrix", identity.model_game_cross_product, "planning cells"],
    ["Open issues", data.open_issue_count],
    ["Open PRs", data.open_pr_count],
    ["Active workflows", data.active_workflow_count],
    ["Main SHA", data.main_sha.slice(0, 12), "live GitHub snapshot"],
  ];
  for (const [label, value, detail] of rows) {
    container.append(card(label, value, detail));
  }
}

function statusClass(status) {
  return STATUS_CLASSES[status] || "status-unknown";
}

function populateFilters(data) {
  const library = document.getElementById("library-filter");
  const libraries = [...new Set(data.models.map((model) => model.library))].sort();
  for (const value of libraries) {
    const option = element("option", "", value);
    option.value = value;
    library.append(option);
  }

  const status = document.getElementById("status-filter");
  const statuses = Object.keys(data.status_counts).sort();
  for (const value of statuses) {
    const option = element("option", "", value);
    option.value = value;
    status.append(option);
  }
}

function buildCellIndex(data) {
  const index = new Map();
  for (const cell of data.cells) {
    index.set(`${cell.model_id}\u0000${cell.game}`, cell);
  }
  return index;
}

function renderMatrix(data, cellIndex) {
  const head = document.getElementById("matrix-head");
  const body = document.getElementById("matrix-body");
  const modelQuery = document.getElementById("model-filter").value.trim().toLowerCase();
  const library = document.getElementById("library-filter").value;
  const status = document.getElementById("status-filter").value;
  const games = data.identity_summary.canonical_games;

  head.replaceChildren();
  body.replaceChildren();

  const headerRow = document.createElement("tr");
  headerRow.append(element("th", "model-column", "Model"));
  headerRow.append(element("th", "library-column", "Library"));
  for (const game of games) {
    headerRow.append(element("th", "", game));
  }
  head.append(headerRow);

  let visible = 0;
  for (const model of data.models) {
    if (modelQuery && !model.model_id.toLowerCase().includes(modelQuery)) {
      continue;
    }
    if (library && model.library !== library) {
      continue;
    }
    const modelCells = games.map((game) =>
      cellIndex.get(`${model.model_id}\u0000${game}`)
    );
    if (status && !modelCells.some((cell) => cell && cell.status === status)) {
      continue;
    }

    const row = document.createElement("tr");
    row.append(element("th", "model-column", model.model_id));
    row.append(element("td", "library-column", model.library));
    for (const cell of modelCells) {
      const td = element("td", "matrix-cell", cell ? cell.status : "MISSING");
      const currentStatus = cell ? cell.status : "MISSING";
      td.classList.add(statusClass(currentStatus));
      if (cell) {
        const evidence = cell.evidence_ref ? ` evidence=${cell.evidence_ref}` : "";
        td.title = `${cell.model_id} / ${cell.game}: ${cell.status}${evidence}`;
      }
      row.append(td);
    }
    body.append(row);
    visible += 1;
  }

  const summary = document.getElementById("status-summary");
  text(summary, `${visible} of ${data.models.length} models shown`);
}

function renderIssues(data) {
  const container = document.getElementById("issues-list");
  if (!data.open_issues.length) {
    container.append(element("p", "muted", "No open issues."));
    return;
  }
  for (const issue of data.open_issues) {
    const row = element("div", "list-row");
    const link = element("a", "list-title", `#${issue.number} ${issue.title}`);
    link.href = issue.html_url;
    link.rel = "noopener";
    row.append(link);
    const labels = Array.isArray(issue.labels) ? issue.labels.join(", ") : "";
    row.append(element("span", "list-meta", labels || "unlabeled"));
    container.append(row);
  }
}

function renderWorkflows(data) {
  const container = document.getElementById("workflows-list");
  for (const workflow of data.active_workflows) {
    const row = element("div", "list-row");
    const link = element("a", "list-title", workflow.name);
    link.href = workflow.html_url;
    link.rel = "noopener";
    row.append(link);
    row.append(element("span", "list-meta", workflow.path));
    container.append(row);
  }
}

async function loadDashboard() {
  const response = await fetch("data/dashboard.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`dashboard.json fetch failed: HTTP ${response.status}`);
  }
  return response.json();
}

async function main() {
  const data = await loadDashboard();
  text(document.getElementById("semantics"), data.dashboard_semantics);

  const repoLink = document.getElementById("repo-link");
  repoLink.href = `https://github.com/${data.repository}`;
  repoLink.rel = "noopener";

  renderGates(data);
  renderOverview(data);
  populateFilters(data);
  renderIssues(data);
  renderWorkflows(data);

  const cellIndex = buildCellIndex(data);
  const rerender = () => renderMatrix(data, cellIndex);
  document.getElementById("model-filter").addEventListener("input", rerender);
  document.getElementById("library-filter").addEventListener("change", rerender);
  document.getElementById("status-filter").addEventListener("change", rerender);
  rerender();
}

main().catch((error) => {
  const message = document.createElement("p");
  message.className = "error";
  text(message, `Dashboard failed to load: ${error.message}`);
  document.body.prepend(message);
});
