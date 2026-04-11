from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

QUEUE_FILENAME = "repair-queue.json"
PRIORITY_ORDER = {
    "required_bind_missing": 0,
    "stale_sync": 1,
    "parse_repair": 2,
    "dispatch_retry": 3,
    "fallback_hotspot_review": 4,
    "manual_improvement": 5,
}
STATUS_ORDER = {
    "running": 0,
    "approved": 1,
    "pending": 2,
    "manual_required": 3,
    "failed": 4,
    "done": 5,
    "rejected": 6,
}
ACTIVE_STATUSES = {"pending", "approved", "running", "manual_required"}
TERMINAL_STATUSES = {"done", "failed", "rejected"}
AUTO_EXECUTABLE_KINDS = {"stale_sync", "parse_repair", "dispatch_retry"}
MANUAL_KINDS = {"required_bind_missing", "fallback_hotspot_review"}
PERSISTENT_MANUAL_KINDS = {"manual_improvement"}
RECENT_TERMINAL_RETENTION = timedelta(hours=24)


def repair_queue_path(repo_root: Path) -> Path:
    return repo_root / ".codex" / "harness" / QUEUE_FILENAME


def load_repair_queue(repo_root: Path) -> List[Dict[str, Any]]:
    path = repair_queue_path(repo_root)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = payload.get("items", [])
    if not isinstance(payload, list):
        return []
    items = []
    for item in payload:
        if isinstance(item, dict) and item.get("id"):
            items.append(dict(item))
    return sort_repair_queue(items)


