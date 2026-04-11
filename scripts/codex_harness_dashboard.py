from __future__ import annotations

import argparse
import json
import mimetypes
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

from scripts.codex_hooks.orchestrator_state import (
    ACCEPTED_PARSE_STATUSES,
    ROLES,
    has_blocker,
    load_json,
    normalize_state_map,
    summarize_orchestrator,
)
from scripts.codex_hooks.repair_queue import (
    approve_repair_item,
    build_repair_candidates,
    enqueue_manual_improvement,
    reject_repair_item,
    repair_queue_counts,
    sync_repair_queue,
)
from scripts.codex_hooks.rounds import list_rounds, load_worker_status, summarize_rounds
from scripts.codex_hooks.uiux_backlog import load_design_backlog, load_reference_digest, reference_digest_summary

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = REPO_ROOT / "tools" / "codex-harness-dashboard"
QA_OBSERVATION_ERROR = "window.render_game_to_text is not a function"


def build_dashboard_payload(repo_root: Path) -> Dict[str, Any]:
    hooks = build_hooks_payload(repo_root)
    raw_state = load_json(repo_root / ".codex" / "orchestrator" / "state.json", {})
    orchestrator = summarize_orchestrator(repo_root)
    qa_observation = _build_qa_observation(repo_root, hooks, raw_state)
    orchestrator = _apply_qa_observation_overrides(orchestrator, qa_observation)
    worker = load_worker_status(repo_root)
    rounds = summarize_rounds(repo_root, limit=8)
    design_backlog = load_design_backlog(repo_root)
    digest_summary = design_backlog.get("reference_digest_summary") or reference_digest_summary(load_reference_digest(repo_root))
    teams = [orchestrator["entries"][role] for role in ROLES]
    dispatch_metrics = _summarize_dispatches(repo_root)
    prompt_metrics = _summarize_prompts(repo_root)
    round_metrics = _summarize_round_metrics(repo_root, rounds)
    hook_metrics = _summarize_hook_metrics(repo_root, hooks)
    routing_graph = _build_routing_graph(repo_root)

    warning_count = len(orchestrator["stale_roles"]) + len(orchestrator["parse_error_roles"])
    block_count = len(orchestrator["blocking_roles"]) + rounds["counts"]["failed"]
    if not orchestrator["targets_bound"]:
        warning_count += 1
    if rounds["counts"]["pending"] and worker.get("state") not in {"running", "polling"}:
        warning_count += 1

    for hook in (hooks["last_intake"], hooks["last_orchestrator_hint"], hooks["last_check"]):
        if not hook:
            continue
        if hook.get("status") == "warn":
            warning_count += 1
        if hook.get("status") == "block":
            block_count += 1

    ready_count = sum(
        1
        for team in teams
        if not team["stale"] and team["parse_status"] in ACCEPTED_PARSE_STATUSES and not has_blocker(team["blocker"])
    )
    latest_completed = rounds["latest_completed"] or {}
    interaction_health = _build_interaction_health(
        orchestrator=orchestrator,
        teams=teams,
        dispatch_metrics=dispatch_metrics,
        prompt_metrics=prompt_metrics,
        round_metrics=round_metrics,
        hook_metrics=hook_metrics,
        worker=worker,
        qa_observation=qa_observation,
    )
    repair_queue = _build_repair_queue(repo_root, interaction_health)
    effectiveness = _build_effectiveness_summary(interaction_health)
    harness_efficiency = _build_harness_efficiency(interaction_health, routing_graph)
    synthesis = _build_synthesis(
        orchestrator=orchestrator,
        dispatch_metrics=dispatch_metrics,
        prompt_metrics=prompt_metrics,
        round_metrics=round_metrics,
        hook_metrics=hook_metrics,
        worker=worker,
        effectiveness=effectiveness,
        harness_efficiency=harness_efficiency,
        qa_observation=qa_observation,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "orchestrator": {
            "targets_bound": orchestrator["targets_bound"],
            "stale_roles": orchestrator["stale_roles"],
            "parse_error_roles": orchestrator["parse_error_roles"],
            "blocking_roles": orchestrator["blocking_roles"],
        },
        "teams": teams,
        "hooks": hooks,
        "worker": worker,
        "rounds": rounds,
        "qa_observation": qa_observation,
        "gameplay_findings": latest_completed.get("gameplay_findings", []),
        "issue_draft_results": latest_completed.get("issue_draft_results", []),
        "follow_up_items": [qa_observation["follow_up_item"]] if qa_observation.get("follow_up_item") else [],
        "design_backlog": design_backlog,
        "reference_digest_summary": digest_summary,
        "interaction_health": interaction_health,
        "effectiveness": effectiveness,
        "harness_efficiency": harness_efficiency,
        "repair_queue": repair_queue,
        "synthesis": synthesis,
        "routing_graph": routing_graph,
        "summary": {
            "ready": ready_count,
            "warnings": warning_count,
            "blocks": block_count,
        },
    }


def build_team_payload(repo_root: Path, role: str) -> Dict[str, Any]:
    raw_state = load_json(repo_root / ".codex" / "orchestrator" / "state.json", {})
    hooks = build_hooks_payload(repo_root)
    qa_observation = _build_qa_observation(repo_root, hooks, raw_state)
    state = normalize_state_map(raw_state)
    entry = state.get(role, {})
    normalized = _apply_qa_observation_overrides(summarize_orchestrator(repo_root), qa_observation)["entries"][role]
    return {
        "role": role,
        "entry": normalized,
        "parsed": entry.get("parsed"),
        "raw_final_text": entry.get("raw_final_text", ""),
        "qa_observation": qa_observation,
    }


def build_hooks_payload(repo_root: Path) -> Dict[str, Any]:
    return {
        "last_intake": _read_last_hook(repo_root, "last-intake.json"),
        "last_orchestrator_hint": _read_last_hook(repo_root, "last-orchestrator-hint.json"),
        "last_check": _read_last_hook(repo_root, "last-check.json"),
    }


