from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

ROLES = ("pm", "planning", "design", "dev", "gameplay_qa")
REQUIRED_ROLES = ("pm", "planning", "design", "dev", "gameplay_qa")
OPTIONAL_ROLES = ()
WARM_AFTER = timedelta(minutes=30)
STALE_AFTER = timedelta(hours=4)
CRITICAL_AFTER = timedelta(hours=24)
ACCEPTED_PARSE_STATUSES = {"ok", "relaxed", "partial"}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def summarize_orchestrator(repo_root: Path, now: datetime | None = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    targets = load_json(repo_root / ".codex" / "orchestrator" / "targets.json", {})
    raw_state = load_json(repo_root / ".codex" / "orchestrator" / "state.json", {})
    state = normalize_state_map(raw_state)
    entries = {}
    stale_roles = []
    parse_error_roles = []
    blocking_roles = []
    unbound_roles = []
    unbound_required_roles = []
    unbound_optional_roles = []
    warm_roles = []
    critical_roles = []

    for role in ROLES:
        entry = normalize_team_entry(role, state.get(role, {}), now)
        entries[role] = entry
        if not targets.get(role):
            unbound_roles.append(role)
            if role in REQUIRED_ROLES:
                unbound_required_roles.append(role)
            else:
                unbound_optional_roles.append(role)
        if entry["freshness"] == "warm":
            warm_roles.append(role)
        if entry["freshness"] in {"stale", "critical"}:
            stale_roles.append(role)
        if entry["freshness"] == "critical":
            critical_roles.append(role)
        if entry["parse_status"] not in ACCEPTED_PARSE_STATUSES:
            parse_error_roles.append(role)
        if entry["risk_state"] == "blocked":
            blocking_roles.append(role)

    return {
        "targets": targets,
        "entries": entries,
        "required_roles": list(REQUIRED_ROLES),
        "optional_roles": list(OPTIONAL_ROLES),
        "targets_bound": len(unbound_required_roles) == 0,
        "unbound_roles": unbound_roles,
        "unbound_required_roles": unbound_required_roles,
        "unbound_optional_roles": unbound_optional_roles,
        "warm_roles": warm_roles,
        "stale_roles": stale_roles,
        "critical_roles": critical_roles,
        "parse_error_roles": parse_error_roles,
        "blocking_roles": blocking_roles,
    }


def normalize_state_map(raw_state: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(raw_state, dict):
        if "entries" in raw_state and isinstance(raw_state["entries"], list):
            mapped = {}
            for entry in raw_state["entries"]:
                if isinstance(entry, dict) and entry.get("role"):
                    mapped[entry["role"]] = entry
            return mapped
        return {key: value for key, value in raw_state.items() if isinstance(value, dict)}
    return {}


def normalize_team_entry(role: str, entry: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    updated_at = entry.get("updated_at")
    parsed_time = parse_timestamp(updated_at)
    freshness, age_minutes = compute_freshness(parsed_time, now)
    parse_status = entry.get("parse_status", "missing") or "missing"
    parse_mode = entry.get("parse_mode") or parse_status
    parse_confidence = float(entry.get("parse_confidence") or default_parse_confidence(parse_status))
    risk_state = derive_risk_state(entry.get("blocker", ""))
    return {
        "role": role,
        "last_dispatch_id": entry.get("last_dispatch_id"),
        "thread_id": entry.get("thread_id"),
        "thread_title": entry.get("thread_title", ""),
        "last_turn_id": entry.get("last_turn_id"),
        "last_status": entry.get("last_status", ""),
        "blocker": entry.get("blocker", ""),
        "next_request": entry.get("next_request", ""),
        "updated_at": updated_at,
        "last_stream_at": entry.get("last_stream_at"),
        "stale": freshness in {"stale", "critical"},
        "freshness": freshness,
        "age_minutes": age_minutes,
        "required_role": role in REQUIRED_ROLES,
        "risk_state": risk_state,
        "source": entry.get("source", "thread"),
        "parse_status": parse_status,
        "parse_mode": parse_mode,
        "parse_confidence": parse_confidence,
        "declared_eta_seconds": int(entry.get("declared_eta_seconds") or 0),
        "progress_state": entry.get("progress_state", ""),
    }


def parse_timestamp(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def has_blocker(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    normalized = " ".join(text.split()).lower()
    return normalized not in {
        "없음",
        "none",
        "- 없음",
        "blocker: 없음",
        "blocker: none",
        "- 개선 후보 선정 자체는 없음",
    }


def default_parse_confidence(parse_status: str) -> float:
    if parse_status == "ok":
        return 1.0
    if parse_status == "relaxed":
        return 0.8
    if parse_status == "partial":
        return 0.55
    if parse_status == "fallback":
        return 0.5
    return 0.25


def compute_freshness(parsed_time: datetime | None, now: datetime) -> tuple[str, int | None]:
    if parsed_time is None:
        return "critical", None
    age = now - parsed_time
    age_minutes = max(0, int(age.total_seconds() // 60))
    if age <= WARM_AFTER:
        return "fresh", age_minutes
    if age <= STALE_AFTER:
        return "warm", age_minutes
    if age <= CRITICAL_AFTER:
        return "stale", age_minutes
    return "critical", age_minutes


def derive_risk_state(blocker: Any) -> str:
    if has_blocker(blocker):
        return "blocked"
    text = str(blocker or "").strip()
    if text and text not in {"없음", "- 없음"}:
        return "review"
    return "clear"
