const refreshButton = document.getElementById("refresh-button");
const lastUpdated = document.getElementById("last-updated");
const summaryGrid = document.getElementById("summary-grid");
const priorityGrid = document.getElementById("priority-grid");
const effectivenessGrid = document.getElementById("effectiveness-grid");
const protocolGrid = document.getElementById("protocol-grid");
const synthesisGrid = document.getElementById("synthesis-grid");
const improvementsGrid = document.getElementById("improvements-grid");
const routingModeSelect = document.getElementById("routing-mode");
const routingWindowSizeInput = document.getElementById("routing-window-size");
const routingWindowStartInput = document.getElementById("routing-window-start");
const routingWindowSizeLabel = document.getElementById("routing-window-size-label");
const routingWindowStartLabel = document.getElementById("routing-window-start-label");
const routingWindowBadge = document.getElementById("routing-window-badge");
const routingSummary = document.getElementById("routing-summary");
const routingGraph = document.getElementById("routing-graph");
const routingTurns = document.getElementById("routing-turns");
const workspaceTabsContainer = document.getElementById("workspace-tabs");
const teamsGrid = document.getElementById("teams-grid");
const workerGrid = document.getElementById("worker-grid");
const designBacklogGrid = document.getElementById("design-backlog-grid");
const repairGrid = document.getElementById("repair-grid");
const roundsGrid = document.getElementById("rounds-grid");
const hooksGrid = document.getElementById("hooks-grid");
const referenceGrid = document.getElementById("reference-grid");
const findingsGrid = document.getElementById("findings-grid");
const logsList = document.getElementById("logs-list");
const badgeOverview = document.getElementById("badge-overview");
const badgeImprovements = document.getElementById("badge-improvements");
const badgeTeams = document.getElementById("badge-teams");
const badgeRounds = document.getElementById("badge-rounds");
const badgeHooks = document.getElementById("badge-hooks");
const badgeEvidence = document.getElementById("badge-evidence");
const badgeLogs = document.getElementById("badge-logs");

const WORKSPACE_PANEL_KEY = "golfsim-harness-workspace-panel";
const DETAILS_STATE_KEY = "golfsim-harness-details-state";
const MODE_LABELS = {
  combined: "통합",
  roundtable: "라운드테이블",
  dispatch: "디스패치",
};
const ACCEPTED_PARSE_STATUSES = new Set(["ok", "relaxed", "partial"]);

let lastDashboard = null;

const routingState = {
  initialized: false,
  mode: "combined",
  windowSize: 5,
  start: 0,
};

const workspaceState = {
  activePanel: loadStoredPanel(),
};

const detailsState = {
  openMap: loadStoredDetailsState(),
};

const NODE_POSITIONS = {
  orchestrator: [500, 312],
  pm: [500, 88],
  planning: [808, 226],
  design: [698, 538],
  dev: [302, 538],
  gameplay_qa: [192, 226],
};

function loadStoredPanel() {
  try {
    const stored = window.localStorage.getItem(WORKSPACE_PANEL_KEY);
    return stored || "overview";
  } catch (_error) {
    return "overview";
  }
}

function storePanel(panel) {
  try {
    window.localStorage.setItem(WORKSPACE_PANEL_KEY, panel);
  } catch (_error) {
    // ignore
  }
}