def build_logs_payload(repo_root: Path, kind: str | None = None) -> Dict[str, Any]:
    if kind in {"intake", "orchestrator", "check"}:
        return {"events": _read_jsonl(repo_root / ".codex" / "harness" / "logs" / f"{kind}.jsonl")}
    if kind == "round":
        return {"events": _read_jsonl(repo_root / ".codex" / "harness" / "logs" / "rounds.jsonl")}

    events = []
    events.extend(_read_dispatch_events(repo_root))
    events.extend(_read_jsonl(repo_root / ".codex" / "harness" / "logs" / "intake.jsonl"))
    events.extend(_read_jsonl(repo_root / ".codex" / "harness" / "logs" / "orchestrator.jsonl"))
    events.extend(_read_jsonl(repo_root / ".codex" / "harness" / "logs" / "check.jsonl"))
    events.extend(_read_jsonl(repo_root / ".codex" / "harness" / "logs" / "rounds.jsonl"))
    events.extend(_synthetic_parse_errors(repo_root))
    events.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return {"events": events[:60]}


def build_health_payload() -> Dict[str, Any]:
    return {"ok": True, "generated_at": datetime.now(timezone.utc).isoformat()}


def build_repair_queue_payload(repo_root: Path) -> Dict[str, Any]:
    payload = build_dashboard_payload(repo_root)
    return payload["repair_queue"]


def _build_repair_queue(repo_root: Path, interaction_health: Dict[str, Any]) -> Dict[str, Any]:
    items = sync_repair_queue(repo_root, build_repair_candidates(interaction_health))
    return {
        "items": items,
        "counts": repair_queue_counts(items),
    }


def _truncate_preview(text: str, limit: int = 220) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _build_qa_observation(repo_root: Path, hooks: Dict[str, Any], raw_state: Any) -> Dict[str, Any]:
    state = normalize_state_map(raw_state)
    last_check = hooks.get("last_check") or {}
    has_last_check = bool(last_check)
    last_check_text = json.dumps(last_check, ensure_ascii=False)
    last_check_time = _parse_iso(last_check.get("timestamp"))
    active_from_check = QA_OBSERVATION_ERROR in last_check_text

    latest_success: Dict[str, Any] | None = None
    latest_failure: Dict[str, Any] | None = None
    historical_failures: List[Dict[str, Any]] = []
    qa_dir = repo_root / ".codex" / "harness" / "qa-evidence"
    for path in sorted(qa_dir.glob("*.json")):
        payload = load_json(path, {})
        timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        snapshot = {
            "path": str(path),
            "timestamp": timestamp.isoformat(),
            "ok": bool(payload.get("ok")),
            "error": str(payload.get("stderr") or ""),
        }
        if snapshot["ok"]:
            if latest_success is None or snapshot["timestamp"] > latest_success["timestamp"]:
                latest_success = snapshot
            continue
        if QA_OBSERVATION_ERROR in snapshot["error"]:
            historical_failures.append(snapshot)
            if latest_failure is None or snapshot["timestamp"] > latest_failure["timestamp"]:
                latest_failure = snapshot

    historical_roles = [
        role
        for role, entry in state.items()
        if QA_OBSERVATION_ERROR in "\n".join(
            str(entry.get(key, "")) for key in ("blocker", "next_request", "raw_final_text")
        )
    ]

    latest_failure_time = _parse_iso(latest_failure["timestamp"]) if latest_failure else None
    latest_success_time = _parse_iso(latest_success["timestamp"]) if latest_success else None
    active_from_evidence = bool(
        latest_failure_time
        and not has_last_check
        and (latest_success_time is None or latest_failure_time >= latest_success_time)
    )
    active_blocker = active_from_check or active_from_evidence
    follow_up_recommended = (bool(historical_failures) or bool(historical_roles)) and not active_blocker
    if active_blocker:
        status = "active_blocker"
        label = "활성 blocker"
        summary = "`render_game_to_text` 계약이 현재 검증선 또는 QA evidence를 직접 막고 있다."
    elif follow_up_recommended:
        status = "follow_up"
        label = "후속 이슈"
        summary = "`render_game_to_text`는 현재 active blocker는 아니지만, 과거 QA 관측 경로를 깨뜨린 이력이 있어 후속 안정화로 추적한다."
    else:
        status = "clear"
        label = "정상"
        summary = "현재 저장된 검증 기록 기준으로 `render_game_to_text` 관련 active/historical 신호가 없다."

    follow_up_item = None
    if follow_up_recommended:
        follow_up_item = {
            "title": "QA 관측 표면 안정화",
            "status": "follow-up",
            "summary": "`render_game_to_text`를 QA/테스트 공용 계약으로 다시 고정하고 재발 시 원인을 별도 표기한다.",
            "details": [
                "`window.render_game_to_text`를 QA/테스트 공용 계약으로 명시",
                "초기화 시점과 export 보장을 한 곳에서 관리",
                "gameplay QA smoke 1건과 UI interaction smoke 1건을 계약 테스트로 유지",
                "실패 시 `qa_observation_broken` 원인으로 분리 표시",
            ],
        }

    return {
        "status": status,
        "label": label,
        "active_blocker": active_blocker,
        "follow_up_recommended": follow_up_recommended,
        "summary": summary,
        "historical_roles": historical_roles,
        "latest_success": latest_success,
        "latest_failure": latest_failure,
        "follow_up_item": follow_up_item,
    }


