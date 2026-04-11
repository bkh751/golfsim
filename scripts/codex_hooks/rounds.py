from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROLES = ("pm", "planning", "design", "dev", "gameplay_qa")
REQUIRED_ROLES = ("pm", "planning", "design", "dev", "gameplay_qa")
OPTIONAL_ROLES = ()


def harness_dir(repo_root: Path) -> Path:
    return repo_root / ".codex" / "harness"


def rounds_dir(repo_root: Path) -> Path:
    return harness_dir(repo_root) / "rounds"


def reviews_dir(repo_root: Path) -> Path:
    return harness_dir(repo_root) / "reviews"


def backlog_drafts_dir(repo_root: Path) -> Path:
    return harness_dir(repo_root) / "backlog-drafts"


def logs_dir(repo_root: Path) -> Path:
    return harness_dir(repo_root) / "logs"


def qa_evidence_dir(repo_root: Path) -> Path:
    return harness_dir(repo_root) / "qa-evidence"


def round_queue_path(repo_root: Path) -> Path:
    return harness_dir(repo_root) / "round-requests.jsonl"


def worker_status_path(repo_root: Path) -> Path:
    return harness_dir(repo_root) / "worker-status.json"


def ensure_harness_dirs(repo_root: Path) -> None:
    for path in (
        harness_dir(repo_root),
        rounds_dir(repo_root),
        reviews_dir(repo_root),
        backlog_drafts_dir(repo_root),
        logs_dir(repo_root),
        qa_evidence_dir(repo_root),
    ):
        path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_changed_files(changed_files: List[str] | None) -> List[str]:
    seen = set()
    normalized = []
    for raw in changed_files or []:
        value = str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return sorted(normalized)


def sanitize_round_artifacts(repo_root: Path) -> int:
    ensure_harness_dirs(repo_root)
    updated = 0
    for path in rounds_dir(repo_root).glob("*.json"):
        payload = load_json(path, None)
        if not isinstance(payload, dict):
            continue
        dirty = False
        for key in ("started_at", "completed_at"):
            if payload.get(key) == "":
                payload.pop(key, None)
                dirty = True
        if dirty:
            save_json(path, payload)
            updated += 1
    return updated


def round_fingerprint(issue_ref: str, topic: str, changed_files: List[str] | None) -> str:
    joined = "\n".join([issue_ref.strip(), topic.strip(), *normalize_changed_files(changed_files)])
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def round_id(now: datetime, fingerprint: str) -> str:
    return f"round-{now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{fingerprint[:8]}"


def round_path(repo_root: Path, round_id_value: str) -> Path:
    return rounds_dir(repo_root) / f"{round_id_value}.json"


def load_round(repo_root: Path, round_id_value: str) -> Dict[str, Any] | None:
    payload = load_json(round_path(repo_root, round_id_value), None)
    if not isinstance(payload, dict):
        return None
    return payload


def save_round(repo_root: Path, round_payload: Dict[str, Any]) -> None:
    ensure_harness_dirs(repo_root)
    payload = dict(round_payload)
    payload["changed_files"] = normalize_changed_files(payload.get("changed_files"))
    save_json(round_path(repo_root, payload["id"]), payload)


def list_rounds(repo_root: Path, limit: int | None = None) -> List[Dict[str, Any]]:
    ensure_harness_dirs(repo_root)
    rounds = []
    for path in sorted(rounds_dir(repo_root).glob("*.json")):
        payload = load_json(path, None)
        if isinstance(payload, dict) and payload.get("id"):
            rounds.append(payload)
    rounds.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    if limit and limit > 0:
        return rounds[:limit]
    return rounds


def write_worker_status(repo_root: Path, payload: Dict[str, Any]) -> None:
    ensure_harness_dirs(repo_root)
    enriched = dict(payload)
    enriched.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    save_json(worker_status_path(repo_root), enriched)


def load_worker_status(repo_root: Path) -> Dict[str, Any]:
    payload = load_json(worker_status_path(repo_root), {})
    if not isinstance(payload, dict):
        return {}
    return payload


def create_round_request(
    repo_root: Path,
    *,
    issue_ref: str = "",
    trigger: str,
    changed_files: List[str] | None = None,
    topic: str = "",
    session_id: str = "",
    source: str = "hook",
) -> Tuple[Dict[str, Any], bool]:
    ensure_harness_dirs(repo_root)
    normalized_files = normalize_changed_files(changed_files)
    fingerprint = round_fingerprint(issue_ref, topic, normalized_files)

    for existing in list_rounds(repo_root):
        if existing.get("change_fingerprint") == fingerprint and existing.get("status") in {"pending", "running"}:
            return existing, True

    now = datetime.now(timezone.utc)
    round_payload = {
        "id": round_id(now, fingerprint),
        "issue_ref": issue_ref.strip(),
        "trigger": trigger.strip(),
        "topic": topic.strip(),
        "changed_files": normalized_files,
        "change_fingerprint": fingerprint,
        "session_id": session_id.strip(),
        "source": source,
        "status": "pending",
        "current_stage": "",
        "pending_reason": "",
        "error": "",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "participants": list(ROLES),
        "required_roles": list(REQUIRED_ROLES),
        "optional_roles": list(OPTIONAL_ROLES),
        "policy": {
            "mode": "steered_mesh",
            "goal": topic.strip() or "라운드 목표 미지정",
            "priorities": [],
            "allowed_roles": list(ROLES),
            "required_roles": list(REQUIRED_ROLES),
            "optional_roles": list(OPTIONAL_ROLES),
            "default_codec": "compact",
            "default_priority": "normal",
            "budget": {
                "max_hops_per_question": 8,
                "max_unanswered": 2,
                "max_tokens_per_packet": 96,
                "interrupt_window_secs": 15,
            },
        },
        "steps": [],
        "messages": [],
        "edges": [],
        "open_questions": [],
        "resolved_questions": [],
        "steering_events": [],
        "summary": "",
        "retrospective": "",
        "gameplay_findings": [],
        "backlog_candidates": [],
        "issue_draft_results": [],
        "review_path": "",
        "backlog_draft_path": "",
    }
    save_round(repo_root, round_payload)
    append_jsonl(
        round_queue_path(repo_root),
        {
            "event": "queued",
            "round_id": round_payload["id"],
            "issue_ref": round_payload["issue_ref"],
            "trigger": round_payload["trigger"],
            "status": round_payload["status"],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )
    return round_payload, False


def summarize_rounds(repo_root: Path, limit: int = 10) -> Dict[str, Any]:
    rounds = list_rounds(repo_root, limit=None)
    pending = [item for item in rounds if item.get("status") == "pending"]
    running = [item for item in rounds if item.get("status") == "running"]
    completed = [item for item in rounds if item.get("status") in {"completed", "resolved"}]
    failed = [item for item in rounds if item.get("status") == "failed"]
    latest_completed = completed[0] if completed else None
    return {
        "counts": {
            "pending": len(pending),
            "running": len(running),
            "completed": len(completed),
            "failed": len(failed),
        },
        "pending": pending[:limit],
        "running": running[:limit],
        "completed": completed[:limit],
        "latest_completed": latest_completed,
    }
