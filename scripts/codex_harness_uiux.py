from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.codex_harness_dashboard import build_dashboard_payload
from scripts.codex_harness_worker import MCPStdioClient
from scripts.codex_hooks.uiux_backlog import (
    REFERENCE_REPO_URL,
    UIUX_ITERATION_SPECS,
    build_reference_digest,
    design_backlog_drafts_dir,
    ensure_uiux_dirs,
    load_reference_digest,
    normalize_design_backlog_item,
    reference_digest_path,
    reference_digest_summary,
    reference_snapshot_dir,
    save_design_backlog,
    save_json,
    save_reference_digest,
)

PARENT_ISSUE = "meta-harness-uiux-backlog"
LIVE_ROLES = ("pm", "planning", "design")
HEALTHY_STATUSES = {"completed", "ready", "idle"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clone_reference_snapshot(repo_root: Path, *, refresh: bool) -> Tuple[Path, str]:
    target = reference_snapshot_dir(repo_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if (target / ".git").exists():
        if refresh:
            subprocess.run(
                ["git", "-C", str(target), "pull", "--ff-only"],
                check=False,
                capture_output=True,
                text=True,
            )
        return target, "snapshot"

    clone = subprocess.run(
        ["git", "clone", "--depth", "1", REFERENCE_REPO_URL, str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if clone.returncode == 0:
        return target, "snapshot"
    return target, "fallback_readme"


def _dashboard_state_summary(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    effect = payload.get("effectiveness") or {}
    efficiency = payload.get("harness_efficiency") or {}
    weak_points = (payload.get("synthesis") or {}).get("weak_points") or []
    drag = efficiency.get("drag_factors") or []
    tabs = ["overview", "improvements", "teams", "rounds", "hooks", "evidence", "logs"]
    parts = [
        f"ready={summary.get('ready', 0)}",
        f"warnings={summary.get('warnings', 0)}",
        f"blocks={summary.get('blocks', 0)}",
        f"effect={effect.get('label', '-')}",
        f"drag={', '.join(drag[:2]) or '-'}",
        f"weak={', '.join(weak_points[:2]) or '-'}",
        f"tabs={', '.join(tabs)}",
    ]
    return " | ".join(parts)


def _previous_items_summary(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "- 아직 backlog 없음"
    lines = []
    for item in items[-3:]:
        lines.append(
            f"- {item.get('iteration')}. {item.get('title')} [{item.get('status')}/{item.get('priority')}] -> {item.get('proposal')}"
        )
    return "\n".join(lines)


def _reference_excerpt(digest: Dict[str, Any], keys: List[str]) -> str:
    lines = []
    for key in keys[:3]:
        value = digest.get(key)
        if isinstance(value, list):
            lines.append(f"- {key}: {', '.join(str(item) for item in value[:3])}")
        elif isinstance(value, dict):
            parts = []
            for subkey, subvalue in value.items():
                if isinstance(subvalue, list):
                    parts.append(f"{subkey}={', '.join(str(item) for item in subvalue[:2])}")
                else:
                    parts.append(f"{subkey}={subvalue}")
            lines.append(f"- {key}: {'; '.join(parts[:3])}")
        elif value:
            lines.append(f"- {key}: {value}")
    return "\n".join(lines) or "- reference digest 없음"


def _reference_basis_for_spec(digest: Dict[str, Any], spec: Dict[str, Any]) -> List[str]:
    basis: List[str] = []
    for key in spec.get("reference_keys") or []:
        value = digest.get(key)
        if isinstance(value, list):
            basis.extend(str(item) for item in value[:1])
        elif isinstance(value, dict):
            if value:
                first_key = next(iter(value))
                first_value = value[first_key]
                if isinstance(first_value, list) and first_value:
                    basis.append(str(first_value[0]))
                else:
                    basis.append(f"{first_key}: {first_value}")
        elif value:
            basis.append(str(value))
    return basis[:3] or ["Executive Dashboard", "Dimensional Layering", "Pre-delivery checklist"]


def _extract_raw_text(result: Dict[str, Any]) -> str:
    parsed = result.get("parsed") or {}
    raw = parsed.get("raw")
    if raw:
        return str(raw)
    result_text = parsed.get("result")
    summary = parsed.get("summary")
    status = parsed.get("status")
    parts = [str(value).strip() for value in (status, summary, result_text) if str(value).strip()]
    return "\n".join(parts)


def _extract_json_block(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    candidate = match.group(1) if match else text
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_planning_prompt(
    spec: Dict[str, Any],
    *,
    dashboard_summary: str,
    reference_excerpt: str,
    previous_summary: str,
) -> str:
    return f"""너는 harness dashboard UI/UX 백로그를 만드는 planning 턴이다.

iteration: {spec['iteration']}/15
topic: {spec['topic']}
target layer: {spec['layer']}
target tab/screen: {spec['tab_target']} / {spec['screen_target']}
trigger state: {spec['trigger_state']}

current dashboard:
{dashboard_summary}

reference digest:
{reference_excerpt}

previous items:
{previous_summary}

답변 규칙:
- 장문 금지. 6줄 이내.
- 템플릿 채우기 말고 핵심만 써라.
- 반드시 아래를 모두 담아라: 문제 / 운영자 목표 / 탭 또는 화면 타깃 / 제안 / 피해야 할 안티패턴 1개.
"""


def _build_design_prompt(
    spec: Dict[str, Any],
    *,
    dashboard_summary: str,
    reference_excerpt: str,
    previous_summary: str,
) -> str:
    return f"""너는 harness dashboard UI/UX 백로그를 만드는 design 턴이다.

iteration: {spec['iteration']}/15
topic: {spec['topic']}
target layer: {spec['layer']}
target tab/screen: {spec['tab_target']} / {spec['screen_target']}
trigger state: {spec['trigger_state']}

current dashboard:
{dashboard_summary}

reference digest:
{reference_excerpt}

previous items:
{previous_summary}

답변 규칙:
- 장문 금지. 6줄 이내.
- 시각/상호작용 계약 위주로 답해라.
- 반드시 아래를 모두 담아라: 문제 / 카드 또는 전환 방식 / 상태 표현 / 안티패턴 1개 / acceptance hint 한 줄.
"""


def _build_rebuttal_prompt(
    spec: Dict[str, Any],
    *,
    rebuttal_role: str,
    planning_text: str,
    design_text: str,
) -> str:
    peer_text = design_text if rebuttal_role == "planning" else planning_text
    other_role = "design" if rebuttal_role == "planning" else "planning"
    return f"""너는 {rebuttal_role}이고, 아래 {other_role} 안을 짧게 교정하는 peer rebuttal 턴이다.

iteration: {spec['iteration']}/15
topic: {spec['topic']}

peer note:
{peer_text}

답변 규칙:
- 4줄 이내.
- 유지할 것 1개, 바꿀 것 1개, pm이 잠가야 할 합의 1개만 말해라.
"""


def _build_pm_prompt(
    spec: Dict[str, Any],
    *,
    dashboard_summary: str,
    reference_excerpt: str,
    planning_text: str,
    design_text: str,
    rebuttal_text: str,
) -> str:
    return f"""너는 harness dashboard UI/UX backlog를 확정하는 pm synthesis 턴이다.

iteration: {spec['iteration']}/15
topic: {spec['topic']}
layer default: {spec['layer']}
tab default: {spec['tab_target']}
screen default: {spec['screen_target']}
trigger default: {spec['trigger_state']}

current dashboard:
{dashboard_summary}

reference digest:
{reference_excerpt}

planning note:
{planning_text or '-'}

design note:
{design_text or '-'}

peer rebuttal:
{rebuttal_text or '-'}

반드시 fenced json 하나만 반환해라.

```json
{{
  "primary_backlog_item": {{
    "layer": "{spec['layer']}",
    "title": "{spec['title']}",
    "tab_target": "{spec['tab_target']}",
    "screen_target": "{spec['screen_target']}",
    "trigger_state": "{spec['trigger_state']}",
    "problem": "",
    "proposal": "",
    "reference_basis": ["Executive Dashboard"],
    "anti_patterns": ["안티패턴 1개"],
    "acceptance_hint": "",
    "priority": "{spec['default_priority']}",
    "status": "{spec['default_status']}",
    "owner": "{spec['default_owner']}"
  }},
  "alternative_rejected": {{
    "title": "",
    "reason": ""
  }},
  "abstract_gate": {{
    "unique_info_layer": false,
    "unique_action_purpose": false,
    "low_overview_overlap": false
  }},
  "iteration_note": "이번 판단을 한 문장으로 요약"
}}
```

규칙:
- `problem`, `proposal`, `acceptance_hint`는 비워 두지 마라.
- planning/design 합의가 약하면 `status`를 `follow-up`으로 내려라.
- `priority`는 `immediate`, `next`, `follow-up`만 쓴다.
- `status`는 `candidate`, `priority`, `follow-up`, `rejected`만 쓴다.
"""


def _dispatch_with_override(
    client: MCPStdioClient,
    *,
    role: str,
    task_request: str,
    prompt: str,
) -> Dict[str, Any]:
    return client.call_tool(
        "dispatch_turn",
        {
            "role": role,
            "parent_issue": PARENT_ISSUE,
            "task_request": task_request,
            "prompt_override": prompt,
            "wait_for_completion": True,
        },
    )


def _fallback_backlog_item(spec: Dict[str, Any], digest: Dict[str, Any], note: str) -> Dict[str, Any]:
    return normalize_design_backlog_item(
        {
            "id": f"uiux-{spec['iteration']:02d}",
            "iteration": spec["iteration"],
            "layer": spec["layer"],
            "title": spec["title"],
            "tab_target": spec["tab_target"],
            "screen_target": spec["screen_target"],
            "trigger_state": spec["trigger_state"],
            "problem": spec["default_problem"],
            "proposal": spec["default_proposal"],
            "reference_basis": _reference_basis_for_spec(digest, spec),
            "anti_patterns": spec["default_anti_patterns"],
            "acceptance_hint": spec["default_acceptance_hint"],
            "priority": spec["default_priority"],
            "status": spec["default_status"],
            "owner": spec["default_owner"],
            "source_round_id": f"uiux-iteration-{spec['iteration']:02d}",
            "reference_mode": digest.get("reference_mode", "fallback_readme"),
            "fallback_note": note,
        },
        spec,
    )


def _role_health(repo_root: Path) -> Dict[str, Any]:
    dashboard = build_dashboard_payload(repo_root)
    teams = {entry["role"]: entry for entry in (dashboard.get("teams") or [])}
    result = {
        "ready": True,
        "roles": {},
    }
    for role in LIVE_ROLES:
        entry = teams.get(role) or {}
        healthy = bool(entry.get("thread_id")) and str(entry.get("last_status") or "").strip() in HEALTHY_STATUSES
        result["roles"][role] = {
            "thread_id": entry.get("thread_id", ""),
            "last_status": entry.get("last_status", ""),
            "healthy": healthy,
        }
        result["ready"] = result["ready"] and healthy
    return result


def _normalize_primary_item(
    payload: Dict[str, Any],
    spec: Dict[str, Any],
    digest: Dict[str, Any],
) -> Dict[str, Any]:
    raw_item = dict(payload.get("primary_backlog_item") or {})
    raw_item.setdefault("id", f"uiux-{spec['iteration']:02d}")
    raw_item.setdefault("iteration", spec["iteration"])
    raw_item.setdefault("source_round_id", f"uiux-iteration-{spec['iteration']:02d}")
    raw_item.setdefault("reference_mode", digest.get("reference_mode", "snapshot"))
    if not raw_item.get("reference_basis"):
        raw_item["reference_basis"] = _reference_basis_for_spec(digest, spec)
    return normalize_design_backlog_item(raw_item, spec)


def _apply_abstract_gate(items: List[Dict[str, Any]], rationale: List[Dict[str, Any]]) -> Dict[str, Any]:
    gate_signals = {
        "unique_info_layer": False,
        "unique_action_purpose": False,
        "low_overview_overlap": False,
    }
    for entry in rationale:
        gate = entry.get("abstract_gate") or {}
        for key in gate_signals:
            gate_signals[key] = gate_signals[key] or bool(gate.get(key))

    allowed = all(gate_signals.values())
    if not allowed:
        for item in items:
            if item.get("tab_target") != "abstract":
                continue
            item["status"] = "follow-up"
            item["priority"] = "follow-up"
    return {
        "candidate_allowed": allowed,
        "signals": gate_signals,
    }


def run_uiux_backlog(
    repo_root: Path,
    *,
    refresh_reference: bool = False,
    live_mode: str = "auto",
    iterations: int = 15,
) -> Dict[str, Any]:
    ensure_uiux_dirs(repo_root)
    _clone_reference_snapshot(repo_root, refresh=refresh_reference)
    digest = build_reference_digest(repo_root)
    save_reference_digest(repo_root, digest)
    dashboard = build_dashboard_payload(repo_root)
    dashboard_summary = _dashboard_state_summary(dashboard)
    reference_summary = reference_digest_summary(digest)
    selected_specs = UIUX_ITERATION_SPECS[: max(0, min(iterations, len(UIUX_ITERATION_SPECS)))]
    health = _role_health(repo_root)
    execution_mode = "live_dispatch" if live_mode == "force" else "auto_fallback_unhealthy_sessions"
    use_live = live_mode == "force" or (live_mode == "auto" and health["ready"])
    items: List[Dict[str, Any]] = []
    rationale: List[Dict[str, Any]] = []

    client: MCPStdioClient | None = None
    if use_live:
        client = MCPStdioClient(repo_root)
        client.start()
        execution_mode = "live_dispatch"

    try:
        for spec in selected_specs:
            previous_summary = _previous_items_summary(items)
            ref_excerpt = _reference_excerpt(digest, spec.get("reference_keys") or [])
            record: Dict[str, Any] = {
                "iteration": spec["iteration"],
                "topic": spec["topic"],
                "mode": execution_mode if use_live else "fallback_synthesis",
                "source_round_id": f"uiux-iteration-{spec['iteration']:02d}",
                "planning": "",
                "design": "",
                "rebuttal": "",
                "pm": "",
                "alternative_rejected": {},
                "abstract_gate": {},
            }

            item: Dict[str, Any]
            if client is None:
                item = _fallback_backlog_item(spec, digest, "team sessions unhealthy; reference-backed synthesis used")
            else:
                try:
                    planning_result = _dispatch_with_override(
                        client,
                        role="planning",
                        task_request=spec["topic"],
                        prompt=_build_planning_prompt(
                            spec,
                            dashboard_summary=dashboard_summary,
                            reference_excerpt=ref_excerpt,
                            previous_summary=previous_summary,
                        ),
                    )
                    record["planning"] = _extract_raw_text(planning_result)

                    design_result = _dispatch_with_override(
                        client,
                        role="design",
                        task_request=spec["topic"],
                        prompt=_build_design_prompt(
                            spec,
                            dashboard_summary=dashboard_summary,
                            reference_excerpt=ref_excerpt,
                            previous_summary=previous_summary,
                        ),
                    )
                    record["design"] = _extract_raw_text(design_result)

                    if spec.get("allow_rebuttal"):
                        rebuttal_role = "planning" if spec["iteration"] % 2 == 0 else "design"
                        rebuttal_result = _dispatch_with_override(
                            client,
                            role=rebuttal_role,
                            task_request=f"{spec['topic']} rebuttal",
                            prompt=_build_rebuttal_prompt(
                                spec,
                                rebuttal_role=rebuttal_role,
                                planning_text=record["planning"],
                                design_text=record["design"],
                            ),
                        )
                        record["rebuttal"] = _extract_raw_text(rebuttal_result)

                    pm_result = _dispatch_with_override(
                        client,
                        role="pm",
                        task_request=f"{spec['topic']} synthesis",
                        prompt=_build_pm_prompt(
                            spec,
                            dashboard_summary=dashboard_summary,
                            reference_excerpt=ref_excerpt,
                            planning_text=record["planning"],
                            design_text=record["design"],
                            rebuttal_text=record["rebuttal"],
                        ),
                    )
                    record["pm"] = _extract_raw_text(pm_result)
                    pm_payload = _extract_json_block(record["pm"])
                    if not pm_payload:
                        raise ValueError("pm synthesis json missing")
                    record["alternative_rejected"] = pm_payload.get("alternative_rejected") or {}
                    record["abstract_gate"] = pm_payload.get("abstract_gate") or {}
                    item = _normalize_primary_item(pm_payload, spec, digest)
                except Exception as exc:  # noqa: BLE001
                    record["mode"] = "mixed_fallback"
                    record["fallback_reason"] = str(exc)
                    item = _fallback_backlog_item(spec, digest, str(exc))

            record["item"] = item
            rationale.append(record)
            items.append(item)
            draft_path = design_backlog_drafts_dir(repo_root) / f"uiux-{spec['iteration']:02d}.json"
            save_json(draft_path, record)
    finally:
        if client is not None:
            client.close()

    abstract_gate = _apply_abstract_gate(items, rationale)
    payload = {
        "generated_at": _now(),
        "reference_mode": digest.get("reference_mode", "missing"),
        "reference_digest_summary": reference_summary,
        "orchestration": {
            "iterations_requested": len(selected_specs),
            "iterations_completed": len(items),
            "execution_mode": execution_mode if use_live else "fallback_synthesis",
            "participants": list(LIVE_ROLES),
            "session_health": health,
        },
        "items": items,
        "iteration_rationale": rationale,
        "abstract_gate": abstract_gate,
    }
    save_design_backlog(repo_root, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="golfsim harness UI/UX backlog orchestration")
    parser.add_argument("--refresh-reference", action="store_true")
    parser.add_argument("--iterations", type=int, default=15)
    parser.add_argument(
        "--live-mode",
        choices=("auto", "force", "off"),
        default="auto",
        help="auto는 세션 건강 시 live dispatch, force는 강제 live, off는 reference 기반 synthesis",
    )
    args = parser.parse_args()

    payload = run_uiux_backlog(
        REPO_ROOT,
        refresh_reference=args.refresh_reference,
        live_mode=args.live_mode,
        iterations=args.iterations,
    )
    print(
        json.dumps(
            {
                "generated_at": payload.get("generated_at"),
                "items": len(payload.get("items") or []),
                "execution_mode": (payload.get("orchestration") or {}).get("execution_mode"),
                "reference_mode": payload.get("reference_mode"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