def save_repair_queue(repo_root: Path, items: List[Dict[str, Any]]) -> None:
    path = repair_queue_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"items": sort_repair_queue(items)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def repair_queue_counts(items: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts = {status: 0 for status in ("pending", "approved", "running", "done", "failed", "rejected", "manual_required")}
    for item in items:
        status = str(item.get("status", "")).strip()
        if status in counts:
            counts[status] += 1
    counts["total"] = sum(counts.values())
    return counts


def build_repair_candidates(interaction_health: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    latest_round = interaction_health.get("latest_round") or {}
    latest_round_id = str(latest_round.get("id", "")).strip()
    for role in interaction_health.get("unbound_required_roles") or []:
        candidates.append(
            _candidate(
                kind="required_bind_missing",
                target_role=role,
                reason=f"{role} role에 바인딩된 thread가 없어 readiness가 닫히지 않는다.",
                action="bind_required_role",
                auto_executable=False,
                requires_approval=False,
                title=f"{role} bind 필요",
            )
        )
    blocked_unbound = set(interaction_health.get("unbound_required_roles") or [])
    for role in interaction_health.get("needs_sync_roles") or []:
        if role in blocked_unbound:
            continue
        candidates.append(
            _candidate(
                kind="stale_sync",
                target_role=role,
                reason=f"{role} 최신 판단이 stale 상태라 짧은 sync가 필요하다.",
                action="sync_role_state",
                auto_executable=True,
                requires_approval=True,
                round_id=latest_round_id,
                title=f"{role} stale sync",
            )
        )
    for role in interaction_health.get("needs_parse_repair_roles") or []:
        if role in blocked_unbound:
            continue
        candidates.append(
            _candidate(
                kind="parse_repair",
                target_role=role,
                reason=f"{role} 응답이 parse_error라 compact/free-form 재정리가 필요하다.",
                action="repair_parse",
                auto_executable=True,
                requires_approval=True,
                round_id=latest_round_id,
                title=f"{role} parse repair",
            )
        )
    for dispatch in interaction_health.get("open_dispatches") or []:
        role = str(dispatch.get("role", "")).strip()
        dispatch_id = str(dispatch.get("dispatch_id", "")).strip()
        if not role or not dispatch_id:
            continue
        candidates.append(
            _candidate(
                kind="dispatch_retry",
                target_role=role,
                reason=f"{role} open dispatch {dispatch_id}가 완료되지 않아 1회 재시도가 필요하다.",
                action="retry_dispatch",
                auto_executable=True,
                requires_approval=True,
                dispatch_id=dispatch_id,
                round_id=latest_round_id,
                title=f"{role} dispatch retry",
            )
        )
    if interaction_health.get("fallback_hotspot"):
        ratio = latest_round.get("fallback_ratio", 0)
        candidates.append(
            _candidate(
                kind="fallback_hotspot_review",
                target_role="",
                reason=f"최신 라운드 fallback 비중이 {ratio}%라 수동 리뷰가 필요하다.",
                action="review_fallback_hotspot",
                auto_executable=False,
                requires_approval=False,
                round_id=latest_round_id,
                title="fallback hotspot review",
            )
        )
    return sort_repair_queue(candidates)


def sync_repair_queue(repo_root: Path, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    now = _now()
    existing_by_key = {str(item.get("dedupe_key", "")): item for item in load_repair_queue(repo_root)}
    merged: List[Dict[str, Any]] = []
    active_keys = set()

    for candidate in candidates:
        dedupe_key = str(candidate.get("dedupe_key", ""))
        active_keys.add(dedupe_key)
        current = existing_by_key.get(dedupe_key)
        merged.append(_merge_candidate(current, candidate, now))

    for key, item in existing_by_key.items():
        if key in active_keys:
            continue
        status = str(item.get("status", "")).strip()
        if item.get("kind") in PERSISTENT_MANUAL_KINDS and status not in TERMINAL_STATUSES:
            merged.append(dict(item))
            continue
        if status in {"approved", "running"}:
            merged.append(dict(item))
            continue
        if status in TERMINAL_STATUSES and _is_recent_terminal(item, now):
            merged.append(dict(item))

    merged = sort_repair_queue(merged)
    save_repair_queue(repo_root, merged)
    return merged


def approve_repair_item(repo_root: Path, item_id: str) -> Dict[str, Any]:
    return _transition_item(repo_root, item_id, "approve")


def reject_repair_item(repo_root: Path, item_id: str) -> Dict[str, Any]:
    return _transition_item(repo_root, item_id, "reject")


def enqueue_manual_improvement(repo_root: Path, *, title: str, reason: str, source: str = "dashboard") -> Dict[str, Any]:
    title = str(title).strip()
    reason = str(reason).strip()
    if not title or not reason:
        raise ValueError("title과 reason이 필요합니다.")
    text_key = hashlib.sha1(f"{title}\n{reason}".encode("utf-8")).hexdigest()[:12]
    dedupe_key = f"manual_improvement::-::-::{text_key}"
    now = _now()
    items = load_repair_queue(repo_root)
    for item in items:
        if item.get("dedupe_key") != dedupe_key:
            continue
        if item.get("status") in TERMINAL_STATUSES:
            continue
        item["updated_at"] = now
        save_repair_queue(repo_root, items)
        return item
    item = {
        "id": hashlib.sha1(dedupe_key.encode("utf-8")).hexdigest()[:12],
        "kind": "manual_improvement",
        "priority": PRIORITY_ORDER["manual_improvement"],
        "title": title,
        "reason": reason,
        "target_role": "",
        "action": "manual_improvement",
        "auto_executable": False,
        "requires_approval": False,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "dedupe_key": dedupe_key,
        "round_id": "",
        "dispatch_id": "",
        "source": source,
    }
    items.append(item)
    save_repair_queue(repo_root, items)
    return item


def list_approved_repairs(repo_root: Path) -> List[Dict[str, Any]]:
    return [
        item
        for item in load_repair_queue(repo_root)
        if item.get("status") == "approved" and item.get("auto_executable")
    ]


def mark_repair_running(repo_root: Path, item_id: str) -> Dict[str, Any]:
    items = load_repair_queue(repo_root)
    for item in items:
        if item.get("id") != item_id:
            continue
        if item.get("status") != "approved":
            raise ValueError("approved 상태의 repair만 running으로 전환할 수 있습니다.")
        item["status"] = "running"
        item["updated_at"] = _now()
        save_repair_queue(repo_root, items)
        return item
    raise KeyError(f"repair item을 찾을 수 없습니다: {item_id}")


def mark_repair_done(repo_root: Path, item_id: str, note: str = "") -> Dict[str, Any]:
    return _set_terminal_state(repo_root, item_id, "done", note)


def mark_repair_failed(repo_root: Path, item_id: str, note: str = "") -> Dict[str, Any]:
    return _set_terminal_state(repo_root, item_id, "failed", note)


def sort_repair_queue(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        (dict(item) for item in items),
        key=lambda item: (
            STATUS_ORDER.get(str(item.get("status", "")), 99),
            int(item.get("priority", 99)),
            str(item.get("updated_at") or item.get("created_at") or ""),
            str(item.get("title", "")),
        ),
    )


def _candidate(
    *,
    kind: str,
    target_role: str,
    reason: str,
    action: str,
    auto_executable: bool,
    requires_approval: bool,
    title: str,
    round_id: str = "",
    dispatch_id: str = "",
) -> Dict[str, Any]:
    dedupe_key = "::".join([kind, target_role or "-", round_id or "-", dispatch_id or "-"])
    item_id = hashlib.sha1(dedupe_key.encode("utf-8")).hexdigest()[:12]
    now = _now()
    return {
        "id": item_id,
        "kind": kind,
        "priority": PRIORITY_ORDER[kind],
        "title": title,
        "reason": reason,
        "target_role": target_role,
        "action": action,
        "auto_executable": auto_executable,
        "requires_approval": requires_approval,
        "status": "manual_required" if kind in MANUAL_KINDS else "pending",
        "created_at": now,
        "updated_at": now,
        "dedupe_key": dedupe_key,
        "round_id": round_id,
        "dispatch_id": dispatch_id,
    }


def _merge_candidate(current: Dict[str, Any] | None, candidate: Dict[str, Any], now: str) -> Dict[str, Any]:
    merged = dict(current or {})
    created_at = merged.get("created_at") or candidate.get("created_at") or now
    merged.update(candidate)
    merged["created_at"] = created_at
    merged["updated_at"] = now
    if candidate["kind"] in MANUAL_KINDS:
        merged["status"] = "manual_required"
        merged["auto_executable"] = False
        merged["requires_approval"] = False
        return merged

    current_status = str((current or {}).get("status", "")).strip()
    if current_status in {"approved", "running", "rejected"}:
        merged["status"] = current_status
    else:
        merged["status"] = "pending"
    return merged


def _transition_item(repo_root: Path, item_id: str, action: str) -> Dict[str, Any]:
    items = load_repair_queue(repo_root)
    for item in items:
        if item.get("id") != item_id:
            continue
        if item.get("status") == "running":
            raise ValueError("실행 중인 repair 항목은 상태를 바꿀 수 없습니다.")
        if action == "approve":
            if item.get("status") == "manual_required" or not item.get("auto_executable"):
                raise ValueError("이 repair 항목은 대시보드 승인 대상이 아닙니다.")
            item["status"] = "approved"
        else:
            item["status"] = "rejected"
        item["updated_at"] = _now()
        save_repair_queue(repo_root, items)
        return item
    raise KeyError(f"repair item을 찾을 수 없습니다: {item_id}")


def _set_terminal_state(repo_root: Path, item_id: str, status: str, note: str) -> Dict[str, Any]:
    items = load_repair_queue(repo_root)
    for item in items:
        if item.get("id") != item_id:
            continue
        item["status"] = status
        item["updated_at"] = _now()
        item["last_note"] = note
        save_repair_queue(repo_root, items)
        return item
    raise KeyError(f"repair item을 찾을 수 없습니다: {item_id}")


def _is_recent_terminal(item: Dict[str, Any], now: datetime) -> bool:
    updated_at = str(item.get("updated_at", "")).strip()
    if not updated_at:
        return False
    try:
        parsed = datetime.fromisoformat(updated_at)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return now - parsed.astimezone(timezone.utc) <= RECENT_TERMINAL_RETENTION


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