function loadStoredDetailsState() {
  try {
    const raw = window.localStorage.getItem(DETAILS_STATE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function storeDetailsState() {
  try {
    window.localStorage.setItem(DETAILS_STATE_KEY, JSON.stringify(detailsState.openMap));
  } catch (_error) {
    // ignore
  }
}

function captureDetailsState(root = document) {
  root.querySelectorAll("details[data-detail-key]").forEach((detail) => {
    detailsState.openMap[detail.dataset.detailKey] = detail.open;
  });
  storeDetailsState();
}

function bindAndRestoreDetailsState(root = document) {
  root.querySelectorAll("details[data-detail-key]").forEach((detail) => {
    const key = detail.dataset.detailKey;
    if (Object.prototype.hasOwnProperty.call(detailsState.openMap, key)) {
      detail.open = Boolean(detailsState.openMap[key]);
    } else {
      detailsState.openMap[key] = detail.open;
    }
    if (detail.dataset.detailBound === "1") return;
    detail.dataset.detailBound = "1";
    detail.addEventListener("toggle", () => {
      detailsState.openMap[key] = detail.open;
      storeDetailsState();
    });
  });
}

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function safe(text) {
  return text == null || text === "" ? "-" : esc(text);
}

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(1)}%`;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function badgeClass(status) {
  if (status === "block" || status === "failed") return "badge badge-block";
  if (status === "warn" || status === "pending") return "badge badge-warn";
  return "badge badge-ok";
}

function toneClass(toneOrFlags) {
  const tone =
    typeof toneOrFlags === "string"
      ? toneOrFlags
      : resolveTone(toneOrFlags || {});
  if (tone === "block") return "card card-block";
  if (tone === "warn") return "card card-warn";
  return "card";
}

function panelBadgeClass(tone) {
  if (tone === "block") return "workspace-tab-badge is-block";
  if (tone === "warn") return "workspace-tab-badge is-warn";
  return "workspace-tab-badge is-ok";
}

function setTabBadge(element, value, tone) {
  element.textContent = String(value);
  element.className = panelBadgeClass(tone);
}

function listHtml(items, emptyText = "항목 없음") {
  if (!items || !items.length) {
    return `<p class="card-copy">${esc(emptyText)}</p>`;
  }
  return `<ul class="detail-list">${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`;
}

function actionableListHtml(items, source, emptyText = "항목 없음") {
  if (!items || !items.length) {
    return `<p class="card-copy">${esc(emptyText)}</p>`;
  }
  return `
    <div class="detail-list">
      ${items
        .map(
          (item, index) => `
            <div class="round-entry">
              <p class="card-copy">${esc(item)}</p>
              <div class="pill-row">
                <button
                  type="button"
                  data-queue-add="1"
                  data-queue-source="${esc(source)}"
                  data-queue-title="${esc(`${source} ${index + 1}`)}"
                  data-queue-reason="${esc(item)}"
                >
                  Queue 추가
                </button>
              </div>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function miniMetric(label, value) {
  return `<p class="card-copy"><strong>${esc(label)}</strong><span>${esc(value)}</span></p>`;
}

function resolveTone({ warning = false, blocked = false, ok = false }) {
  if (blocked) return "block";
  if (warning) return "warn";
  if (ok) return "ok";
  return "warn";
}

function renderSummary(dashboard) {
  const interaction = dashboard.interaction_health || {};
  const latestRound = interaction.latest_round || {};
  const effect = dashboard.effectiveness || {};
  const directRatio = Math.max(0, 100 - Number(latestRound.fallback_ratio || 0));
  const unboundRoles = interaction.unbound_roles || [];
  const blocks = Number(dashboard.summary?.blocks || 0);
  const warnings = Number(dashboard.summary?.warnings || 0);
  const summaryCards = [
    {
      label: "현재 판단",
      value: effect.label || "-",
      note: effect.headline || "판단 기준 없음",
      tone: effect.status === "needs-hardening" ? "warn" : "ok",
      secondary: false,
    },
    {
      label: "주의 신호",
      value: `${warnings} / ${blocks}`,
      note: `warn ${warnings} · block ${blocks}`,
      tone: blocks > 0 ? "block" : warnings > 0 ? "warn" : "ok",
      secondary: false,
    },
    {
      label: "직접 상호작용",
      value: pct(directRatio),
      note: `fallback ${pct(latestRound.fallback_ratio || 0)}`,
      tone: directRatio >= 70 ? "ok" : directRatio >= 40 ? "warn" : "block",
      secondary: false,
    },
    {
      label: "라운드 완주",
      value: pct(interaction.rounds?.completion_rate || 0),
      note: `turn budget ${latestRound.turn_budget_ok ? "OK" : "WARN"}`,
      tone: interaction.rounds?.completion_rate === 100 ? "ok" : "warn",
      secondary: false,
    },
    {
      label: "역할 바인딩",
      value: `${interaction.bound_roles || 0}/${interaction.roles_total || 0}`,
      note: unboundRoles.length ? `미바인딩 ${unboundRoles.join(", ")}` : "전 역할 바인딩",
      tone: unboundRoles.length ? "warn" : "ok",
      secondary: false,
    },
    {
      label: "worker",
      value: dashboard.worker?.state || "missing",
      note: `pending ${dashboard.worker?.pending_rounds ?? 0}`,
      tone: dashboard.worker?.state === "error" ? "block" : dashboard.worker?.state === "running" ? "ok" : "warn",
      secondary: false,
    },
    {
      label: "프롬프트 커버리지",
      value: pct(interaction.relay_prompts?.coverage_rate || 0),
      note: (interaction.relay_prompts?.roles_covered || []).join(", ") || "기록 없음",
      tone: interaction.relay_prompts?.coverage_rate === 100 ? "ok" : "warn",
      secondary: true,
    },
    {
      label: "QA 근거",
      value: latestRound.qa_evidence_present ? "YES" : "NO",
      note: `finding ${latestRound.findings_count ?? 0}`,
      tone: latestRound.qa_evidence_present ? "ok" : "warn",
      secondary: true,
    },
  ];

  summaryGrid.innerHTML = summaryCards
    .map(
      (card) => `
        <article class="summary-card ${card.secondary ? "is-secondary" : "is-primary"} summary-card-${card.tone}">
          <p class="summary-label">${esc(card.label)}</p>
          <p class="summary-value">${esc(card.value)}</p>
          <p class="summary-note">${esc(card.note)}</p>
        </article>
      `
    )
    .join("");
}

function derivePriorityCards(dashboard) {
  const interaction = dashboard.interaction_health || {};
  const effect = dashboard.effectiveness || {};
  const synthesis = dashboard.synthesis || {};
  const latestRound = interaction.latest_round || {};
  const staleRoles = interaction.stale_roles || [];
  const parseRoles = interaction.parse_error_roles || [];
  const blockers = interaction.blocking_roles || [];
  const unboundRoles = interaction.unbound_roles || [];

  const immediateItems = [
    ...((effect.next_focus || []).slice(0, 3)),
    unboundRoles.length ? `미바인딩 역할을 먼저 복구한다: ${unboundRoles.join(", ")}` : null,
  ].filter(Boolean);

  const weakItems = [
    ...((synthesis.weak_points || []).slice(0, 3)),
    staleRoles.length ? `stale role을 다시 sync한다: ${staleRoles.join(", ")}` : null,
    parseRoles.length ? `compact/free-form parse 수용을 보강한다: ${parseRoles.join(", ")}` : null,
    Number(latestRound.fallback_ratio || 0) >= 50 ? `fallback 비중이 ${pct(latestRound.fallback_ratio)}라 직접 상호작용이 약하다.` : null,
  ].filter(Boolean);

  const stableItems = [
    ...((synthesis.working || []).slice(0, 3)),
    ...((effect.strengths || []).slice(0, 2)),
  ].filter(Boolean);

  const nextItems = [
    ...((synthesis.next_actions || []).slice(0, 4)),
    blockers.length ? `blocker 역할을 우선 해소한다: ${blockers.join(", ")}` : null,
  ].filter(Boolean);

  return [
    {
      title: "지금 바로 볼 것",
      tone: immediateItems.length ? "warn" : "ok",
      badge: `${immediateItems.length || 0}`,
      body: listHtml(immediateItems, "당장 처리할 우선 항목 없음"),
    },
    {
      title: "현재 약한 지점",
      tone: weakItems.length ? "block" : "ok",
      badge: `${weakItems.length || 0}`,
      body: listHtml(weakItems, "지금 드러난 약점 없음"),
    },
    {
      title: "안정 신호",
      tone: stableItems.length ? "ok" : "warn",
      badge: `${stableItems.length || 0}`,
      body: listHtml(stableItems, "아직 누적된 안정 신호 없음"),
    },
    {
      title: "운영 문맥",
      tone: "ok",
      badge: dashboard.effectiveness?.label || "-",
      body: `
        <p class="card-copy">${safe(synthesis.overview || "운영 종합 없음")}</p>
        <p class="card-copy">${safe(synthesis.interaction_summary || "상호작용 종합 없음")}</p>
        <details data-detail-key="priority-next-actions">
          <summary>다음 액션</summary>
          ${listHtml(nextItems, "다음 액션 없음")}
        </details>
      `,
    },
  ];
}

function renderPriority(dashboard) {
  const cards = derivePriorityCards(dashboard);
  priorityGrid.innerHTML = cards
    .map(
      (card) => `
        <article class="${toneClass(card.tone)} priority-card">
          <div class="card-header">
            <h3>${esc(card.title)}</h3>
            <span class="${badgeClass(card.tone)}">${esc(card.badge)}</span>
          </div>
          ${card.body}
        </article>
      `
    )
    .join("");
}

function renderEffectiveness(dashboard) {
  const effect = dashboard.effectiveness || {};
  const interaction = dashboard.interaction_health || {};
  const latestRound = interaction.latest_round || {};
  effectivenessGrid.innerHTML = `
    <article class="${toneClass(effect.status === "needs-hardening" ? "warn" : "ok")}">
      <div class="card-header">
        <h3>효과성 판단</h3>
        <span class="${badgeClass(effect.status === "needs-hardening" ? "warn" : "ok")}">${safe(effect.label)}</span>
      </div>
      <p class="card-title">${safe(effect.headline || "판단 기준 없음")}</p>
      <p class="card-copy"><strong>점수:</strong> ${safe(effect.score)}</p>
      ${listHtml(effect.strengths, "강점 없음")}
      <details data-detail-key="effectiveness-risk-focus">
        <summary>리스크와 다음 포커스</summary>
        ${listHtml([...(effect.risks || []), ...(effect.next_focus || [])], "추가 항목 없음")}
      </details>
    </article>
    <article class="${toneClass({
      warning: (interaction.stale_roles || []).length > 0 || (interaction.parse_error_roles || []).length > 0,
      blocked: (interaction.blocking_roles || []).length > 0,
      ok: true,
    })}">
      <div class="card-header">
        <h3>상호작용 건강도</h3>
        <span class="${badgeClass((interaction.healthy_roles || 0) >= 4 ? "ok" : "warn")}">${safe(interaction.healthy_roles)}/${safe(interaction.roles_total)}</span>
      </div>
      <div class="mini-grid">
        ${miniMetric("active roles", interaction.active_roles ?? 0)}
        ${miniMetric("stale roles", (interaction.stale_roles || []).length)}
        ${miniMetric("parse error", (interaction.parse_error_roles || []).length)}
        ${miniMetric("blocker roles", (interaction.blocking_roles || []).length)}
        ${miniMetric("dispatch success", pct(interaction.dispatch?.success_rate || 0))}
        ${miniMetric("round completion", pct(interaction.rounds?.completion_rate || 0))}
      </div>
      ${listHtml(
        [
          `unbound: ${((interaction.unbound_roles || []).join(", ")) || "없음"}`,
          `stale: ${((interaction.stale_roles || []).join(", ")) || "없음"}`,
          `parse_error: ${((interaction.parse_error_roles || []).join(", ")) || "없음"}`,
          `blocker: ${((interaction.blocking_roles || []).join(", ")) || "없음"}`,
        ],
        "경고 없음"
      )}
    </article>
    <article class="${toneClass((latestRound.fallback_ratio || 0) >= 50 ? "warn" : "ok")}">
      <div class="card-header">
        <h3>라운드 프로토콜</h3>
        <span class="${badgeClass((latestRound.role_coverage_rate || 0) === 100 && (latestRound.fallback_ratio || 0) < 50 ? "ok" : "warn")}">${pct(latestRound.role_coverage_rate || 0)}</span>
      </div>
      <div class="mini-grid">
        ${miniMetric("fallback", pct(latestRound.fallback_ratio || 0))}
        ${miniMetric("QA evidence", latestRound.qa_evidence_present ? "YES" : "NO")}
        ${miniMetric("rebuttal", latestRound.rebuttal_steps ?? 0)}
        ${miniMetric("turn budget", latestRound.turn_budget_ok ? "OK" : "WARN")}
        ${miniMetric("findings", latestRound.findings_count ?? 0)}
        ${miniMetric("draft results", latestRound.issue_draft_count ?? 0)}
      </div>
      ${listHtml(
        [
          `roles seen: ${((latestRound.roles_seen || []).join(", ")) || "없음"}`,
          `qa summary: ${latestRound.has_summary ? "YES" : "NO"}`,
          `retrospective: ${latestRound.has_retrospective ? "YES" : "NO"}`,
        ],
        "라운드 프로토콜 기록 없음"
      )}
    </article>
  `;
}

function renderProtocol(dashboard) {
  const efficiency = dashboard.harness_efficiency || {};
  const latestRound = dashboard.interaction_health?.latest_round || {};
  protocolGrid.innerHTML = `
    <article class="${toneClass(
      efficiency.status === "draggy" ? "warn" : efficiency.status === "insufficient_data" ? "warn" : "ok"
    )}">
      <div class="card-header">
        <h3>Harness Efficiency</h3>
        <span class="${badgeClass(efficiency.status === "draggy" ? "warn" : "ok")}">${safe(efficiency.label || "-")}</span>
      </div>
      <p class="card-title">${safe(efficiency.score ?? "-")}</p>
      <div class="mini-grid">
        ${miniMetric("routing", pct(efficiency.components?.routing_efficiency || 0))}
        ${miniMetric("handoff", pct(efficiency.components?.handoff_clarity || 0))}
        ${miniMetric("closure", pct(efficiency.components?.closure_efficiency || 0))}
        ${miniMetric("steering", pct(efficiency.components?.steering_overhead || 0))}
        ${miniMetric("evidence", pct(efficiency.components?.evidence_alignment || 0))}
        ${miniMetric("compact", efficiency.trend?.compact_routes ?? 0)}
        ${miniMetric("interrupt", efficiency.trend?.interrupt_routes ?? 0)}
      </div>
    </article>
    <article class="${toneClass((latestRound.open_questions_count || 0) > 0 ? "warn" : "ok")}">
      <div class="card-header">
        <h3>Open Questions</h3>
        <span class="${badgeClass((latestRound.open_questions_count || 0) > 0 ? "warn" : "ok")}">${safe(latestRound.open_questions_count ?? 0)}</span>
      </div>
      <div class="mini-grid">
        ${miniMetric("resolved", latestRound.resolved_questions_count ?? 0)}
        ${miniMetric("messages", latestRound.messages_count ?? 0)}
        ${miniMetric("steering", latestRound.steering_events_count ?? 0)}
        ${miniMetric("compact", latestRound.compact_messages_count ?? 0)}
        ${miniMetric("interrupt", latestRound.interrupt_messages_count ?? 0)}
        ${miniMetric("budgeted", latestRound.budgeted_messages_count ?? 0)}
      </div>
      <p class="card-copy">미해결 질문, interrupt 패킷, compact packet 비중을 함께 보고 라운드 closure 효율을 본다.</p>
    </article>
    <article class="${toneClass((efficiency.drag_factors || []).length ? "warn" : "ok")}">
      <div class="card-header">
        <h3>Drag Factors</h3>
        <span class="${badgeClass((efficiency.drag_factors || []).length ? "warn" : "ok")}">${safe((efficiency.drag_factors || []).length)}</span>
      </div>
      ${listHtml(efficiency.drag_factors, "현재 대표 drag factor 없음")}
    </article>
  `;
}

function renderSynthesis(dashboard) {
  const synthesis = dashboard.synthesis || {};
  synthesisGrid.innerHTML = `
    <article class="card">
      <div class="card-header">
        <h3>운영 종합</h3>
        <span class="${badgeClass(dashboard.effectiveness?.status === "needs-hardening" ? "warn" : "ok")}">${safe(dashboard.effectiveness?.label || "-")}</span>
      </div>
      <p class="card-copy">${safe(synthesis.overview || "종합 없음")}</p>
      <p class="card-copy">${safe(synthesis.interaction_summary || "상호작용 종합 없음")}</p>
    </article>
    <article class="${toneClass((synthesis.weak_points || []).length ? "warn" : "ok")}">
      <div class="card-header">
        <h3>잘 되는 점 / 약한 점</h3>
        <span class="${badgeClass((synthesis.weak_points || []).length ? "warn" : "ok")}">${safe((synthesis.turns || []).length)}</span>
      </div>
      <details open data-detail-key="synthesis-working">
        <summary>작동하는 부분</summary>
        ${listHtml(synthesis.working, "아직 명시된 강점 없음")}
      </details>
      <details data-detail-key="synthesis-weak-points">
        <summary>보강이 필요한 부분</summary>
        ${listHtml(synthesis.weak_points, "현재 명시된 약점 없음")}
      </details>
    </article>
    <article class="card">
      <div class="card-header">
        <h3>최근 턴 종합</h3>
        <span class="${badgeClass((synthesis.turns || []).length ? "ok" : "warn")}">${safe((synthesis.turns || []).length)}</span>
      </div>
      ${listHtml(synthesis.turns, "최근 라운드 턴 종합 없음")}
      <details data-detail-key="synthesis-next-actions">
        <summary>다음 액션</summary>
        ${listHtml(synthesis.next_actions, "다음 액션 없음")}
      </details>
    </article>
  `;
}

function renderImprovements(dashboard) {
  const synthesis = dashboard.synthesis || {};
  const effect = dashboard.effectiveness || {};
  const efficiency = dashboard.harness_efficiency || {};
  const latestRound = dashboard.interaction_health?.latest_round || {};
  improvementsGrid.innerHTML = `
    <article class="${toneClass((synthesis.weak_points || []).length ? "warn" : "ok")}">
      <div class="card-header">
        <h3>보강이 필요한 부분</h3>
        <span class="${badgeClass((synthesis.weak_points || []).length ? "warn" : "ok")}">${safe((synthesis.weak_points || []).length)}</span>
      </div>
      ${actionableListHtml(synthesis.weak_points || [], "weak-point", "현재 명시된 약점 없음")}
    </article>
    <article class="${toneClass((effect.next_focus || []).length ? "warn" : "ok")}">
      <div class="card-header">
        <h3>다음 액션</h3>
        <span class="${badgeClass((effect.next_focus || []).length ? "warn" : "ok")}">${safe((effect.next_focus || []).length)}</span>
      </div>
      ${actionableListHtml(effect.next_focus || [], "next-focus", "다음 액션 없음")}
    </article>
    <article class="${toneClass((efficiency.drag_factors || []).length ? "warn" : "ok")}">
      <div class="card-header">
        <h3>Drag Factors</h3>
        <span class="${badgeClass((efficiency.drag_factors || []).length ? "warn" : "ok")}">${safe((efficiency.drag_factors || []).length)}</span>
      </div>
      ${actionableListHtml(efficiency.drag_factors || [], "drag-factor", "현재 대표 drag factor 없음")}
      <p class="muted small">fallback ${pct(latestRound.fallback_ratio || 0)} · open questions ${safe(latestRound.open_questions_count ?? 0)}</p>
    </article>
  `;
}

function renderDesignBacklog(dashboard) {
  const backlog = dashboard.design_backlog || {};
  const counts = backlog.counts || {};
  const items = backlog.items || [];
  const abstractGate = backlog.abstract_gate || {};
  const topItems = items.slice(0, 6);

  designBacklogGrid.innerHTML = `
    <article class="${toneClass(items.length ? "ok" : "warn")}">
      <div class="card-header">
        <h3>UI/UX Backlog</h3>
        <span class="${badgeClass(items.length ? "ok" : "warn")}">${safe(counts.total ?? 0)}</span>
      </div>
      <div class="mini-grid">
        ${miniMetric("priority", counts.priority ?? 0)}
        ${miniMetric("candidate", counts.candidate ?? 0)}
        ${miniMetric("follow-up", counts.follow_up ?? 0)}
        ${miniMetric("immediate", counts.immediate ?? 0)}
        ${miniMetric("next", counts.next ?? 0)}
        ${miniMetric("mode", backlog.orchestration?.execution_mode || "not_run")}
      </div>
      <p class="card-copy">repair queue와 분리된 UI/UX 탐색 백로그입니다. planning + design + pm synthesis 15회 기준으로 유지합니다.</p>
      <details data-detail-key="design-backlog-abstract-gate">
        <summary>추상화 탭 게이트</summary>
        <p class="card-copy">candidate ${abstractGate.candidate_allowed ? "허용" : "보류"}</p>
        ${listHtml(
          Object.entries(abstractGate.signals || {}).map(([key, value]) => `${key}: ${value ? "yes" : "no"}`),
          "게이트 기록 없음"
        )}
      </details>
    </article>
    <article class="card">
      <div class="card-header">
        <h3>Anchor Items</h3>
        <span class="${badgeClass(topItems.length ? "ok" : "warn")}">${safe(topItems.length)}</span>
      </div>
      ${
        topItems.length
          ? topItems
              .map(
                (item) => `
                  <details data-detail-key="uiux-item-${esc(item.id)}">
                    <summary>${safe(item.iteration)}. ${safe(item.title)} <span class="muted small">[${safe(item.status)} / ${safe(item.priority)}]</span></summary>
                    <p class="card-copy"><strong>${safe(item.tab_target)}</strong> / ${safe(item.screen_target)}</p>
                    <p class="card-copy">${safe(item.problem)}</p>
                    <p class="card-copy">${safe(item.proposal)}</p>
                    <p class="card-copy"><strong>acceptance:</strong> ${safe(item.acceptance_hint)}</p>
                    ${listHtml(item.reference_basis || [], "reference 없음")}
                    <p class="muted small">owner ${safe(item.owner)} · trigger ${safe(item.trigger_state)}</p>
                  </details>
                `
              )
              .join("")
          : `<p class="card-copy">아직 생성된 UI/UX backlog가 없습니다.</p>`
      }
    </article>
  `;
}

function renderReferenceDigest(dashboard) {
  const summary = dashboard.reference_digest_summary || {};
  const rationale = (dashboard.design_backlog || {}).iteration_rationale || [];

  referenceGrid.innerHTML = `
    <article class="${toneClass(summary.pattern ? "ok" : "warn")}">
      <div class="card-header">
        <h3>Reference Digest</h3>
        <span class="${badgeClass(summary.pattern ? "ok" : "warn")}">${safe(summary.reference_mode || "missing")}</span>
      </div>
      <p class="card-copy"><strong>pattern:</strong> ${safe(summary.pattern || "-")}</p>
      <p class="card-copy"><strong>style:</strong> ${safe(summary.style || "-")}</p>
      <p class="card-copy"><strong>chart:</strong> ${safe(summary.chart || "-")}</p>
      <details data-detail-key="reference-digest-anti-patterns">
        <summary>anti-patterns / checklist</summary>
        ${listHtml(
          [...(summary.anti_patterns || []), ...(summary.checklist || []).map((item) => `check: ${item}`)],
          "digest 항목 없음"
        )}
      </details>
    </article>
    <article class="card">
      <div class="card-header">
        <h3>Iteration Rationale</h3>
        <span class="${badgeClass(rationale.length ? "ok" : "warn")}">${safe(rationale.length)}</span>
      </div>
      ${
        rationale.length
          ? rationale
              .slice(0, 6)
              .map(
                (item) => `
                  <details data-detail-key="uiux-rationale-${esc(item.source_round_id || item.iteration)}">
                    <summary>${safe(item.iteration)}. ${safe(item.topic)} <span class="muted small">[${safe(item.mode)}]</span></summary>
                    <p class="card-copy"><strong>planning:</strong> ${safe(item.planning || "-")}</p>
                    <p class="card-copy"><strong>design:</strong> ${safe(item.design || "-")}</p>
                    ${item.rebuttal ? `<p class="card-copy"><strong>rebuttal:</strong> ${safe(item.rebuttal)}</p>` : ""}
                    <p class="card-copy"><strong>pm:</strong> ${safe(item.pm || "-")}</p>
                    ${item.fallback_reason ? `<p class="muted small">${safe(item.fallback_reason)}</p>` : ""}
                  </details>
                `
              )
              .join("")
          : `<p class="card-copy">iteration rationale 없음</p>`
      }
    </article>
  `;
}

function renderRouting(dashboard) {
  const routing = dashboard.routing_graph || { history: {}, counts: {}, default_mode: "combined", default_window_size: 5 };
  if (!routingState.initialized) {
    routingState.mode = routing.default_mode || "combined";
    routingState.windowSize = routing.default_window_size || 5;
    routingState.initialized = true;
  }

  const history = routing.history?.[routingState.mode] || [];
  const total = history.length;
  const maxSize = Math.max(1, Math.min(20, total || 1));
  routingState.windowSize = clamp(routingState.windowSize, 1, maxSize);
  const maxStart = Math.max(0, total - routingState.windowSize);
  routingState.start = clamp(routingState.start, 0, maxStart);
  const windowItems = history.slice(routingState.start, routingState.start + routingState.windowSize);
  const graph = buildRoutingWindow(windowItems, routingState.mode);

  routingModeSelect.value = routingState.mode;
  routingWindowSizeInput.max = String(maxSize);
  routingWindowSizeInput.value = String(routingState.windowSize);
  routingWindowStartInput.max = String(maxStart);
  routingWindowStartInput.value = String(routingState.start);
  routingWindowSizeLabel.textContent = `윈도우 크기 ${routingState.windowSize}`;
  routingWindowStartLabel.textContent = total
    ? `시작 위치 ${routingState.start + 1} / ${Math.max(total - routingState.windowSize + 1, 1)}`
    : "시작 위치 0";
  routingWindowBadge.textContent = `${windowItems.length}/${total}`;
  routingWindowBadge.className = badgeClass(total ? "ok" : "warn");

  routingSummary.innerHTML = `
    <div class="card-header">
      <h3>라우팅 요약</h3>
      <span class="${badgeClass(graph.summary.warnCount ? "warn" : "ok")}">${esc(MODE_LABELS[routingState.mode] || routingState.mode)}</span>
    </div>
    <div class="mini-grid">
      ${miniMetric("윈도우 turn", windowItems.length)}
      ${miniMetric("고유 route", graph.edges.length)}
      ${miniMetric("dispatch", graph.summary.dispatchCount)}
      ${miniMetric("roundtable", graph.summary.roundCount)}
      ${miniMetric("fallback", graph.summary.fallbackCount)}
      ${miniMetric("active role", graph.summary.mostActiveRole || "-")}
    </div>
    <p class="card-copy">
      ${total ? `현재 윈도우는 ${routingState.start + 1}번째부터 ${routingState.start + windowItems.length}번째 turn까지를 보여줍니다.` : "표시할 라우팅 기록이 없습니다."}
    </p>
  `;
  routingGraph.innerHTML = graph.svg;
  routingTurns.innerHTML = windowItems.length
    ? windowItems
        .map(
          (item, index) => `
            <div class="route-turn">
              <div class="card-header">
                <p class="card-title">turn ${routingState.start + index + 1}</p>
                <span class="${badgeClass(item.status)}">${esc(item.kind === "dispatch" ? "디스패치" : "라운드")}</span>
              </div>
              <p class="card-copy"><strong>${safe(item.source)}</strong> → <strong>${safe(item.target)}</strong></p>
              <p class="card-copy">${safe(item.label)}</p>
              ${
                item.prompt_preview
                  ? `
                    <div class="route-prompt-block">
                      <div class="route-prompt-header">
                        <strong>${safe(item.prompt_label || "prompt")}</strong>
                        ${item.prompt_path ? `<span class="muted small">${safe(item.prompt_path)}</span>` : ""}
                      </div>
                      <pre class="route-prompt-scroll">${safe(item.prompt_preview)}</pre>
                    </div>
                  `
                  : ""
              }
              <div class="route-meta">
                <span>${safe(item.stage || "-")}</span>
                <span>${item.fallback ? "fallback" : "direct"}</span>
                <span>${safe(item.issue_ref || item.dispatch_id || item.round_id || "-")}</span>
              </div>
              <div class="route-meta">
                <span>progress ${safe(item.progress_state || "-")}</span>
                <span>eta ${safe(item.declared_eta_seconds || 0)}s</span>
                <span>${safe(item.timeout_reason || "live")}</span>
              </div>
              ${
                item.last_stream_at || item.adaptive_deadline
                  ? `<p class="muted small">stream ${safe(item.last_stream_at || "-")} · deadline ${safe(item.adaptive_deadline || "-")} · extend ${safe(item.extended_slices ?? 0)}</p>`
                  : ""
              }
            </div>
          `
        )
        .join("")
    : `<p class="card-copy">이 윈도우에 들어온 turn이 없습니다.</p>`;
}

function buildRoutingWindow(windowItems, mode) {
  const nodeActivity = new Map();
  const edgeMap = new Map();
  windowItems.forEach((item, index) => {
    [item.source, item.target].forEach((nodeId) => {
      if (!nodeId || !NODE_POSITIONS[nodeId]) return;
      nodeActivity.set(nodeId, (nodeActivity.get(nodeId) || 0) + 1);
    });
    if (!item.source || !item.target || !NODE_POSITIONS[item.source] || !NODE_POSITIONS[item.target]) return;
    const key = `${item.source}->${item.target}`;
    const current = edgeMap.get(key) || {
      source: item.source,
      target: item.target,
      count: 0,
      kinds: new Set(),
      fallbackCount: 0,
      warnCount: 0,
    };
    current.count += 1;
    current.kinds.add(item.kind);
    current.fallbackCount += item.fallback ? 1 : 0;
    current.warnCount += item.status === "warn" || item.status === "pending" ? 1 : 0;
    edgeMap.set(key, current);
  });

  const edges = Array.from(edgeMap.values()).map((edge, index) => {
    const kind = edge.kinds.size === 1 ? Array.from(edge.kinds)[0] : "mixed";
    return {
      ...edge,
      kind,
      status: edge.warnCount > 0 ? "warn" : "ok",
      curveSeed: index,
    };
  });

  const mostActiveRole = Array.from(nodeActivity.entries())
    .filter(([nodeId]) => nodeId !== "orchestrator")
    .sort((a, b) => b[1] - a[1])[0]?.[0];

  return {
    edges,
    svg: buildRoutingSvg(edges, nodeActivity, mode),
    summary: {
      dispatchCount: windowItems.filter((item) => item.kind === "dispatch").length,
      roundCount: windowItems.filter((item) => item.kind === "roundtable").length,
      fallbackCount: windowItems.filter((item) => item.fallback).length,
      warnCount: windowItems.filter((item) => item.status === "warn" || item.status === "pending").length,
      mostActiveRole,
    },
  };
}

function buildRoutingSvg(edges, nodeActivity, mode) {
  const visibleNodes = new Set(["pm", "planning", "design", "dev", "gameplay_qa"]);
  if (mode !== "roundtable" || nodeActivity.get("orchestrator")) {
    visibleNodes.add("orchestrator");
  }
  const edgeSvg = edges
    .map((edge) => {
      const [sx, sy] = NODE_POSITIONS[edge.source];
      const [tx, ty] = NODE_POSITIONS[edge.target];
      const path = buildEdgePath(edge.source, edge.target, edge.curveSeed);
      const [lx, ly] = buildLabelPoint(sx, sy, tx, ty, edge.curveSeed);
      return `
        <g class="graph-edge graph-edge-${edge.kind} graph-edge-${edge.status}">
          <path d="${path}" marker-end="url(#arrow-${edge.status})"></path>
          <text x="${lx}" y="${ly}" class="graph-edge-label">×${edge.count}</text>
        </g>
      `;
    })
    .join("");
  const nodeSvg = Array.from(visibleNodes)
    .map((nodeId) => {
      const [x, y] = NODE_POSITIONS[nodeId];
      const activity = nodeActivity.get(nodeId) || 0;
      const radius = nodeId === "orchestrator" ? 34 : 28 + Math.min(activity * 1.5, 10);
      return `
        <g class="graph-node ${nodeId === "orchestrator" ? "graph-node-system" : "graph-node-team"}">
          <circle cx="${x}" cy="${y}" r="${radius}"></circle>
          <text x="${x}" y="${y - 5}" class="graph-node-label">${esc(nodeId)}</text>
          <text x="${x}" y="${y + 16}" class="graph-node-meta">${activity}</text>
        </g>
      `;
    })
    .join("");

  return `
    <svg viewBox="0 0 1000 640" class="routing-svg" aria-label="routing network">
      <defs>
        <marker id="arrow-ok" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="#7fd8ff"></path>
        </marker>
        <marker id="arrow-warn" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="#ffb65c"></path>
        </marker>
      </defs>
      ${edgeSvg}
      ${nodeSvg}
    </svg>
  `;
}

function buildEdgePath(source, target, seed) {
  const [sx, sy] = NODE_POSITIONS[source];
  const [tx, ty] = NODE_POSITIONS[target];
  const dx = tx - sx;
  const dy = ty - sy;
  const length = Math.hypot(dx, dy) || 1;
  const nx = -dy / length;
  const ny = dx / length;
  const direction = seed % 2 === 0 ? 1 : -1;
  const curve = Math.min(96, 24 + Math.abs(seed % 4) * 14);
  const cx = (sx + tx) / 2 + nx * curve * direction;
  const cy = (sy + ty) / 2 + ny * curve * direction;
  return `M ${sx} ${sy} Q ${cx} ${cy} ${tx} ${ty}`;
}

function buildLabelPoint(sx, sy, tx, ty, seed) {
  const dx = tx - sx;
  const dy = ty - sy;
  const length = Math.hypot(dx, dy) || 1;
  const nx = -dy / length;
  const ny = dx / length;
  const direction = seed % 2 === 0 ? 1 : -1;
  const curve = Math.min(96, 24 + Math.abs(seed % 4) * 14);
  return [
    (sx + tx) / 2 + nx * curve * direction * 0.55,
    (sy + ty) / 2 + ny * curve * direction * 0.55,
  ];
}

function renderTeams(dashboard) {
  const teams = [...(dashboard.teams || [])].sort((left, right) => {
    const leftPriority = Number(left.stale) + Number(!ACCEPTED_PARSE_STATUSES.has(left.parse_status)) + Number(left.blocker && left.blocker !== "blocker: 없음");
    const rightPriority = Number(right.stale) + Number(!ACCEPTED_PARSE_STATUSES.has(right.parse_status)) + Number(right.blocker && right.blocker !== "blocker: 없음");
    return rightPriority - leftPriority;
  });

  teamsGrid.innerHTML = teams
    .map((team) => {
      const hasBlocker = team.blocker && team.blocker !== "blocker: 없음";
      const warning = team.stale || !ACCEPTED_PARSE_STATUSES.has(team.parse_status) || hasBlocker;
      return `
        <article class="${toneClass({ warning, blocked: hasBlocker, ok: !warning })}">
          <div class="card-header">
            <h3>${safe(team.role)}</h3>
            <span class="${badgeClass(hasBlocker ? "block" : warning ? "warn" : "ok")}">${safe(team.parse_status)}${team.stale ? " / stale" : ""}</span>
          </div>
          <p class="card-title">${safe(team.thread_title || "미바인딩")}</p>
          <div class="pill-row">
            <span class="pill ${team.stale ? "is-warn" : "is-ok"}">${team.stale ? "stale" : "fresh"}</span>
            <span class="pill ${ACCEPTED_PARSE_STATUSES.has(team.parse_status) ? "is-ok" : "is-warn"}">${safe(team.parse_status)}</span>
            <span class="pill ${hasBlocker ? "is-block" : "is-ok"}">${hasBlocker ? "blocker" : "clear"}</span>
          </div>
          <p class="card-copy"><strong>상태:</strong> ${safe(team.last_status)}</p>
          <p class="card-copy"><strong>progress:</strong> ${safe(team.progress_state || "-")}</p>
          <p class="card-copy"><strong>eta:</strong> ${safe(team.declared_eta_seconds || 0)}s</p>
          <p class="card-copy"><strong>blocker:</strong> ${safe(team.blocker || "없음")}</p>
          <p class="card-copy"><strong>다음 요청:</strong> ${safe(team.next_request || "없음")}</p>
          <p class="muted small">${safe(team.updated_at || "업데이트 기록 없음")} · stream ${safe(team.last_stream_at || "-")}</p>
        </article>
      `;
    })
    .join("");
}

function renderWorkerAndRounds(dashboard) {
  const worker = dashboard.worker || {};
  const counts = dashboard.rounds?.counts || {};
  workerGrid.innerHTML = `
    <article class="${toneClass({
      blocked: worker.state === "error",
      warning: worker.state !== "running",
      ok: worker.state === "running",
    })}">
      <div class="card-header">
        <h3>worker 상태</h3>
        <span class="${badgeClass(worker.state === "error" ? "block" : worker.state === "running" ? "ok" : "warn")}">${safe(worker.state || "missing")}</span>
      </div>
      <p class="card-copy"><strong>current round:</strong> ${safe(worker.current_round_id)}</p>
      <p class="card-copy"><strong>current repair:</strong> ${safe(worker.current_repair_id)}</p>
      <p class="card-copy"><strong>repair state:</strong> ${safe(worker.repair_state || "없음")}</p>
      <p class="card-copy"><strong>pending:</strong> ${safe(worker.pending_rounds ?? 0)}</p>
      <p class="card-copy"><strong>pending repairs:</strong> ${safe(worker.pending_repairs ?? 0)}</p>
      <p class="card-copy"><strong>last error:</strong> ${safe(worker.last_error || "없음")}</p>
      <p class="muted small">${safe(worker.updated_at || "-")}</p>
    </article>
    <article class="${toneClass({
      blocked: counts.failed > 0,
      warning: counts.pending > 0,
      ok: counts.failed === 0 && counts.pending === 0,
    })}">
      <div class="card-header">
        <h3>라운드 상태</h3>
        <span class="${badgeClass(counts.failed ? "block" : counts.pending ? "warn" : "ok")}">${counts.running ? "running" : "idle"}</span>
      </div>
      <div class="mini-grid">
        ${miniMetric("pending", counts.pending ?? 0)}
        ${miniMetric("running", counts.running ?? 0)}
        ${miniMetric("completed", counts.completed ?? 0)}
        ${miniMetric("failed", counts.failed ?? 0)}
      </div>
    </article>
  `;

  const buckets = [
    ["pending", dashboard.rounds?.pending || []],
    ["running", dashboard.rounds?.running || []],
    ["completed", dashboard.rounds?.completed || []],
  ];
  roundsGrid.innerHTML = buckets
    .map(([name, items]) => `
      <article class="card round-card">
        <div class="card-header">
          <h3>${esc(name)}</h3>
          <span class="${badgeClass(name === "completed" ? "ok" : name === "running" ? "ok" : "warn")}">${items.length}</span>
        </div>
        ${
          items.length
            ? items
                .slice(0, 4)
                .map(
                  (item) => `
                    <div class="round-entry">
                      <p class="card-title">${safe(item.id)}</p>
                      <p class="card-copy">${safe(item.topic || item.summary || item.pending_reason || "-")}</p>
                      <p class="muted small">${safe(item.updated_at || item.created_at)}</p>
                    </div>
                  `
                )
                .join("")
            : `<p class="card-copy">항목 없음</p>`
        }
      </article>
    `)
    .join("");
}

function repairTone(status) {
  if (status === "failed") return "block";
  if (status === "pending" || status === "approved" || status === "manual_required" || status === "running") return "warn";
  return "ok";
}

function repairActionButtonsHtml(item) {
  if (item.status === "manual_required") {
    return `<p class="muted small">수동 조치 필요</p>`;
  }
  if (item.status === "running") {
    return `<p class="muted small">worker가 실행 중</p>`;
  }
  const buttons = [];
  if (item.auto_executable && item.status !== "approved" && item.status !== "done") {
    buttons.push(`<button type="button" data-repair-action="approve" data-repair-id="${esc(item.id)}">Approve</button>`);
  }
  if (item.status !== "rejected" && item.status !== "done") {
    buttons.push(
      `<button type="button" data-repair-action="reject" data-repair-id="${esc(item.id)}">${
        item.auto_executable ? "Reject" : "Dismiss"
      }</button>`
    );
  }
  return buttons.length ? `<div class="pill-row">${buttons.join("")}</div>` : `<p class="muted small">추가 동작 없음</p>`;
}

function renderRepairQueue(dashboard) {
  const queue = dashboard.repair_queue || {};
  const counts = queue.counts || {};
  const items = queue.items || [];
  repairGrid.innerHTML = `
    <article class="${toneClass((counts.manual_required || 0) + (counts.pending || 0) + (counts.approved || 0) + (counts.running || 0) ? "warn" : "ok")}">
      <div class="card-header">
        <h3>Repair Queue</h3>
        <span class="${badgeClass((counts.failed || 0) > 0 ? "block" : (counts.pending || 0) + (counts.approved || 0) + (counts.manual_required || 0) > 0 ? "warn" : "ok")}">${safe(counts.total ?? 0)}</span>
      </div>
      <div class="mini-grid">
        ${miniMetric("pending", counts.pending ?? 0)}
        ${miniMetric("approved", counts.approved ?? 0)}
        ${miniMetric("running", counts.running ?? 0)}
        ${miniMetric("done", counts.done ?? 0)}
        ${miniMetric("failed", counts.failed ?? 0)}
        ${miniMetric("manual", counts.manual_required ?? 0)}
      </div>
      <p class="card-copy">대시보드에서 승인한 safe repair만 worker가 순차 자동 실행합니다.</p>
    </article>
    <article class="card">
      <div class="card-header">
        <h3>Queue Items</h3>
        <span class="${badgeClass(items.length ? "warn" : "ok")}">${safe(items.length)}</span>
      </div>
      ${
        items.length
          ? items
              .map(
                (item) => `
                  <div class="round-entry">
                    <div class="card-header">
                      <p class="card-title">${safe(item.title)}</p>
                      <span class="${badgeClass(repairTone(item.status))}">${safe(item.status)}</span>
                    </div>
                    <p class="card-copy"><strong>kind:</strong> ${safe(item.kind)}</p>
                    <p class="card-copy"><strong>target:</strong> ${safe(item.target_role || "-")}</p>
                    ${item.source ? `<p class="card-copy"><strong>source:</strong> ${safe(item.source)}</p>` : ""}
                    <p class="card-copy">${safe(item.reason)}</p>
                    ${item.last_note ? `<p class="muted small">${safe(item.last_note)}</p>` : ""}
                    ${repairActionButtonsHtml(item)}
                  </div>
                `
              )
              .join("")
          : `<p class="card-copy">현재 repair queue 항목이 없습니다.</p>`
      }
    </article>
  `;
}

function renderHooks(hooks) {
  const cards = [
    ["intake_guard", hooks.last_intake],
    ["orchestrator_hint", hooks.last_orchestrator_hint],
    ["check_guard", hooks.last_check],
  ];
  hooksGrid.innerHTML = cards
    .map(([name, hook]) => {
      if (!hook) {
        return `
          <article class="card card-warn">
            <div class="card-header">
              <h3>${esc(name)}</h3>
              <span class="${badgeClass("warn")}">missing</span>
            </div>
            <p class="card-copy">아직 실행 기록이 없습니다.</p>
          </article>
        `;
      }
      return `
        <article class="${toneClass({ blocked: hook.status === "block", warning: hook.status === "warn", ok: hook.status === "ok" })}">
          <div class="card-header">
            <h3>${esc(name)}</h3>
            <span class="${badgeClass(hook.status)}">${safe(hook.status)}</span>
          </div>
          <p class="card-title">${safe(hook.summary)}</p>
          <p class="card-copy">${safe(hook.next_action)}</p>
          <details data-detail-key="hook-${esc(name)}-details">
            <summary>세부 내용</summary>
            ${listHtml(hook.details, "세부 항목 없음")}
          </details>
          <p class="muted small">${safe(hook.timestamp)}</p>
        </article>
      `;
    })
    .join("");
}

function renderFindings(dashboard) {
  const findings = dashboard.gameplay_findings || [];
  const drafts = dashboard.issue_draft_results || [];
  const followUps = dashboard.follow_up_items || [];
  const draftItems = [
    ...drafts.map((item) => ({ ...item, itemType: "draft" })),
    ...followUps.map((item) => ({ ...item, itemType: "follow-up" })),
  ];
  findingsGrid.innerHTML = `
    <article class="${toneClass(findings.length ? "ok" : "warn")}">
      <div class="card-header">
        <h3>Gameplay QA finding</h3>
        <span class="${badgeClass(findings.length ? "ok" : "warn")}">${findings.length}</span>
      </div>
      ${findings.length ? listHtml(findings, "최근 완료 라운드 finding 없음") : `<p class="card-copy">최근 완료 라운드 finding 없음</p>`}
    </article>
    <article class="${toneClass({
      blocked: draftItems.some((item) => item.status === "error"),
      warning: !draftItems.length,
      ok: draftItems.length && !draftItems.some((item) => item.status === "error"),
    })}">
      <div class="card-header">
        <h3>backlog / draft issue</h3>
        <span class="${badgeClass(draftItems.some((item) => item.status === "error") ? "block" : draftItems.length ? "ok" : "warn")}">${draftItems.length}</span>
      </div>
      ${
        draftItems.length
          ? draftItems
              .map((item) => {
                const linkHtml = item.url
                  ? `<a href="${esc(item.url)}" target="_blank" rel="noreferrer">열기</a>`
                  : "";
                return `
                  <div class="round-entry">
                    <p class="card-title">${safe(item.title)}</p>
                    <p class="card-copy">${safe(item.status)} ${linkHtml}</p>
                    <p class="card-copy">${safe(item.summary || "")}</p>
                    <p class="muted small">${safe(item.error || item.team_label || item.itemType || "-")}</p>
                  </div>
                `;
              })
              .join("")
          : `<p class="card-copy">draft 결과 없음</p>`
      }
    </article>
  `;
}

function renderLogs(logs) {
  const events = logs.events || [];
  logsList.innerHTML = events.length
    ? events
        .map((event, index) => {
          const details = event.details || [];
          return `
            <article class="log-card">
              <div class="card-header">
                <p class="card-title">${safe(event.summary || event.event_type)}</p>
                <span class="${badgeClass(event.status)}">${safe(event.status || "info")}</span>
              </div>
              <p class="muted small">${safe(event.timestamp)}</p>
              ${details.length ? `<details data-detail-key="log-${esc(event.timestamp || "unknown")}-${index}"><summary>details</summary>${listHtml(details, "세부 항목 없음")}</details>` : ""}
            </article>
          `;
        })
        .join("")
    : `<article class="log-card"><p class="card-copy">표시할 이벤트 로그가 없습니다.</p></article>`;
}

function renderWorkspaceBadges(dashboard, logs) {
  const teams = dashboard.teams || [];
  const designBacklog = dashboard.design_backlog || {};
  const designCounts = designBacklog.counts || {};
  const teamWarnCount = teams.filter(
    (team) => team.stale || !ACCEPTED_PARSE_STATUSES.has(team.parse_status) || (team.blocker && team.blocker !== "blocker: 없음")
  ).length;
  const repairCounts = dashboard.repair_queue?.counts || {};
  const improvementAttention =
    Number((dashboard.synthesis?.weak_points || []).length) +
    Number((dashboard.effectiveness?.next_focus || []).length) +
    Number((dashboard.harness_efficiency?.drag_factors || []).length) +
    Number(designCounts.priority || 0) +
    Number(designCounts.candidate || 0);
  const roundAttention =
    Number(dashboard.rounds?.counts?.pending || 0) +
    Number(dashboard.rounds?.counts?.running || 0) +
    Number(repairCounts.pending || 0) +
    Number(repairCounts.approved || 0) +
    Number(repairCounts.running || 0) +
    Number(repairCounts.manual_required || 0);
  const hookStatuses = [dashboard.hooks?.last_intake, dashboard.hooks?.last_orchestrator_hint, dashboard.hooks?.last_check].filter(Boolean);
  const hookWarnCount = hookStatuses.filter((item) => item.status === "warn" || item.status === "block").length;
  const evidenceCount =
    Number((dashboard.gameplay_findings || []).length) +
    Number((dashboard.issue_draft_results || []).length) +
    Number((dashboard.follow_up_items || []).length) +
    Number((dashboard.reference_digest_summary?.source_count || 0) > 0 ? 1 : 0) +
    Number(((dashboard.design_backlog || {}).iteration_rationale || []).length);
  const overviewCount = Number(dashboard.summary?.blocks || 0) + Number(dashboard.summary?.warnings || 0);
  const logsCount = Number((logs.events || []).length);

  setTabBadge(
    badgeOverview,
    overviewCount,
    dashboard.summary?.blocks ? "block" : dashboard.summary?.warnings ? "warn" : "ok"
  );
  setTabBadge(
    badgeImprovements,
    improvementAttention || Number(repairCounts.total || 0),
    repairCounts.failed ? "block" : improvementAttention || repairCounts.pending || repairCounts.approved || repairCounts.manual_required ? "warn" : "ok"
  );
  setTabBadge(badgeTeams, teamWarnCount, teamWarnCount ? "warn" : "ok");
  setTabBadge(
    badgeRounds,
    roundAttention || Number(dashboard.rounds?.counts?.completed || 0),
    dashboard.rounds?.counts?.failed || repairCounts.failed ? "block" : roundAttention ? "warn" : "ok"
  );
  setTabBadge(
    badgeHooks,
    hookWarnCount,
    hookStatuses.some((item) => item.status === "block") ? "block" : hookWarnCount ? "warn" : "ok"
  );
  setTabBadge(badgeEvidence, evidenceCount, evidenceCount ? "ok" : "warn");
  setTabBadge(badgeLogs, Math.min(logsCount, 99), logsCount ? "ok" : "warn");
}

function setActiveWorkspacePanel(panelName) {
  const nextPanel = workspaceTabsContainer.querySelector(`[data-panel="${panelName}"]`) ? panelName : "overview";
  workspaceState.activePanel = nextPanel;
  storePanel(nextPanel);
  workspaceTabsContainer.querySelectorAll(".workspace-tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.panel === nextPanel);
  });
  document.querySelectorAll(".workspace-panel").forEach((panel) => {
    const active = panel.id === `panel-${nextPanel}`;
    panel.classList.toggle("is-active", active);
    panel.setAttribute("aria-hidden", active ? "false" : "true");
  });
}

async function updateRepairItem(itemId, action) {
  const response = await fetch(`/api/repair-queue/${encodeURIComponent(itemId)}/${action}`, {
    method: "POST",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "repair queue update failed");
  }
  await refresh();
}

async function enqueueImprovement(title, reason, source) {
  const response = await fetch("/api/repair-queue/enqueue", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title, reason, source }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "queue enqueue failed");
  }
  await refresh();
}

async function refresh() {
  captureDetailsState();
  const [dashboardResponse, logsResponse] = await Promise.all([fetch("/api/dashboard"), fetch("/api/logs")]);
  const dashboard = await dashboardResponse.json();
  const logs = await logsResponse.json();
  lastDashboard = dashboard;

  renderSummary(dashboard);
  renderPriority(dashboard);
  renderEffectiveness(dashboard);
  renderProtocol(dashboard);
  renderSynthesis(dashboard);
  renderImprovements(dashboard);
  renderDesignBacklog(dashboard);
  renderRouting(dashboard);
  renderTeams(dashboard);
  renderWorkerAndRounds(dashboard);
  renderRepairQueue(dashboard);
  renderHooks(dashboard.hooks || {});
  renderReferenceDigest(dashboard);
  renderFindings(dashboard);
  renderLogs(logs);
  renderWorkspaceBadges(dashboard, logs);
  bindAndRestoreDetailsState();
  setActiveWorkspacePanel(workspaceState.activePanel || "overview");
  lastUpdated.textContent = `마지막 갱신: ${new Date().toLocaleString("ko-KR")}`;
}

refreshButton.addEventListener("click", () => {
  refresh().catch((error) => {
    console.error(error);
    lastUpdated.textContent = "갱신 실패";
  });
});

workspaceTabsContainer.addEventListener("click", (event) => {
  const target = event.target.closest(".workspace-tab");
  if (!target) return;
  setActiveWorkspacePanel(target.dataset.panel);
});

repairGrid.addEventListener("click", (event) => {
  const button = event.target.closest("[data-repair-action]");
  if (!button) return;
  updateRepairItem(button.dataset.repairId, button.dataset.repairAction).catch((error) => {
    console.error(error);
    lastUpdated.textContent = "repair queue 갱신 실패";
  });
});

improvementsGrid.addEventListener("click", (event) => {
  const button = event.target.closest("[data-queue-add]");
  if (!button) return;
  enqueueImprovement(button.dataset.queueTitle, button.dataset.queueReason, button.dataset.queueSource).catch((error) => {
    console.error(error);
    lastUpdated.textContent = "개선 큐 추가 실패";
  });
});

routingModeSelect.addEventListener("change", () => {
  routingState.mode = routingModeSelect.value;
  const history = lastDashboard?.routing_graph?.history?.[routingState.mode] || [];
  routingState.start = Math.max(0, history.length - routingState.windowSize);
  if (lastDashboard) renderRouting(lastDashboard);
});

routingWindowSizeInput.addEventListener("input", () => {
  routingState.windowSize = Number(routingWindowSizeInput.value);
  const history = lastDashboard?.routing_graph?.history?.[routingState.mode] || [];
  routingState.start = Math.max(0, history.length - routingState.windowSize);
  if (lastDashboard) renderRouting(lastDashboard);
});

routingWindowStartInput.addEventListener("input", () => {
  routingState.start = Number(routingWindowStartInput.value);
  if (lastDashboard) renderRouting(lastDashboard);
});

refresh().catch((error) => {
  console.error(error);
  lastUpdated.textContent = "초기 로드 실패";
});

window.setInterval(() => {
  refresh().catch((error) => {
    console.error(error);
  });
}, 10000);