def _apply_qa_observation_overrides(orchestrator: Dict[str, Any], qa_observation: Dict[str, Any]) -> Dict[str, Any]:
    if qa_observation.get("status") != "follow_up":
        return orchestrator
    entries = {role: dict(entry) for role, entry in orchestrator["entries"].items()}
    historical_roles = set(qa_observation.get("historical_roles") or [])
    for role, entry in entries.items():
        if role not in historical_roles:
            continue
        combined = "\n".join(str(entry.get(key, "")) for key in ("blocker", "next_request"))
        if QA_OBSERVATION_ERROR not in combined and QA_OBSERVATION_ERROR not in str(entry.get("source", "")):
            entry["historical_blocker"] = entry.get("blocker", "")
            entry["blocker"] = ""
            entry["risk_state"] = "review"
            entry["observation_status"] = "historical_follow_up"
            continue
        entry["historical_blocker"] = entry.get("blocker", "")
        entry["blocker"] = ""
        entry["risk_state"] = "review"
        entry["observation_status"] = "historical_follow_up"

    blocking_roles = [
        role for role in orchestrator["blocking_roles"] if entries.get(role, {}).get("risk_state") == "blocked"
    ]
    adjusted = dict(orchestrator)
    adjusted["entries"] = entries
    adjusted["blocking_roles"] = blocking_roles
    return adjusted


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _read_prompt_preview(repo_root: Path, prompt_path: str) -> str:
    raw = str(prompt_path or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / raw
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _read_last_hook(repo_root: Path, filename: str) -> Dict[str, Any] | None:
    path = repo_root / ".codex" / "harness" / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {
            "status": "warn",
            "summary": f"{filename} parse 실패",
            "details": [],
            "next_action": "파일 내용을 확인한다.",
        }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _read_dispatch_items(repo_root: Path) -> List[Dict[str, Any]]:
    return _read_jsonl(repo_root / ".codex" / "orchestrator" / "dispatches.jsonl")


def _read_dispatch_events(repo_root: Path) -> List[Dict[str, Any]]:
    events = []
    for item in _read_dispatch_items(repo_root):
        timestamp = item.get("completed_at") or item.get("created_at") or ""
        prompt_path = item.get("prompt_path", "")
        events.append(
            {
                "timestamp": timestamp,
                "event_type": "dispatch",
                "status": "warn" if item.get("error") else "ok",
                "summary": f"{item.get('role', '?')} {item.get('event', 'event')}",
                "details": [
                    f"thread: {item.get('thread_title', '')}",
                    f"dispatch_id: {item.get('dispatch_id', '')}",
                    *([f"prompt_path: {prompt_path}"] if prompt_path else []),
                ],
            }
        )
    return events


def _summarize_dispatches(repo_root: Path) -> Dict[str, Any]:
    items = _read_dispatch_items(repo_root)
    grouped: Dict[str, Dict[str, Any]] = {}
    for item in items:
        dispatch_id = item.get("dispatch_id")
        if not dispatch_id:
            continue
        group = grouped.setdefault(
            dispatch_id,
            {
                "dispatch_id": dispatch_id,
                "role": item.get("role", ""),
                "thread_title": item.get("thread_title", ""),
                "prompt_path": "",
                "started_at": "",
                "completed_at": "",
                "completed": False,
                "error": "",
            },
        )
        if item.get("event") == "started":
            group["started_at"] = item.get("created_at") or group["started_at"]
            group["prompt_path"] = item.get("prompt_path") or group["prompt_path"]
        if item.get("event") == "completed":
            group["completed_at"] = item.get("completed_at") or group["completed_at"]
            group["completed"] = True
            group["error"] = item.get("error", "") or group["error"]

    dispatches = list(grouped.values())
    total = len(dispatches)
    completed = sum(1 for item in dispatches if item["completed"])
    errors = sum(1 for item in dispatches if item["completed"] and item["error"])
    open_count = sum(1 for item in dispatches if not item["completed"])
    success = max(completed - errors, 0)
    success_rate = round((success / completed) * 100, 1) if completed else 0.0
    completed_roles = sorted({item["role"] for item in dispatches if item["completed"] and item["role"]})
    started_roles = sorted({item["role"] for item in dispatches if item["role"]})
    return {
        "total": total,
        "completed": completed,
        "success": success,
        "errors": errors,
        "open": open_count,
        "success_rate": success_rate,
        "roles_started": started_roles,
        "roles_completed": completed_roles,
        "items": dispatches,
        "open_items": [item for item in dispatches if not item["completed"]],
    }


def _summarize_prompts(repo_root: Path) -> Dict[str, Any]:
    prompt_dir = repo_root / ".codex" / "orchestrator" / "prompts"
    roles = []
    total = 0
    if prompt_dir.exists():
        for path in prompt_dir.glob("*.md"):
            total += 1
            role = _infer_prompt_role(path.stem)
            if role:
                roles.append(role)
    unique_roles = sorted(set(roles))
    coverage_rate = round((len(unique_roles) / len(ROLES)) * 100, 1) if ROLES else 0.0
    return {
        "total": total,
        "roles_covered": unique_roles,
        "coverage_rate": coverage_rate,
    }


def _infer_prompt_role(stem: str) -> str:
    for role in ROLES:
        if stem.endswith(f"-{role}") or stem == role:
            return role
    return ""


def _summarize_round_metrics(repo_root: Path, rounds: Dict[str, Any]) -> Dict[str, Any]:
    counts = rounds["counts"]
    total = counts["pending"] + counts["running"] + counts["completed"] + counts["failed"]
    completion_rate = round((counts["completed"] / total) * 100, 1) if total else 0.0
    latest = rounds.get("latest_completed") or {}
    steps = latest.get("steps", [])
    messages = latest.get("messages", [])
    open_questions = latest.get("open_questions", [])
    resolved_questions = latest.get("resolved_questions", [])
    steering_events = latest.get("steering_events", [])
    compact_messages = [message for message in messages if message.get("codec") in {"compact", "kv", "symbolic"}]
    interrupt_messages = [
        message for message in messages if message.get("interrupt") or message.get("priority") == "interrupt"
    ]
    budgeted_messages = [message for message in messages if int(message.get("token_budget") or 0) > 0]
    role_counter = Counter(step.get("role", "") for step in steps if step.get("role"))
    roles_seen = sorted(role_counter.keys())
    fallback_steps = [
        step
        for step in steps
        if step.get("parse_status") == "fallback" or step.get("thread_id") == "local-fallback"
    ]
    timeout_steps = [step for step in fallback_steps if step.get("fallback_kind") == "timeout_fallback"]
    upstream_timeout_steps = [step for step in fallback_steps if step.get("fallback_kind") == "upstream_timeout"]
    direct_steps = [step for step in steps if step not in fallback_steps]
    rebuttal_steps = [step for step in steps if "rebuttal" in str(step.get("stage", ""))]
    turn_budget_ok = all(count <= 2 for count in role_counter.values())
    qa_evidence_present = bool(
        latest.get("gameplay_findings")
        or (repo_root / ".codex" / "harness" / "qa-evidence" / f"{latest.get('id', '')}.json").exists()
    )
    role_coverage_rate = round((len(roles_seen) / len(ROLES)) * 100, 1) if ROLES else 0.0
    fallback_ratio = round((len(fallback_steps) / len(steps)) * 100, 1) if steps else 0.0
    return {
        "total": total,
        "completion_rate": completion_rate,
        "latest": {
            "id": latest.get("id", ""),
            "status": latest.get("status", ""),
            "summary": latest.get("summary", ""),
            "retrospective": latest.get("retrospective", ""),
            "roles_seen": roles_seen,
            "role_coverage_rate": role_coverage_rate,
            "steps_total": len(steps),
            "fallback_steps": len(fallback_steps),
            "timeout_fallback_steps": len(timeout_steps),
            "upstream_timeout_steps": len(upstream_timeout_steps),
            "direct_steps": len(direct_steps),
            "fallback_ratio": fallback_ratio,
            "rebuttal_steps": len(rebuttal_steps),
            "turn_budget_ok": turn_budget_ok,
            "has_summary": bool(latest.get("summary")),
            "has_retrospective": bool(latest.get("retrospective")),
            "has_findings": bool(latest.get("gameplay_findings")),
            "findings_count": len(latest.get("gameplay_findings", [])),
            "has_backlog": bool(latest.get("backlog_candidates")),
            "backlog_count": len(latest.get("backlog_candidates", [])),
            "draft_count": len(latest.get("issue_draft_results", [])),
            "qa_evidence_present": qa_evidence_present,
            "messages_count": len(messages),
            "compact_messages_count": len(compact_messages),
            "interrupt_messages_count": len(interrupt_messages),
            "budgeted_messages_count": len(budgeted_messages),
            "open_questions_count": len(open_questions),
            "resolved_questions_count": len(resolved_questions),
            "steering_events_count": len(steering_events),
            "turns": _summarize_round_turns(steps),
        },
    }


def _summarize_round_turns(steps: List[Dict[str, Any]], limit: int = 8) -> List[str]:
    items = []
    for step in steps[:limit]:
        stage = str(step.get("stage", "")).replace("_", " ")
        role = step.get("role", "?")
        summary = step.get("result") or step.get("last_status") or step.get("understanding") or ""
        summary = " ".join(str(summary).split())
        if len(summary) > 120:
            summary = summary[:117].rstrip() + "..."
        items.append(f"{role} / {stage}: {summary or '-'}")
    return items


def _summarize_hook_metrics(repo_root: Path, hooks: Dict[str, Any]) -> Dict[str, Any]:
    last_hooks = {
        "intake": hooks.get("last_intake"),
        "orchestrator": hooks.get("last_orchestrator_hint"),
        "check": hooks.get("last_check"),
    }
    warn_count = 0
    block_count = 0
    for hook in last_hooks.values():
        if not hook:
            continue
        if hook.get("status") == "warn":
            warn_count += 1
        if hook.get("status") == "block":
            block_count += 1

    log_counts = {}
    for kind in ("intake", "orchestrator", "check", "rounds"):
        log_counts[kind] = len(_read_jsonl(repo_root / ".codex" / "harness" / "logs" / f"{kind}.jsonl"))
    return {
        "warn_count": warn_count,
        "block_count": block_count,
        "log_counts": log_counts,
    }


def _build_routing_graph(repo_root: Path) -> Dict[str, Any]:
    dispatch_history = _build_dispatch_history(repo_root)
    roundtable_history = _build_roundtable_history(repo_root)
    combined = sorted(dispatch_history + roundtable_history, key=lambda item: item.get("timestamp", ""))
    nodes = [
        {"id": "orchestrator", "label": "orchestrator", "kind": "system"},
        *[
            {"id": role, "label": role, "kind": "team"}
            for role in ROLES
        ],
    ]
    return {
        "nodes": nodes,
        "history": {
            "dispatch": dispatch_history,
            "roundtable": roundtable_history,
            "combined": combined,
        },
        "counts": {
            "dispatch": len(dispatch_history),
            "roundtable": len(roundtable_history),
            "combined": len(combined),
        },
        "default_mode": "combined",
        "default_window_size": 5,
    }


def _build_dispatch_history(repo_root: Path) -> List[Dict[str, Any]]:
    items = _read_dispatch_items(repo_root)
    grouped: Dict[str, Dict[str, Any]] = {}
    for item in items:
        dispatch_id = item.get("dispatch_id")
        if not dispatch_id:
            continue
        group = grouped.setdefault(
            dispatch_id,
            {
                "dispatch_id": dispatch_id,
                "role": item.get("role", ""),
                "thread_title": item.get("thread_title", ""),
                "prompt_path": "",
                "started_at": "",
                "completed_at": "",
                "completed": False,
                "error": "",
            },
        )
        if item.get("event") == "started":
            group["started_at"] = item.get("created_at") or group["started_at"]
            group["prompt_path"] = item.get("prompt_path") or group["prompt_path"]
        if item.get("event") == "completed":
            group["completed_at"] = item.get("completed_at") or group["completed_at"]
            group["completed"] = True
            group["error"] = item.get("error", "") or group["error"]

    dispatches = sorted(grouped.values(), key=lambda item: item.get("started_at") or item.get("completed_at") or "")
    history = []
    for index, item in enumerate(dispatches, start=1):
        if item["completed"] and item["error"]:
            status = "warn"
        elif item["completed"]:
            status = "ok"
        else:
            status = "pending"
        prompt_preview = _read_prompt_preview(repo_root, item.get("prompt_path", ""))
        history.append(
            {
                "id": item["dispatch_id"],
                "sequence": index,
                "kind": "dispatch",
                "timestamp": item.get("started_at") or item.get("completed_at") or "",
                "source": "orchestrator",
                "target": item.get("role", ""),
                "label": f"dispatch {item.get('role', '')}",
                "status": status,
                "thread_title": item.get("thread_title", ""),
                "dispatch_id": item["dispatch_id"],
                "completed": item["completed"],
                "error": item["error"],
                "round_id": "",
                "issue_ref": "",
                "stage": "",
                "fallback": False,
                "direct": item["completed"] and not item["error"],
                "prompt_path": item.get("prompt_path", ""),
                "prompt_preview": prompt_preview,
                "prompt_label": "prompt",
            }
        )
    return history


def _build_roundtable_history(repo_root: Path) -> List[Dict[str, Any]]:
    rounds = sorted(list_rounds(repo_root, limit=None), key=lambda item: item.get("created_at", ""))
    history = []
    sequence = 0
    for round_item in rounds:
        messages = round_item.get("messages") or []
        if messages:
            for message in messages:
                from_role = message.get("from_role", "") or "orchestrator"
                targets = message.get("to_roles") or []
                for target in targets:
                    sequence += 1
                    history.append(
                        {
                            "id": message.get("message_id") or f"{round_item.get('id', 'round')}:{sequence}",
                            "sequence": sequence,
                            "kind": "roundtable",
                            "timestamp": message.get("created_at") or round_item.get("updated_at") or round_item.get("created_at") or "",
                            "source": from_role,
                            "target": target,
                            "label": message.get("intent") or "peer",
                            "status": "warn" if message.get("fallback_kind") else ("ok" if message.get("protocol_status") == "accepted" else "pending"),
                            "thread_title": "",
                            "dispatch_id": "",
                            "completed": True,
                            "error": "",
                            "round_id": round_item.get("id", ""),
                            "issue_ref": round_item.get("issue_ref", ""),
                            "stage": message.get("intent", ""),
                            "fallback": bool(message.get("fallback_kind")),
                            "direct": not bool(message.get("fallback_kind")),
                            "parse_status": message.get("parse_mode", ""),
                            "codec": message.get("codec", ""),
                            "priority": message.get("priority", ""),
                            "interrupt": bool(message.get("interrupt")),
                            "token_budget": int(message.get("token_budget") or 0),
                            "declared_eta_seconds": int(message.get("eta_seconds") or 0),
                            "progress_state": message.get("progress_state", ""),
                            "last_stream_at": message.get("last_stream_at", ""),
                            "adaptive_deadline": message.get("adaptive_deadline", ""),
                            "extended_slices": int(message.get("extended_slices") or 0),
                            "timeout_reason": message.get("timeout_reason", ""),
                            "turn_index": sequence,
                            "prompt_preview": str(message.get("summary") or "").strip(),
                            "prompt_label": "packet" if message.get("parse_mode") == "direct" else "message",
                        }
                    )
            continue
        steps = round_item.get("steps", [])
        previous_role = "orchestrator"
        for turn_index, step in enumerate(steps, start=1):
            role = step.get("role", "")
            if not role:
                continue
            sequence += 1
            fallback = step.get("parse_status") == "fallback" or step.get("thread_id") == "local-fallback"
            status = "warn" if fallback else ("ok" if step.get("parse_status") in {"ok", ""} else "warn")
            history.append(
                {
                    "id": f"{round_item.get('id', 'round')}:{turn_index}",
                    "sequence": sequence,
                    "kind": "roundtable",
                    "timestamp": step.get("updated_at") or round_item.get("updated_at") or round_item.get("created_at") or "",
                    "source": previous_role,
                    "target": role,
                    "label": str(step.get("stage", "")).replace("_", " "),
                    "status": status,
                    "thread_title": step.get("thread_id", ""),
                    "dispatch_id": "",
                    "completed": True,
                    "error": "",
                    "round_id": round_item.get("id", ""),
                    "issue_ref": round_item.get("issue_ref", ""),
                    "stage": step.get("stage", ""),
                    "fallback": fallback,
                    "direct": not fallback,
                    "parse_status": step.get("parse_status", ""),
                    "declared_eta_seconds": int(step.get("eta_seconds") or 0),
                    "progress_state": step.get("progress_state", ""),
                    "last_stream_at": step.get("last_stream_at", ""),
                    "adaptive_deadline": step.get("adaptive_deadline", ""),
                    "extended_slices": int(step.get("extended_slices") or 0),
                    "timeout_reason": step.get("timeout_reason", ""),
                    "turn_index": turn_index,
                    "prompt_preview": str(step.get("raw") or "").strip(),
                    "prompt_label": "packet",
                }
            )
            previous_role = role
    return history


def _build_interaction_health(
    *,
    orchestrator: Dict[str, Any],
    teams: List[Dict[str, Any]],
    dispatch_metrics: Dict[str, Any],
    prompt_metrics: Dict[str, Any],
    round_metrics: Dict[str, Any],
    hook_metrics: Dict[str, Any],
    worker: Dict[str, Any],
    qa_observation: Dict[str, Any],
) -> Dict[str, Any]:
    healthy_roles = [
        team["role"]
        for team in teams
        if team.get("thread_id") and not team["stale"] and team["parse_status"] in ACCEPTED_PARSE_STATUSES and not has_blocker(team["blocker"])
    ]
    active_roles = [team["role"] for team in teams if team.get("thread_id") or team.get("thread_title")]
    protocol_ok_roles = [team["role"] for team in teams if team["parse_status"] in ACCEPTED_PARSE_STATUSES]
    latest_round = round_metrics["latest"]
    unbound_required = orchestrator["unbound_required_roles"]
    needs_sync_roles = [role for role in orchestrator["stale_roles"] if role not in unbound_required]
    needs_parse_repair_roles = [role for role in orchestrator["parse_error_roles"] if role not in unbound_required]
    return {
        "roles_total": len(ROLES),
        "bound_roles": len(orchestrator["required_roles"]) - len(orchestrator["unbound_required_roles"]),
        "healthy_roles": len(healthy_roles),
        "active_roles": len(active_roles),
        "protocol_ok_roles": len(protocol_ok_roles),
        "unbound_roles": orchestrator["unbound_roles"],
        "unbound_required_roles": orchestrator["unbound_required_roles"],
        "unbound_optional_roles": orchestrator["unbound_optional_roles"],
        "warm_roles": orchestrator["warm_roles"],
        "stale_roles": orchestrator["stale_roles"],
        "critical_roles": orchestrator["critical_roles"],
        "parse_error_roles": orchestrator["parse_error_roles"],
        "blocking_roles": orchestrator["blocking_roles"],
        "dispatch": dispatch_metrics,
        "open_dispatch_count": dispatch_metrics["open"],
        "open_dispatches": dispatch_metrics.get("open_items", []),
        "relay_prompts": prompt_metrics,
        "rounds": round_metrics,
        "hooks": hook_metrics,
        "worker_state": worker.get("state", "missing"),
        "latest_round": latest_round,
        "fallback_hotspot": latest_round.get("fallback_ratio", 0) >= 50,
        "needs_sync_roles": needs_sync_roles,
        "needs_parse_repair_roles": needs_parse_repair_roles,
        "qa_observation": qa_observation,
    }


def _build_effectiveness_summary(interaction_health: Dict[str, Any]) -> Dict[str, Any]:
    score = 100
    score -= len(interaction_health["unbound_required_roles"]) * 15
    score -= len(interaction_health["stale_roles"]) * 6
    score -= len(interaction_health["parse_error_roles"]) * 10
    score -= len(interaction_health["blocking_roles"]) * 8
    score -= interaction_health["hooks"]["block_count"] * 10
    score -= interaction_health["hooks"]["warn_count"] * 4
    if interaction_health["dispatch"]["total"] == 0:
        score -= 20
    else:
        score -= interaction_health["dispatch"]["open"] * 5
        if interaction_health["dispatch"]["success_rate"] < 60:
            score -= 10
    latest_round = interaction_health["latest_round"]
    if not latest_round.get("id"):
        score -= 15
    else:
        if latest_round["role_coverage_rate"] < 100:
            score -= 15
        if latest_round["fallback_ratio"] >= 75:
            score -= 20
        elif latest_round["fallback_ratio"] >= 25:
            score -= 8
        if not latest_round["has_retrospective"]:
            score -= 5
        if not latest_round["has_findings"]:
            score -= 5
    score = max(0, min(score, 100))

    if score >= 80:
        status = "effective"
        label = "효과적"
    elif score >= 60:
        status = "partial"
        label = "부분 효과"
    else:
        status = "needs-hardening"
        label = "보강 필요"

    strengths = []
    risks = []
    next_focus = []
    if interaction_health["dispatch"]["completed"] > 0:
        strengths.append(
            f"dispatch {interaction_health['dispatch']['completed']}건이 기록되어 기본 라우팅 경로는 동작한다."
        )
    if interaction_health["qa_observation"].get("follow_up_recommended"):
        strengths.append("`render_game_to_text`는 현재 active blocker가 아니라 follow-up 안정화 항목으로 분리 가능하다.")
    if interaction_health["rounds"]["completion_rate"] > 0:
        strengths.append(
            f"roundtable 완료율이 {interaction_health['rounds']['completion_rate']}%라서 라운드 산출물은 남는다."
        )
    if interaction_health["latest_round"].get("qa_evidence_present"):
        strengths.append("최신 라운드에 QA evidence와 findings가 있어 플레이 검토 흔적은 남는다.")
    if interaction_health["hooks"]["block_count"] == 0:
        strengths.append("최근 훅은 block 없이 advisory 중심으로 동작하고 있다.")

    if interaction_health["unbound_required_roles"]:
        risks.append(f"required role 미바인딩이 남아 있다: {', '.join(interaction_health['unbound_required_roles'])}")
        next_focus.append("required role thread를 bind해서 fallback 비중을 낮춘다.")
    if interaction_health["unbound_optional_roles"]:
        risks.append(f"optional coverage missing: {', '.join(interaction_health['unbound_optional_roles'])}")
    if interaction_health["stale_roles"]:
        risks.append(f"stale role이 많다: {', '.join(interaction_health['stale_roles'])}")
        next_focus.append("stale role을 다시 sync해서 실제 최신 판단을 올린다.")
    if interaction_health["parse_error_roles"]:
        risks.append(f"프로토콜 parse_error가 있다: {', '.join(interaction_health['parse_error_roles'])}")
        next_focus.append("고정 템플릿 강제가 아니라 compact/free-form parse 수용 범위를 더 다듬는다.")
    if interaction_health["latest_round"].get("fallback_ratio", 0) >= 50:
        risks.append(
            f"최신 라운드 fallback 비중이 {interaction_health['latest_round']['fallback_ratio']}%라 직접 상호작용이 약하다."
        )
        next_focus.append("local fallback 대신 실제 팀 세션 응답으로 라운드를 완주하게 만든다.")
    if interaction_health["dispatch"]["open"] > 0:
        risks.append(f"미완료 dispatch가 {interaction_health['dispatch']['open']}건 남아 있다.")
        next_focus.append("open dispatch를 1회 retry해서 local fallback 후보를 줄인다.")
    if interaction_health["qa_observation"].get("follow_up_recommended"):
        next_focus.append("`render_game_to_text` 재발 방지는 follow-up issue로 분리하고 active blocker로는 다루지 않는다.")

    if not strengths:
        strengths.append("최소 로그, 라운드, 훅 산출물은 축적되고 있다.")
    if not risks:
        risks.append("현재 스냅샷 기준 치명적 운영 위험은 없다.")
    if not next_focus:
        next_focus.append("현재 기준을 유지하면서 round 수와 direct response 비율을 더 쌓아본다.")

    if status == "effective":
        headline = "하네스가 직접 상호작용과 회고까지 비교적 안정적으로 굴러간다."
    elif status == "partial":
        headline = "하네스는 돌아가지만 실제 팀 간 상호작용보다 fallback과 stale 복구에 더 의존한다."
    else:
        headline = "하네스는 산출물은 만들지만 아직 실제 멀티팀 상호작용 품질이 낮다."

    return {
        "score": score,
        "status": status,
        "label": label,
        "headline": headline,
        "strengths": strengths[:4],
        "risks": risks[:4],
        "next_focus": next_focus[:4],
    }


def _build_harness_efficiency(interaction_health: Dict[str, Any], routing_graph: Dict[str, Any]) -> Dict[str, Any]:
    latest_round = interaction_health["latest_round"]
    history = routing_graph.get("history", {}).get("roundtable", [])
    total_routes = max(len(history), 1)
    direct_routes = sum(1 for item in history if item.get("direct"))
    fallback_routes = sum(1 for item in history if item.get("fallback"))
    compact_routes = sum(1 for item in history if item.get("codec") in {"compact", "kv", "symbolic"})
    interrupt_routes = sum(1 for item in history if item.get("interrupt"))
    budgeted_routes = sum(1 for item in history if int(item.get("token_budget") or 0) > 0)
    duplicate_routes = max(len(history) - len({(item.get("source"), item.get("target"), item.get("label")) for item in history}), 0)
    compact_bonus = min(12.0, (compact_routes / total_routes) * 12)
    routing_efficiency = max(0.0, min(100.0, (direct_routes / total_routes) * 100 - duplicate_routes * 5 - fallback_routes * 8 + compact_bonus))
    handoff_clarity = max(0.0, min(100.0, (interaction_health["protocol_ok_roles"] / max(interaction_health["active_roles"], 1)) * 100))
    total_questions = max(latest_round.get("open_questions_count", 0) + latest_round.get("resolved_questions_count", 0), 1)
    closure_efficiency = max(0.0, min(100.0, (latest_round.get("resolved_questions_count", 0) / total_questions) * 100))
    steering_overhead = max(0.0, min(100.0, 100 - latest_round.get("steering_events_count", 0) * 12))
    evidence_alignment = 100.0 if latest_round.get("qa_evidence_present") else 40.0
    insufficient = latest_round.get("messages_count", 0) < 3
    score = round(
        routing_efficiency * 0.25
        + handoff_clarity * 0.20
        + closure_efficiency * 0.25
        + steering_overhead * 0.15
        + evidence_alignment * 0.15,
        1,
    )
    drag_factors = []
    if fallback_routes > 0:
        drag_factors.append("timeout_fallback 또는 local fallback 비중이 높다.")
    if latest_round.get("timeout_fallback_steps", 0) > 0:
        drag_factors.append("adaptive timeout 조정이 더 필요하다.")
    if compact_routes < max(total_routes // 2, 1):
        drag_factors.append("compact packet 사용률이 낮다.")
    if latest_round.get("open_questions_count", 0) > latest_round.get("resolved_questions_count", 0):
        drag_factors.append("질문 미해결 carry-over가 남아 있다.")
    if duplicate_routes > 0:
        drag_factors.append("불필요한 duplicate route가 있다.")
    if interaction_health["unbound_required_roles"]:
        drag_factors.append("required role 준비도가 낮다.")
    if insufficient:
        status = "insufficient_data"
        label = "데이터 부족"
    elif score >= 80:
        status = "efficient"
        label = "효율적"
    elif score >= 60:
        status = "mixed"
        label = "부분 효율"
    else:
        status = "draggy"
        label = "마찰 큼"
    return {
        "status": status,
        "label": label,
        "score": score,
        "components": {
            "routing_efficiency": round(routing_efficiency, 1),
            "handoff_clarity": round(handoff_clarity, 1),
            "closure_efficiency": round(closure_efficiency, 1),
            "steering_overhead": round(steering_overhead, 1),
            "evidence_alignment": round(evidence_alignment, 1),
        },
        "drag_factors": drag_factors[:3],
        "trend": {
            "routes": len(history),
            "direct_routes": direct_routes,
            "fallback_routes": fallback_routes,
            "timeout_fallback_steps": latest_round.get("timeout_fallback_steps", 0),
            "upstream_timeout_steps": latest_round.get("upstream_timeout_steps", 0),
            "compact_routes": compact_routes,
            "interrupt_routes": interrupt_routes,
            "budgeted_routes": budgeted_routes,
            "resolved_questions": latest_round.get("resolved_questions_count", 0),
        },
    }


def _build_synthesis(
    *,
    orchestrator: Dict[str, Any],
    dispatch_metrics: Dict[str, Any],
    prompt_metrics: Dict[str, Any],
    round_metrics: Dict[str, Any],
    hook_metrics: Dict[str, Any],
    worker: Dict[str, Any],
    effectiveness: Dict[str, Any],
    harness_efficiency: Dict[str, Any],
    qa_observation: Dict[str, Any],
) -> Dict[str, Any]:
    latest_round = round_metrics["latest"]
    overview = (
        f"현재 하네스 판단은 `{effectiveness['label']}`이다. "
        f"dispatch 성공률은 {dispatch_metrics['success_rate']}%, "
        f"round 완료율은 {round_metrics['completion_rate']}%, "
        f"최신 round fallback 비중은 {latest_round.get('fallback_ratio', 0)}%다. "
        f"harness efficiency는 {harness_efficiency['label']} ({harness_efficiency['score']})다."
    )
    interaction_summary = (
        f"바인딩된 역할은 {len(ROLES) - len(orchestrator['unbound_roles'])}/{len(ROLES)}, "
        f"stale role은 {len(orchestrator['stale_roles'])}개, "
        f"parse_error role은 {len(orchestrator['parse_error_roles'])}개다. "
        f"relay prompt는 {prompt_metrics['roles_covered'] or ['없음']} 역할까지 생성됐다."
    )
    weak_points = []
    if orchestrator["unbound_roles"]:
        weak_points.append(f"gameplay_qa를 포함한 미바인딩 역할이 직접 대화 루프를 끊고 있다.")
    if orchestrator["parse_error_roles"]:
        weak_points.append(f"{', '.join(orchestrator['parse_error_roles'])} 응답은 현재 parser 수용 범위를 벗어나서 relay parse가 흔들린다.")
    if latest_round.get("fallback_ratio", 0) >= 50:
        weak_points.append("최근 round는 완주됐지만 대부분 local fallback으로 채워져 실제 peer-to-peer 품질은 낮다.")
    if worker.get("state") not in {"running", "polling", "idle"}:
        weak_points.append(f"worker 상태가 `{worker.get('state', 'missing')}`라 자동 라운드 안정성이 낮다.")
    if qa_observation.get("active_blocker"):
        weak_points.append("`render_game_to_text` 계약이 현재 QA 관측 경로를 직접 막고 있다.")

    working = []
    if hook_metrics["block_count"] == 0:
        working.append("최근 훅은 block 없이 intake/orchestrator/check 경로를 유지하고 있다.")
    if dispatch_metrics["completed"] > 0:
        working.append("dispatch와 prompt 파일이 남아 relay 자체가 아예 끊기지는 않았다.")
    if latest_round.get("has_summary") and latest_round.get("has_retrospective"):
        working.append("최신 round에 summary와 retrospective가 같이 남아 회고 루프는 작동한다.")
    if latest_round.get("has_findings"):
        working.append("Gameplay QA finding이 남아 제품 체감 피드백을 backlog로 연결할 기반이 있다.")
    if qa_observation.get("follow_up_recommended"):
        working.append("`render_game_to_text`는 현재 blocker가 아니므로 QA 관측 계약 안정화 follow-up으로 분리할 수 있다.")

    next_actions = list(effectiveness["next_focus"])
    next_actions.extend(harness_efficiency.get("drag_factors", []))
    if qa_observation.get("follow_up_recommended"):
        next_actions.append("QA 관측 표면 안정화 이슈로 `render_game_to_text` 계약을 후속 추적한다.")
    turns = latest_round.get("turns", [])
    return {
        "overview": overview,
        "interaction_summary": interaction_summary,
        "turns": turns,
        "working": working[:4],
        "weak_points": weak_points[:4],
        "next_actions": next_actions[:4],
    }


def _synthetic_parse_errors(repo_root: Path) -> List[Dict[str, Any]]:
    summary = summarize_orchestrator(repo_root)
    events = []
    for role in summary["parse_error_roles"]:
        entry = summary["entries"][role]
        events.append(
            {
                "timestamp": entry["updated_at"] or "",
                "event_type": "parse_error",
                "status": "warn",
                "summary": f"{role} parse_error",
                "details": [f"parse_status: {entry['parse_status']}"],
            }
        )
    return events


class DashboardHandler(BaseHTTPRequestHandler):
    def __init__(self, *args: Any, repo_root: Path, **kwargs: Any) -> None:
        self.repo_root = repo_root
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            return self._send_json(build_dashboard_payload(self.repo_root))
        if parsed.path == "/api/repair-queue":
            return self._send_json(build_repair_queue_payload(self.repo_root))
        if parsed.path.startswith("/api/team/"):
            role = parsed.path.split("/")[-1]
            if role not in ROLES:
                return self._send_json({"error": "unknown role"}, status=404)
            return self._send_json(build_team_payload(self.repo_root, role))
        if parsed.path == "/api/hooks":
            return self._send_json(build_hooks_payload(self.repo_root))
        if parsed.path == "/api/logs":
            query = parse_qs(parsed.query)
            kind = query.get("kind", [None])[0]
            return self._send_json(build_logs_payload(self.repo_root, kind))
        if parsed.path == "/health":
            return self._send_json(build_health_payload())
        return self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/repair-queue/enqueue":
            try:
                payload = self._read_json_body()
                item = enqueue_manual_improvement(
                    self.repo_root,
                    title=str(payload.get("title", "")).strip(),
                    reason=str(payload.get("reason", "")).strip(),
                    source=str(payload.get("source", "dashboard")).strip() or "dashboard",
                )
            except ValueError as exc:
                return self._send_json({"error": str(exc)}, status=400)
            return self._send_json(
                {
                    "item": item,
                    "repair_queue": build_repair_queue_payload(self.repo_root),
                },
                status=201,
            )
        if parsed.path.startswith("/api/repair-queue/"):
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) != 4:
                return self._send_json({"error": "invalid repair queue path"}, status=404)
            _, _, item_id, action = parts
            try:
                if action == "approve":
                    item = approve_repair_item(self.repo_root, item_id)
                elif action == "reject":
                    item = reject_repair_item(self.repo_root, item_id)
                else:
                    return self._send_json({"error": "unsupported repair queue action"}, status=404)
            except KeyError as exc:
                return self._send_json({"error": str(exc)}, status=404)
            except ValueError as exc:
                return self._send_json({"error": str(exc)}, status=409)
            return self._send_json(
                {
                    "item": item,
                    "repair_queue": build_repair_queue_payload(self.repo_root),
                }
            )
        return self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _serve_static(self, path: str) -> None:
        target = "index.html" if path in {"", "/"} else path.lstrip("/")
        candidate = STATIC_DIR / target
        if not candidate.exists() or not candidate.is_file():
            self.send_error(404, "Not Found")
            return
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("JSON object body가 필요합니다.")
        return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="golfsim Codex harness dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    def handler(*handler_args: Any, **handler_kwargs: Any) -> DashboardHandler:
        return DashboardHandler(*handler_args, repo_root=REPO_ROOT, **handler_kwargs)

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Dashboard listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
