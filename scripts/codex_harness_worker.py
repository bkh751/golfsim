from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from scripts.codex_hooks.orchestrator_state import OPTIONAL_ROLES, REQUIRED_ROLES, ROLES
from scripts.codex_hooks.repair_queue import (
    list_approved_repairs,
    load_repair_queue,
    mark_repair_done,
    mark_repair_failed,
    mark_repair_running,
)
from scripts.codex_hooks.rounds import (
    append_jsonl,
    backlog_drafts_dir,
    ensure_harness_dirs,
    harness_dir,
    list_rounds,
    load_json,
    qa_evidence_dir,
    reviews_dir,
    rounds_dir,
    sanitize_round_artifacts,
    save_json,
    save_round,
    write_worker_status,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = REPO_ROOT / ".codex" / "orchestrator" / "targets.json"
ROUND_LOG_PATH = harness_dir(REPO_ROOT) / "logs" / "rounds.jsonl"
WORKER_STATUS_PATH = harness_dir(REPO_ROOT) / "worker-status.json"
ACK_TIMEOUT_SECONDS = 15.0
PROGRESS_SLICE_SECONDS = 30.0
HEARTBEAT_POLL_SECONDS = 15.0
NO_PROGRESS_LIMIT = 2
MAX_ROUTE_WAIT_SECONDS = 300.0
ETA_BUFFER_SECONDS = 30.0
REPAIR_POLLING_EXTENSION_SECONDS = 90.0
RUNNING_STALE_SECONDS = 120.0
DEFAULT_PACKET_BUDGET = 96
INTERRUPT_PACKET_BUDGET = 64
INTERRUPT_FLUSH_LIMIT = 2


class MCPStdioClient:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.proc: subprocess.Popen[str] | None = None
        self.next_id = 1
        self.stderr_lines: List[str] = []

    def start(self) -> None:
        if self.proc and self.proc.poll() is None:
            return
        command = ["/bin/zsh", str(self.repo_root / "scripts" / "start-codex-orchestrator-mcp.sh")]
        self.proc = subprocess.Popen(
            command,
            cwd=self.repo_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._initialize()

    def close(self) -> None:
        if not self.proc:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self._request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )
        if result.get("isError"):
            raise RuntimeError(result["content"][0]["text"])
        content = result.get("content") or []
        text = content[0]["text"] if content else "{}"
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{name} 응답 JSON 해석 실패: {exc}: {text}") from exc

    def _initialize(self) -> None:
        self._request("initialize", {})
        self._notify("initialized", {})

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            raise RuntimeError("MCP 프로세스가 시작되지 않았습니다")
        request_id = self.next_id
        self.next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            line = self.proc.stdout.readline()
            if line == "":
                stderr = self.proc.stderr.read() if self.proc.stderr else ""
                raise RuntimeError(f"MCP 응답 대기 중 프로세스 종료: {stderr}")
            data = json.loads(line)
            if data.get("id") != request_id:
                continue
            if "error" in data:
                raise RuntimeError(data["error"].get("message", "unknown mcp error"))
            return data.get("result", {})

    def _write(self, payload: Dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("MCP stdin 사용 불가")
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="golfsim harness worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=8.0)
    args = parser.parse_args()

    ensure_harness_dirs(REPO_ROOT)
    sanitize_round_artifacts(REPO_ROOT)
    client = MCPStdioClient(REPO_ROOT)
    try:
        run_worker(client, once=args.once, poll_interval=args.poll_interval)
    finally:
        client.close()
    return 0


def run_worker(client: MCPStdioClient, *, once: bool, poll_interval: float) -> None:
    while True:
        pending = _list_processible_rounds()
        approved_repairs = list_approved_repairs(REPO_ROOT)
        write_worker_status(
            REPO_ROOT,
            {
                "state": "repair_pending" if approved_repairs else ("polling" if pending else "idle"),
                "pid": os.getpid(),
                "pending_rounds": len(pending),
                "pending_repairs": len(approved_repairs),
                "current_round_id": "",
                "current_repair_id": "",
                "repair_state": "",
                "last_error": "",
            },
        )
        if approved_repairs:
            process_repair(client, approved_repairs[0])
            if once:
                return
        elif pending:
            for round_payload in pending:
                process_round(client, round_payload["id"])
                if once:
                    return
        elif once:
            return
        time.sleep(poll_interval)


def process_repair(client: MCPStdioClient, item: Dict[str, Any]) -> None:
    item_id = str(item.get("id", "")).strip()
    kind = str(item.get("kind", "")).strip()
    role = str(item.get("target_role", "")).strip()
    if not item_id or not kind:
        return

    current = mark_repair_running(REPO_ROOT, item_id)
    write_worker_status(
        REPO_ROOT,
        {
            "state": "repairing",
            "pid": os.getpid(),
            "pending_rounds": _pending_round_count(),
            "pending_repairs": len(list_approved_repairs(REPO_ROOT)),
            "current_round_id": "",
            "current_repair_id": item_id,
            "repair_state": kind,
            "last_error": "",
        },
    )

    try:
        if role and role in _missing_targets():
            raise RuntimeError(f"{role} role bind 누락")
        client.start()
        result = _run_repair_action(client, current)
        if result.get("parse_status") not in {"ok", "relaxed", "partial"} or result.get("fallback_kind"):
            note = result.get("fallback_kind") or result.get("parse_status") or "repair 응답 수용 실패"
            mark_repair_failed(REPO_ROOT, item_id, str(note))
            write_worker_status(
                REPO_ROOT,
                {
                    "state": "idle",
                    "pid": os.getpid(),
                    "pending_rounds": _pending_round_count(),
                    "pending_repairs": len(list_approved_repairs(REPO_ROOT)),
                    "current_round_id": "",
                    "current_repair_id": "",
                    "repair_state": "",
                    "last_error": str(note),
                },
            )
            return
        summary = (
            result.get("parsed", {}).get("summary")
            or result.get("parsed", {}).get("result")
            or result.get("last_status")
            or "repair 완료"
        )
        mark_repair_done(REPO_ROOT, item_id, str(summary))
        write_worker_status(
            REPO_ROOT,
            {
                "state": "idle",
                "pid": os.getpid(),
                "pending_rounds": _pending_round_count(),
                "pending_repairs": len(list_approved_repairs(REPO_ROOT)),
                "current_round_id": "",
                "current_repair_id": "",
                "repair_state": "",
                "last_error": "",
            },
        )
    except Exception as exc:  # noqa: BLE001
        mark_repair_failed(REPO_ROOT, item_id, str(exc))
        write_worker_status(
            REPO_ROOT,
            {
                "state": "error",
                "pid": os.getpid(),
                "pending_rounds": _pending_round_count(),
                "pending_repairs": len(list_approved_repairs(REPO_ROOT)),
                "current_round_id": "",
                "current_repair_id": "",
                "repair_state": "",
                "last_error": str(exc),
            },
        )


def process_round(client: MCPStdioClient, round_id: str) -> None:
    round_payload = load_json(rounds_dir(REPO_ROOT) / f"{round_id}.json", {})
    if not isinstance(round_payload, dict) or not round_payload.get("id"):
        return

    missing_roles = _missing_targets()
    if missing_roles:
        round_payload["pending_reason"] = "바인딩 누락: " + ", ".join(missing_roles)
        round_payload["updated_at"] = _now()
        save_round(REPO_ROOT, round_payload)
        _log_round_event("pending", round_payload, [round_payload["pending_reason"]])
        write_worker_status(
            REPO_ROOT,
            {
                "state": "idle",
                "pid": os.getpid(),
                "pending_rounds": _pending_round_count(),
                "pending_repairs": len(list_approved_repairs(REPO_ROOT)),
                "current_round_id": "",
                "current_repair_id": "",
                "repair_state": "",
                "last_error": round_payload["pending_reason"],
            },
        )
        return

    client.start()
    round_payload.setdefault("required_roles", list(REQUIRED_ROLES))
    round_payload.setdefault("optional_roles", list(OPTIONAL_ROLES))
    round_payload.setdefault(
        "policy",
        {
            "mode": "steered_mesh",
            "goal": round_payload.get("topic") or "라운드 목표 미지정",
            "priorities": [],
            "allowed_roles": list(ROLES),
            "required_roles": list(REQUIRED_ROLES),
            "optional_roles": list(OPTIONAL_ROLES),
            "default_codec": "compact",
            "default_priority": "normal",
            "budget": {
                "max_hops_per_question": 8,
                "max_unanswered": 2,
                "max_tokens_per_packet": DEFAULT_PACKET_BUDGET,
                "interrupt_window_secs": 15,
            },
        },
    )
    round_payload.setdefault("messages", [])
    round_payload.setdefault("edges", [])
    round_payload.setdefault("open_questions", [])
    round_payload.setdefault("resolved_questions", [])
    round_payload.setdefault("steering_events", [])
    round_payload["status"] = "running"
    round_payload["pending_reason"] = ""
    round_payload["current_stage"] = "steering"
    round_payload["started_at"] = round_payload.get("started_at") or _now()
    round_payload["updated_at"] = _now()
    save_round(REPO_ROOT, round_payload)
    write_worker_status(
        REPO_ROOT,
        {
            "state": "running",
            "pid": os.getpid(),
            "pending_rounds": _pending_round_count(),
            "pending_repairs": len(list_approved_repairs(REPO_ROOT)),
            "current_round_id": round_id,
            "current_repair_id": "",
            "repair_state": "",
            "last_error": "",
        },
    )
    _log_round_event("running", round_payload, ["라운드 실행 시작"])

    try:
        evidence = _collect_gameplay_evidence(round_payload)
        steps: List[Dict[str, Any]] = []
        _steer_round(
            client,
            round_payload,
            goal=round_payload.get("topic") or "peer collaboration",
            priorities=["routing", "closure", "evidence"],
        )
        _persist_round_progress(round_payload, steps, "steering")
        _flush_interrupt_queue(client, round_payload, evidence, steps)

        qa_initial = _route_peer_turn(
            client,
            from_role="orchestrator",
            to_role="gameplay_qa",
            stage="gameplay_qa_initial",
            intent="evidence_probe",
            role="gameplay_qa",
            round_payload=round_payload,
            task_request="Gameplay QA 초기 실플레이 검토",
            prompt=_build_gameplay_qa_prompt(round_payload, evidence),
            evidence=evidence,
            steps=steps,
            needs_reply=True,
            priority="high",
        )
        steps.append(_as_step("gameplay_qa_initial", 1, qa_initial))
        _persist_round_progress(round_payload, steps, "pm_frame")
        _flush_interrupt_queue(client, round_payload, evidence, steps)

        pm_frame = _route_peer_turn(
            client,
            from_role="orchestrator",
            to_role="pm",
            stage="pm_frame",
            intent="policy_change",
            role="pm",
            round_payload=round_payload,
            task_request="PM 라운드 목표와 평가 축 확정",
            prompt=_build_pm_frame_prompt(round_payload, evidence, steps),
            evidence=evidence,
            steps=steps,
            needs_reply=True,
            priority="high",
        )
        steps.append(_as_step("pm_frame", 1, pm_frame))
        _persist_round_progress(round_payload, steps, "role_analysis")

        for role in ("planning", "design", "dev"):
            dispatch = _route_peer_turn(
                client,
                from_role="pm",
                to_role=role,
                stage=f"{role}_analysis",
                intent="analysis_request",
                role=role,
                round_payload=round_payload,
                task_request=f"{role} 1차 분석",
                prompt=_build_role_analysis_prompt(role, round_payload, evidence, steps),
                evidence=evidence,
                steps=steps,
                needs_reply=True,
            )
            steps.append(_as_step(f"{role}_analysis", 1, dispatch))
            _persist_round_progress(round_payload, steps, "role_analysis")
            _flush_interrupt_queue(client, round_payload, evidence, steps)

        planning_step = next((step for step in reversed(steps) if step.get("stage") == "planning_analysis"), None)
        if planning_step:
            dispatch = _route_peer_turn(
                client,
                from_role="planning",
                to_role="design",
                stage="planning_design_peer",
                intent="role_conflict",
                role="design",
                round_payload=round_payload,
                task_request="planning -> design peer sync",
                prompt=_build_peer_sync_prompt("planning", "design", round_payload, steps, planning_step),
                evidence=evidence,
                steps=steps,
                needs_reply=True,
                priority="high",
                interrupt=_step_requires_interrupt(planning_step),
                codec="kv",
                token_budget=72,
            )
            steps.append(_as_step("planning_design_peer", 2, dispatch))
            _persist_round_progress(round_payload, steps, "peer_sync")
            _flush_interrupt_queue(client, round_payload, evidence, steps)

        design_step = next((step for step in reversed(steps) if step.get("stage") == "design_analysis"), None)
        if design_step:
            dispatch = _route_peer_turn(
                client,
                from_role="design",
                to_role="dev",
                stage="design_dev_peer",
                intent="wide_impact",
                role="dev",
                round_payload=round_payload,
                task_request="design -> dev peer sync",
                prompt=_build_peer_sync_prompt("design", "dev", round_payload, steps, design_step),
                evidence=evidence,
                steps=steps,
                needs_reply=True,
                priority="high",
                interrupt=_step_requires_interrupt(design_step),
                codec="kv",
                token_budget=72,
            )
            steps.append(_as_step("design_dev_peer", 2, dispatch))
            _persist_round_progress(round_payload, steps, "peer_sync")
            _flush_interrupt_queue(client, round_payload, evidence, steps)

        qa_step = next((step for step in reversed(steps) if step.get("stage") == "gameplay_qa_initial"), None)
        if qa_step:
            dispatch = _route_peer_turn(
                client,
                from_role="gameplay_qa",
                to_role="pm",
                stage="qa_pm_peer",
                intent="evidence_alignment",
                role="pm",
                round_payload=round_payload,
                task_request="gameplay_qa -> pm peer sync",
                prompt=_build_peer_sync_prompt("gameplay_qa", "pm", round_payload, steps, qa_step),
                evidence=evidence,
                steps=steps,
                needs_reply=False,
                priority="high",
                codec="kv",
                token_budget=72,
            )
            steps.append(_as_step("qa_pm_peer", 2, dispatch))
            _persist_round_progress(round_payload, steps, "peer_sync")
            _flush_interrupt_queue(client, round_payload, evidence, steps)

        dev_step = next((step for step in reversed(steps) if step.get("stage") == "dev_analysis"), None)
        if dev_step:
            dispatch = _route_peer_turn(
                client,
                from_role="dev",
                to_role="pm",
                stage="dev_pm_peer",
                intent="implementation_risk",
                role="pm",
                round_payload=round_payload,
                task_request="dev -> pm peer sync",
                prompt=_build_peer_sync_prompt("dev", "pm", round_payload, steps, dev_step),
                evidence=evidence,
                steps=steps,
                needs_reply=True,
                priority="interrupt" if _step_requires_interrupt(dev_step) else "high",
                interrupt=_step_requires_interrupt(dev_step),
                codec="kv",
                token_budget=72,
            )
            steps.append(_as_step("dev_pm_peer", 2, dispatch))
            _persist_round_progress(round_payload, steps, "peer_sync")
            _flush_interrupt_queue(client, round_payload, evidence, steps)

        pm_final = _route_peer_turn(
            client,
            from_role="orchestrator",
            to_role="pm",
            stage="pm_final",
            intent="policy_change",
            role="pm",
            round_payload=round_payload,
            task_request="PM 최종 회고 및 백로그 합성",
            prompt=_build_pm_final_prompt(round_payload, evidence, steps),
            evidence=evidence,
            steps=steps,
            needs_reply=False,
            priority="high",
        )
        final_step = _as_step("pm_final", 2, pm_final)
        steps.append(final_step)
        _persist_round_progress(round_payload, steps, "issue_drafts")
        _flush_interrupt_queue(client, round_payload, evidence, steps)
        final_payload = _parse_harness_final_json(final_step["raw"])

        round_payload["steps"] = steps
        round_payload["current_stage"] = "issue_drafts"
        round_payload["summary"] = final_payload.get("round_summary") or final_step.get("result", "")
        round_payload["retrospective"] = final_payload.get("retrospective") or ""
        round_payload["gameplay_findings"] = final_payload.get("gameplay_findings") or _fallback_gameplay_findings(steps)
        round_payload["backlog_candidates"] = final_payload.get("backlog_candidates") or []
        round_payload["issue_draft_results"] = _create_issue_drafts(round_payload)
        review_path, backlog_path = _write_round_artifacts(round_payload, evidence)
        round_payload["review_path"] = str(review_path)
        round_payload["backlog_draft_path"] = str(backlog_path)
        _close_round(client, round_payload)
        round_payload["status"] = "resolved"
        round_payload["current_stage"] = "completed"
        round_payload["completed_at"] = _now()
        round_payload["updated_at"] = _now()
        save_round(REPO_ROOT, round_payload)
        _log_round_event(
            "completed",
            round_payload,
            [
                round_payload["summary"] or "요약 없음",
                f"backlog candidates: {len(round_payload['backlog_candidates'])}",
            ],
        )
        write_worker_status(
            REPO_ROOT,
            {
                "state": "idle",
                "pid": os.getpid(),
                "pending_rounds": _pending_round_count(),
                "pending_repairs": len(list_approved_repairs(REPO_ROOT)),
                "current_round_id": "",
                "current_repair_id": "",
                "repair_state": "",
                "last_completed_round_id": round_id,
                "last_error": "",
            },
        )
    except Exception as exc:  # noqa: BLE001
        round_payload["status"] = "failed"
        round_payload["error"] = str(exc)
        round_payload["updated_at"] = _now()
        round_payload["completed_at"] = _now()
        save_round(REPO_ROOT, round_payload)
        _log_round_event("failed", round_payload, [str(exc)])
        write_worker_status(
            REPO_ROOT,
            {
                "state": "error",
                "pid": os.getpid(),
                "pending_rounds": _pending_round_count(),
                "pending_repairs": len(list_approved_repairs(REPO_ROOT)),
                "current_round_id": round_id,
                "current_repair_id": "",
                "repair_state": "",
                "last_error": str(exc),
            },
        )


def _missing_targets() -> List[str]:
    targets = load_json(TARGETS_PATH, {})
    if not isinstance(targets, dict):
        return list(ROLES)
    return [role for role in ROLES if not str(targets.get(role, "")).strip()]


def _pending_round_count() -> int:
    return len([item for item in list_rounds(REPO_ROOT) if item.get("status") == "pending"])


def _run_repair_action(client: MCPStdioClient, item: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(item.get("kind", "")).strip()
    role = str(item.get("target_role", "")).strip()
    if kind == "stale_sync":
        return _route_peer_turn(
            client,
            from_role="orchestrator",
            to_role=role,
            stage=f"repair_{kind}",
            intent="sync_request",
            role=role,
            round_payload={"id": str(item.get("round_id", "")).strip(), "topic": "stale sync", "issue_ref": ""},
            task_request=f"{role} stale sync",
            prompt=_build_repair_sync_prompt(item),
            evidence={},
            steps=[],
            needs_reply=False,
            priority="high",
            codec="kv",
            token_budget=72,
            compression_hint="primitive",
            lane="priority",
            polling_extension_seconds=REPAIR_POLLING_EXTENSION_SECONDS,
        )
    if kind == "parse_repair":
        return _route_peer_turn(
            client,
            from_role="orchestrator",
            to_role=role,
            stage=f"repair_{kind}",
            intent="parse_repair",
            role=role,
            round_payload={"id": str(item.get("round_id", "")).strip(), "topic": "parse repair", "issue_ref": ""},
            task_request=f"{role} parse repair",
            prompt=_build_repair_parse_prompt(item),
            evidence={},
            steps=[],
            needs_reply=False,
            priority="high",
            codec="kv",
            token_budget=72,
            compression_hint="primitive",
            lane="priority",
            polling_extension_seconds=REPAIR_POLLING_EXTENSION_SECONDS,
        )
    if kind == "dispatch_retry":
        return _route_peer_turn(
            client,
            from_role="orchestrator",
            to_role=role,
            stage=f"repair_{kind}",
            intent="dispatch_retry",
            role=role,
            round_payload={"id": str(item.get("round_id", "")).strip(), "topic": "dispatch retry", "issue_ref": ""},
            task_request=f"{role} dispatch retry",
            prompt=_build_dispatch_retry_prompt(item),
            evidence={},
            steps=[],
            needs_reply=False,
            priority="high",
            codec="kv",
            token_budget=72,
            compression_hint="primitive",
            lane="priority",
            polling_extension_seconds=REPAIR_POLLING_EXTENSION_SECONDS,
        )
    raise RuntimeError(f"지원하지 않는 repair kind: {kind}")


def _list_processible_rounds() -> List[Dict[str, Any]]:
    worker_status = load_json(WORKER_STATUS_PATH, {})
    rounds = []
    for round_payload in list_rounds(REPO_ROOT):
        if round_payload.get("status") == "pending":
            rounds.append(round_payload)
            continue
        if _is_stale_running_round(round_payload, worker_status):
            rounds.append(round_payload)
    return rounds


def _is_stale_running_round(round_payload: Dict[str, Any], worker_status: Dict[str, Any]) -> bool:
    if round_payload.get("status") != "running":
        return False
    current_round_id = str(worker_status.get("current_round_id", "")).strip()
    pid = int(worker_status.get("pid") or 0)
    if current_round_id == round_payload.get("id") and _pid_alive(pid):
        return False
    updated_at = _parse_iso_timestamp(round_payload.get("updated_at", ""))
    if updated_at is None:
        return True
    return (datetime.now(timezone.utc) - updated_at).total_seconds() >= RUNNING_STALE_SECONDS


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _parse_iso_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _collect_gameplay_evidence(round_payload: Dict[str, Any]) -> Dict[str, Any]:
    command = ["node", "scripts/run-action.mjs", "test-actions.json"]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    payload: Dict[str, Any] = {
        "ok": result.returncode == 0,
        "command": " ".join(command),
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if payload["ok"]:
        try:
            payload["render_payload"] = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload["ok"] = False
            payload["stderr"] = (payload["stderr"] + "\nrender payload parse 실패").strip()
    save_json(qa_evidence_dir(REPO_ROOT) / f"{round_payload['id']}.json", payload)
    return payload


def _local_gameplay_qa_step(
    stage: str,
    turn_index: int,
    round_payload: Dict[str, Any],
    evidence: Dict[str, Any],
    steps: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result = _local_gameplay_qa_result(round_payload, evidence, steps, rebuttal=turn_index > 1)
    return {
        "stage": stage,
        "role": "gameplay_qa",
        "from_role": "orchestrator",
        "to_roles": ["gameplay_qa"],
        "turn_index": turn_index,
        "message_id": f"local-{stage}-{int(time.time() * 1000)}",
        "intent": "evidence_probe",
        "thread_id": "local-fallback",
        "turn_id": "",
        "parse_status": "fallback",
        "parse_mode": "local",
        "fallback_kind": "local_evidence",
        "last_status": result["status"],
        "blocker": result["blocker"],
        "next_request": result["next_request"],
        "needs_reply": result["next_request"] != "없음",
        "priority": "high",
        "interrupt": False,
        "codec": "compact",
        "token_budget": DEFAULT_PACKET_BUDGET,
        "compression_hint": "primitive",
        "lane": "priority",
        "understanding": result["understanding"],
        "result": result["result"],
        "raw": _render_five_section_text(result),
        "updated_at": _now(),
    }


def _local_gameplay_qa_result(
    round_payload: Dict[str, Any],
    evidence: Dict[str, Any],
    steps: List[Dict[str, Any]],
    *,
    rebuttal: bool,
) -> Dict[str, str]:
    findings = []
    blocker = "없음"
    if evidence.get("ok"):
        payload = evidence.get("render_payload") or {}
        findings.append("자동 플레이 evidence로 기본 샷 루프와 실시간 비행 정보를 확인했다.")
        if payload.get("cameraMode"):
            findings.append(f"현재 캡처 기준 카메라 모드는 {payload.get('cameraMode')} 이다.")
        recent = payload.get("recentShots") or []
        findings.append(f"최근 샷 이력은 {len(recent)}건까지 노출된다.")
    else:
        blocker = "자동 플레이 실패: " + (evidence.get("stderr") or "원인 미상")
        findings.append("자동 플레이가 실패해서 deterministic evidence와 현재 변경 범위 기준으로만 검토했다.")

    if rebuttal and steps:
        findings.append("동료 역할 제안 중 정보 과다보다 반복 플레이 감을 우선해야 한다는 축을 유지한다.")

    return {
        "status": "로컬 gameplay qa fallback",
        "understanding": f"{round_payload.get('topic') or '게임플레이 변경'}에 대해 gameplay_qa thread 대신 로컬 evidence를 사용한다.",
        "result": " ".join(findings[:3]),
        "blocker": blocker,
        "next_request": "PM이 최종 우선순위를 잠가야 한다." if not rebuttal else "없음",
    }


def _render_five_section_text(result: Dict[str, str]) -> str:
    lines = [
        f"st:{result['status']}",
        f"sc:{result['understanding']}",
        f"rs:{result['result']}",
    ]
    blocker = str(result.get("blocker", "")).strip()
    next_request = str(result.get("next_request", "")).strip()
    if blocker and blocker not in {"없음", "none", "None"}:
        lines.append(f"rk:{blocker}")
    if next_request and next_request not in {"없음", "none", "None"}:
        lines.append(f"ask:{next_request}")
    return " | ".join(lines)


def _route_peer_turn(
    client: MCPStdioClient,
    *,
    from_role: str,
    to_role: str,
    stage: str,
    intent: str,
    role: str,
    round_payload: Dict[str, Any],
    task_request: str,
    prompt: str,
    evidence: Dict[str, Any],
    steps: List[Dict[str, Any]],
    needs_reply: bool,
    priority: str = "normal",
    interrupt: bool = False,
    codec: str = "compact",
    token_budget: int = DEFAULT_PACKET_BUDGET,
    compression_hint: str = "primitive",
    lane: str = "",
    soft_timeout_seconds: float = ACK_TIMEOUT_SECONDS,
    poll_interval_seconds: float = HEARTBEAT_POLL_SECONDS,
    polling_extension_seconds: float = REPAIR_POLLING_EXTENSION_SECONDS,
    adaptive_timeout: bool | None = None,
    progress_slice_seconds: float = PROGRESS_SLICE_SECONDS,
    no_progress_limit: int = NO_PROGRESS_LIMIT,
    max_route_wait_seconds: float = MAX_ROUTE_WAIT_SECONDS,
    eta_buffer_seconds: float = ETA_BUFFER_SECONDS,
) -> Dict[str, Any]:
    _ = client
    adaptive_timeout = _adaptive_timeout_enabled(stage, priority, interrupt) if adaptive_timeout is None else adaptive_timeout
    route_client = MCPStdioClient(REPO_ROOT)
    poll_client = MCPStdioClient(REPO_ROOT)
    result: Dict[str, Any] = {}
    error: Dict[str, Exception] = {}
    prompt_to_send = _build_adaptive_prompt(prompt, soft_timeout_seconds) if adaptive_timeout else prompt
    lane_value = lane or ("interrupt" if interrupt or priority == "interrupt" else "priority" if priority == "high" else "default")
    route_args = {
        "from_role": from_role,
        "to_roles": [to_role],
        "round_id": round_payload.get("id"),
        "intent": intent,
        "message": prompt_to_send,
        "wait_mode": "completion",
        "needs_reply": needs_reply,
        "priority": priority,
        "interrupt": interrupt,
        "codec": codec,
        "token_budget": token_budget,
        "compression_hint": compression_hint,
        "lane": lane_value,
    }

    def _run() -> None:
        try:
            route_client.start()
            result["value"] = route_client.call_tool("route_turn", route_args)
        except Exception as exc:  # noqa: BLE001
            error["value"] = exc
        finally:
            route_client.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    start_monotonic = time.monotonic()
    start_wall = datetime.now(timezone.utc)
    hard_deadline = start_monotonic + max_route_wait_seconds
    adaptive_deadline = min(hard_deadline, start_monotonic + soft_timeout_seconds)
    extended_slices = 0
    no_progress_slices = 0
    declared_eta_seconds = 0
    timeout_reason = ""
    last_stream_at = ""
    progress_state = ""
    poll_client.start()

    try:
        if adaptive_timeout:
            while thread.is_alive():
                remaining = max(0.1, min(poll_interval_seconds, max(0.1, adaptive_deadline - time.monotonic())))
                thread.join(remaining)
                if not thread.is_alive():
                    break

                snapshot = _read_route_progress_state(poll_client, role=to_role)
                if snapshot:
                    last_stream_at = snapshot.get("last_stream_at", "") or last_stream_at
                    progress_state = snapshot.get("progress_state", "") or progress_state
                    if int(snapshot.get("declared_eta_seconds") or 0) > 0:
                        declared_eta_seconds = int(snapshot["declared_eta_seconds"])
                        adaptive_deadline = min(
                            hard_deadline,
                            max(adaptive_deadline, start_monotonic + declared_eta_seconds + eta_buffer_seconds),
                        )
                    if _route_progress_is_final(snapshot):
                        candidate = _progress_snapshot_to_dispatch(
                            snapshot,
                            from_role=from_role,
                            to_role=to_role,
                            intent=intent,
                            priority=priority,
                            interrupt=interrupt,
                            codec=codec,
                            token_budget=token_budget,
                            compression_hint=compression_hint,
                            lane=lane_value,
                        )
                        candidate = _attach_route_meta(
                            candidate,
                            declared_eta_seconds=declared_eta_seconds,
                            progress_state=progress_state,
                            last_stream_at=last_stream_at,
                            adaptive_deadline=_adaptive_deadline_iso(start_wall, start_monotonic, adaptive_deadline),
                            extended_slices=extended_slices,
                            timeout_reason="",
                        )
                        route_client.close()
                        thread.join(1.0)
                        poll_client.close()
                        return candidate

                    if _route_progress_has_activity(snapshot, progress_slice_seconds):
                        no_progress_slices = 0
                        next_deadline = min(hard_deadline, max(adaptive_deadline, time.monotonic() + progress_slice_seconds))
                        if next_deadline > adaptive_deadline:
                            extended_slices += 1
                            adaptive_deadline = next_deadline

                if thread.is_alive() and time.monotonic() >= adaptive_deadline:
                    no_progress_slices += 1
                    if time.monotonic() >= hard_deadline:
                        timeout_reason = "hard_cap_reached"
                        break
                    if no_progress_slices >= no_progress_limit:
                        timeout_reason = "no_ack" if not declared_eta_seconds and not last_stream_at else "no_heartbeat"
                        break
                    extended_slices += 1
                    adaptive_deadline = min(hard_deadline, time.monotonic() + progress_slice_seconds)
        else:
            thread.join(soft_timeout_seconds)
            if thread.is_alive():
                elapsed = 0.0
                while thread.is_alive() and elapsed < polling_extension_seconds:
                    thread.join(poll_interval_seconds)
                    elapsed += poll_interval_seconds
                if thread.is_alive():
                    timeout_reason = "no_heartbeat"
                    last_snapshot = _read_route_progress_state(poll_client, role=to_role)
                    if last_snapshot:
                        last_stream_at = last_snapshot.get("last_stream_at", "")
                        progress_state = last_snapshot.get("progress_state", "")
                        declared_eta_seconds = int(last_snapshot.get("declared_eta_seconds") or 0)
                    route_client.close()
                    thread.join(1.0)
                    rechecked = _recheck_route_team_state(
                        poll_client,
                        from_role=from_role,
                        to_role=to_role,
                        intent=intent,
                        priority=priority,
                        interrupt=interrupt,
                        codec=codec,
                        token_budget=token_budget,
                        compression_hint=compression_hint,
                        lane=lane_value,
                    )
                    if rechecked:
                        poll_client.close()
                        return _attach_route_meta(
                            rechecked,
                            declared_eta_seconds=declared_eta_seconds,
                            progress_state=progress_state,
                            last_stream_at=last_stream_at,
                            adaptive_deadline=_adaptive_deadline_iso(start_wall, start_monotonic, adaptive_deadline),
                            extended_slices=extended_slices,
                            timeout_reason="",
                        )
                    fallback = _local_dispatch_fallback(
                        from_role=from_role,
                        to_role=to_role,
                        intent=intent,
                        stage=stage,
                        role=role,
                        task_request=task_request,
                        round_payload=round_payload,
                        evidence=evidence,
                        steps=steps,
                        reason=f"route timeout {(soft_timeout_seconds + polling_extension_seconds):.0f}s",
                        fallback_kind=_timeout_fallback_kind(steps),
                        priority=priority,
                        interrupt=interrupt,
                        codec=codec,
                        token_budget=token_budget,
                        compression_hint=compression_hint,
                        lane=lane_value,
                        declared_eta_seconds=declared_eta_seconds,
                        progress_state=progress_state,
                        last_stream_at=last_stream_at,
                        adaptive_deadline=_adaptive_deadline_iso(start_wall, start_monotonic, adaptive_deadline),
                        extended_slices=extended_slices,
                        timeout_reason=timeout_reason,
                    )
                    _append_local_graph_entry(round_payload, _as_step(stage, 0, fallback))
                    poll_client.close()
                    return fallback

        if thread.is_alive():
            route_client.close()
            thread.join(1.0)
        if "value" in error:
            raise error["value"]
    except Exception as exc:  # noqa: BLE001
        route_client.close()
        thread.join(1.0)
        fallback = _local_dispatch_fallback(
            from_role=from_role,
            to_role=to_role,
            intent=intent,
            stage=stage,
            role=role,
            task_request=task_request,
            round_payload=round_payload,
            evidence=evidence,
            steps=steps,
            reason=str(exc),
            fallback_kind=_timeout_fallback_kind(steps),
            priority=priority,
            interrupt=interrupt,
            codec=codec,
            token_budget=token_budget,
            compression_hint=compression_hint,
            lane=lane_value,
            declared_eta_seconds=declared_eta_seconds,
            progress_state=progress_state,
            last_stream_at=last_stream_at,
            adaptive_deadline=_adaptive_deadline_iso(start_wall, start_monotonic, adaptive_deadline),
            extended_slices=extended_slices,
            timeout_reason=timeout_reason or "no_heartbeat",
        )
        _append_local_graph_entry(round_payload, _as_step(stage, 0, fallback))
        poll_client.close()
        return fallback
    if thread.is_alive():
        route_client.close()
        thread.join(1.0)
        rechecked = _recheck_route_team_state(
            poll_client,
            from_role=from_role,
            to_role=to_role,
            intent=intent,
            priority=priority,
            interrupt=interrupt,
            codec=codec,
            token_budget=token_budget,
            compression_hint=compression_hint,
            lane=lane_value,
        )
        if rechecked:
            poll_client.close()
            return _attach_route_meta(
                rechecked,
                declared_eta_seconds=declared_eta_seconds,
                progress_state=progress_state,
                last_stream_at=last_stream_at,
                adaptive_deadline=_adaptive_deadline_iso(start_wall, start_monotonic, adaptive_deadline),
                extended_slices=extended_slices,
                timeout_reason="",
            )
        fallback = _local_dispatch_fallback(
            from_role=from_role,
            to_role=to_role,
            intent=intent,
            stage=stage,
            role=role,
            task_request=task_request,
            round_payload=round_payload,
            evidence=evidence,
            steps=steps,
            reason=f"adaptive timeout {timeout_reason or 'unknown'}",
            fallback_kind=_timeout_fallback_kind(steps),
            priority=priority,
            interrupt=interrupt,
            codec=codec,
            token_budget=token_budget,
            compression_hint=compression_hint,
            lane=lane_value,
            declared_eta_seconds=declared_eta_seconds,
            progress_state=progress_state,
            last_stream_at=last_stream_at,
            adaptive_deadline=_adaptive_deadline_iso(start_wall, start_monotonic, adaptive_deadline),
            extended_slices=extended_slices,
            timeout_reason=timeout_reason or "no_heartbeat",
        )
        _append_local_graph_entry(round_payload, _as_step(stage, 0, fallback))
        poll_client.close()
        return fallback
    poll_client.close()

    routed = result["value"] or {}
    routed_results = routed.get("results") or []
    if not routed_results:
        fallback = _local_dispatch_fallback(
            from_role=from_role,
            to_role=to_role,
            intent=intent,
            stage=stage,
            role=role,
            task_request=task_request,
            round_payload=round_payload,
            evidence=evidence,
            steps=steps,
            reason="route 결과 비어 있음",
            fallback_kind="synthetic_ok",
            priority=priority,
            interrupt=interrupt,
            codec=codec,
            token_budget=token_budget,
            compression_hint=compression_hint,
            lane=lane_value,
            declared_eta_seconds=declared_eta_seconds,
            progress_state=progress_state,
            last_stream_at=last_stream_at,
            adaptive_deadline=_adaptive_deadline_iso(start_wall, start_monotonic, adaptive_deadline),
            extended_slices=extended_slices,
            timeout_reason="",
        )
        _append_local_graph_entry(round_payload, _as_step(stage, 0, fallback))
        return fallback
    dispatch = routed_results[0]
    dispatch["from_role"] = from_role
    dispatch["to_roles"] = [to_role]
    dispatch["intent"] = intent
    dispatch["message_id"] = routed.get("message_id", "")
    dispatch["open_question_id"] = routed.get("open_question_id", "")
    dispatch["priority"] = routed.get("priority") or priority
    dispatch["interrupt"] = bool(routed.get("interrupt") or interrupt)
    dispatch["codec"] = routed.get("codec") or codec
    dispatch["token_budget"] = routed.get("token_budget") or token_budget
    dispatch["compression_hint"] = routed.get("compression_hint") or compression_hint
    dispatch["lane"] = routed.get("lane") or lane_value
    dispatch = _attach_route_meta(
        dispatch,
        declared_eta_seconds=int(dispatch.get("parsed", {}).get("eta_seconds") or declared_eta_seconds),
        progress_state=dispatch.get("parsed", {}).get("progress_state") or progress_state,
        last_stream_at=last_stream_at,
        adaptive_deadline=_adaptive_deadline_iso(start_wall, start_monotonic, adaptive_deadline),
        extended_slices=extended_slices,
        timeout_reason="",
    )
    if dispatch.get("parse_status") not in {"ok", "relaxed", "partial"}:
        fallback = _local_dispatch_fallback(
            from_role=from_role,
            to_role=to_role,
            intent=intent,
            stage=stage,
            role=role,
            task_request=task_request,
            round_payload=round_payload,
            evidence=evidence,
            steps=steps,
            reason=f"parse_status={dispatch.get('parse_status') or 'unknown'}",
            fallback_kind="parse_fallback",
            priority=priority,
            interrupt=interrupt,
            codec=codec,
            token_budget=token_budget,
            compression_hint=compression_hint,
            lane=lane_value,
            declared_eta_seconds=declared_eta_seconds,
            progress_state=progress_state,
            last_stream_at=last_stream_at,
            adaptive_deadline=_adaptive_deadline_iso(start_wall, start_monotonic, adaptive_deadline),
            extended_slices=extended_slices,
            timeout_reason="",
        )
        _append_local_graph_entry(round_payload, _as_step(stage, 0, fallback))
        return fallback
    return dispatch


def _adaptive_timeout_enabled(stage: str, priority: str, interrupt: bool) -> bool:
    if interrupt or priority == "interrupt":
        return False
    return not str(stage or "").startswith("repair_")


def _build_adaptive_prompt(prompt: str, ack_timeout_seconds: float) -> str:
    return "\n".join(
        [
            f"첫 줄은 {int(ack_timeout_seconds)}초 안에 compact ack로 시작해라: st:ack | eta:90 | more:1 | risk:none | ask:none",
            "- 이어서 실제 답변을 계속 작성해라.",
            "- 최종 답이 이미 준비됐으면 st:final | eta:0 | more:0 으로 시작하고 바로 본문을 이어도 된다.",
            "",
            prompt,
        ]
    )


def _timeout_fallback_kind(steps: List[Dict[str, Any]]) -> str:
    for step in steps:
        if step.get("fallback_kind") in {"timeout_fallback", "upstream_timeout"}:
            return "upstream_timeout"
    return "timeout_fallback"


def _attach_route_meta(
    dispatch: Dict[str, Any],
    *,
    declared_eta_seconds: int,
    progress_state: str,
    last_stream_at: str,
    adaptive_deadline: str,
    extended_slices: int,
    timeout_reason: str,
) -> Dict[str, Any]:
    dispatch["declared_eta_seconds"] = int(declared_eta_seconds or 0)
    dispatch["progress_state"] = str(progress_state or "").strip()
    dispatch["last_stream_at"] = str(last_stream_at or "").strip()
    dispatch["adaptive_deadline"] = str(adaptive_deadline or "").strip()
    dispatch["extended_slices"] = int(extended_slices or 0)
    dispatch["timeout_reason"] = str(timeout_reason or "").strip()
    return dispatch


def _read_route_progress_state(client: MCPStdioClient, *, role: str) -> Dict[str, Any] | None:
    try:
        team = client.call_tool("read_team", {"role": role})
    except Exception:  # noqa: BLE001
        return None
    state = team.get("state") or {}
    raw = team.get("raw") or {}
    parsed = raw.get("parsed") or {}
    if raw.get("stream_text"):
        stream_parsed = _parse_progress_packet(raw.get("stream_text"))
        if stream_parsed:
            parsed = {**stream_parsed, **parsed}
    return {
        "thread_id": raw.get("thread_id") or state.get("thread_id") or "",
        "turn_id": raw.get("last_turn_id") or state.get("last_turn_id") or "",
        "last_status": str(raw.get("last_status") or state.get("last_status") or "").strip().lower(),
        "parse_status": raw.get("parse_status") or state.get("parse_status") or "",
        "parse_mode": raw.get("parse_mode") or state.get("parse_mode") or parsed.get("parse_mode", ""),
        "parse_confidence": raw.get("parse_confidence") or state.get("parse_confidence") or parsed.get("confidence") or 0,
        "blocker": raw.get("blocker") or state.get("blocker") or "없음",
        "next_request": raw.get("next_request") or state.get("next_request") or "없음",
        "parsed": parsed,
        "raw_text": raw.get("raw_final_text") or "",
        "stream_text": raw.get("stream_text") or "",
        "last_stream_at": raw.get("last_stream_at") or state.get("last_stream_at") or "",
        "declared_eta_seconds": int(raw.get("declared_eta_seconds") or state.get("declared_eta_seconds") or parsed.get("eta_seconds") or 0),
        "progress_state": raw.get("progress_state") or state.get("progress_state") or parsed.get("progress_state") or "",
        "more_coming": bool(parsed.get("more_coming")),
    }


def _parse_progress_packet(text: Any) -> Dict[str, Any]:
    packet = _extract_compact_packet(str(text or ""))
    if not packet:
        return {}
    progress_state = _normalize_progress_state(packet.get("progress_state") or packet.get("상태") or "")
    eta_seconds = _parse_int(packet.get("eta_seconds") or "0")
    more_coming = _parse_bool(packet.get("more_coming"))
    if not progress_state and not eta_seconds and "more_coming" not in packet:
        return {}
    return {
        "status": packet.get("상태", ""),
        "understanding": packet.get("이해한 범위", ""),
        "result": packet.get("결과", ""),
        "blocker": packet.get("blocker", "없음") or "없음",
        "next_request": packet.get("다음 요청", "없음") or "없음",
        "summary": packet.get("결과", "") or packet.get("상태", ""),
        "parse_mode": "compact",
        "confidence": 0.68,
        "eta_seconds": eta_seconds,
        "progress_state": progress_state,
        "more_coming": more_coming,
        "raw": str(text or ""),
    }


def _route_progress_is_final(snapshot: Dict[str, Any]) -> bool:
    if not snapshot:
        return False
    if snapshot.get("parse_status") not in {"ok", "relaxed", "partial"}:
        return False
    progress_state = str(snapshot.get("progress_state") or "").strip().lower()
    last_status = str(snapshot.get("last_status") or "").strip().lower()
    if progress_state == "final":
        return True
    return last_status not in {"dispatching", "running", "in_progress", "queued", "streaming", "ack", "work"}


def _route_progress_has_activity(snapshot: Dict[str, Any], window_seconds: float) -> bool:
    if not snapshot:
        return False
    if str(snapshot.get("progress_state") or "").strip().lower() in {"ack", "work"}:
        last_stream_at = _parse_iso_datetime(snapshot.get("last_stream_at"))
        if last_stream_at and (datetime.now(timezone.utc) - last_stream_at).total_seconds() <= max(window_seconds, 1.0):
            return True
    last_stream_at = _parse_iso_datetime(snapshot.get("last_stream_at"))
    if not last_stream_at:
        return False
    return (datetime.now(timezone.utc) - last_stream_at).total_seconds() <= max(window_seconds, 1.0)


def _progress_snapshot_to_dispatch(
    snapshot: Dict[str, Any],
    *,
    from_role: str,
    to_role: str,
    intent: str,
    priority: str,
    interrupt: bool,
    codec: str,
    token_budget: int,
    compression_hint: str,
    lane: str,
) -> Dict[str, Any]:
    parsed = snapshot.get("parsed") or {}
    return {
        "role": to_role,
        "from_role": from_role,
        "to_roles": [to_role],
        "intent": intent,
        "message_id": f"recheck-{to_role}-{int(time.time() * 1000)}",
        "thread_id": snapshot.get("thread_id") or "",
        "turn_id": snapshot.get("turn_id") or "",
        "parse_status": snapshot.get("parse_status") or "",
        "parse_mode": snapshot.get("parse_mode") or parsed.get("parse_mode", ""),
        "fallback_kind": "",
        "priority": priority,
        "interrupt": interrupt,
        "codec": parsed.get("codec") or codec,
        "token_budget": parsed.get("token_budget") or token_budget,
        "compression_hint": parsed.get("compression_hint") or compression_hint,
        "lane": parsed.get("lane") or lane,
        "last_status": parsed.get("status") or snapshot.get("last_status") or "",
        "parsed": {
            **parsed,
            "priority": parsed.get("priority") or priority,
            "interrupt": parsed.get("interrupt") if "interrupt" in parsed else interrupt,
            "codec": parsed.get("codec") or codec,
            "token_budget": parsed.get("token_budget") or token_budget,
            "compression_hint": parsed.get("compression_hint") or compression_hint,
            "lane": parsed.get("lane") or lane,
            "eta_seconds": parsed.get("eta_seconds") or snapshot.get("declared_eta_seconds") or 0,
            "progress_state": parsed.get("progress_state") or snapshot.get("progress_state") or "",
            "more_coming": parsed.get("more_coming", snapshot.get("more_coming", False)),
            "raw": parsed.get("raw") or snapshot.get("raw_text") or snapshot.get("stream_text") or "",
        },
    }


def _adaptive_deadline_iso(start_wall: datetime, start_monotonic: float, adaptive_deadline: float) -> str:
    seconds = max(0.0, adaptive_deadline - start_monotonic)
    return (start_wall + timedelta(seconds=seconds)).isoformat()


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _extract_compact_packet(text: str) -> Dict[str, str]:
    packet: Dict[str, str] = {}
    matched = 0
    candidate = str(text or "").replace("\r\n", "\n").replace("\n", " | ").replace(";", " | ")
    for chunk in candidate.split("|"):
        piece = chunk.strip()
        if not piece:
            continue
        separator = ":" if ":" in piece else "=" if "=" in piece else ""
        if not separator:
            continue
        key, value = piece.split(separator, 1)
        normalized = _normalize_compact_key(key)
        if not normalized:
            continue
        packet[normalized] = value.strip()
        matched += 1
    if matched < 3:
        return {}
    return packet


def _normalize_compact_key(value: str) -> str:
    lowered = str(value or "").strip().lower()
    if lowered in {"st", "status", "state"}:
        return "상태"
    if lowered in {"sc", "scope", "understanding", "owner", "ow"}:
        return "이해한 범위"
    if lowered in {"rs", "res", "result", "summary", "sum"}:
        return "결과"
    if lowered in {"bk", "blocker", "risk", "rk"}:
        return "blocker"
    if lowered in {"rq", "next", "next_request", "req", "request", "ask"}:
        return "다음 요청"
    if lowered in {"eta", "eta_seconds"}:
        return "eta_seconds"
    if lowered in {"pg", "progress", "progress_state", "work"}:
        return "progress_state"
    if lowered in {"more", "more_coming", "m"}:
        return "more_coming"
    return ""


def _normalize_progress_state(value: str) -> str:
    lowered = str(value or "").strip().lower()
    if lowered == "ack":
        return "ack"
    if lowered in {"work", "working", "streaming"}:
        return "work"
    if lowered in {"blocked", "block"}:
        return "blocked"
    if lowered in {"final", "done", "complete", "completed"}:
        return "final"
    return ""


def _parse_int(value: Any) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError:
        return 0


def _parse_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "t", "y", "yes", "on"}


def _recheck_route_team_state(
    client: MCPStdioClient,
    *,
    from_role: str,
    to_role: str,
    intent: str,
    priority: str,
    interrupt: bool,
    codec: str,
    token_budget: int,
    compression_hint: str,
    lane: str,
) -> Dict[str, Any] | None:
    snapshot = _read_route_progress_state(client, role=to_role)
    if not snapshot or not _route_progress_is_final(snapshot):
        return None
    return _progress_snapshot_to_dispatch(
        snapshot,
        from_role=from_role,
        to_role=to_role,
        intent=intent,
        priority=priority,
        interrupt=interrupt,
        codec=codec,
        token_budget=token_budget,
        compression_hint=compression_hint,
        lane=lane or ("interrupt" if interrupt or priority == "interrupt" else "priority" if priority == "high" else "default"),
    )


def _local_dispatch_fallback(
    *,
    from_role: str,
    to_role: str,
    intent: str,
    stage: str,
    role: str,
    task_request: str,
    round_payload: Dict[str, Any],
    evidence: Dict[str, Any],
    steps: List[Dict[str, Any]],
    reason: str,
    fallback_kind: str,
    priority: str,
    interrupt: bool,
    codec: str,
    token_budget: int,
    compression_hint: str,
    lane: str,
    declared_eta_seconds: int = 0,
    progress_state: str = "",
    last_stream_at: str = "",
    adaptive_deadline: str = "",
    extended_slices: int = 0,
    timeout_reason: str = "",
) -> Dict[str, Any]:
    result = _local_role_result(role, task_request, round_payload, evidence, steps, reason=reason)
    raw = result.pop("raw")
    return {
        "role": role,
        "from_role": from_role,
        "to_roles": [to_role],
        "intent": intent,
        "message_id": f"local-{stage}-{int(time.time() * 1000)}",
        "thread_id": "local-fallback",
        "turn_id": "",
        "parse_status": "fallback",
        "parse_mode": "local",
        "fallback_kind": fallback_kind,
        "priority": priority,
        "interrupt": interrupt,
        "codec": codec,
        "token_budget": token_budget,
        "compression_hint": compression_hint,
        "lane": lane or ("interrupt" if interrupt or priority == "interrupt" else "priority" if priority == "high" else "default"),
        "declared_eta_seconds": declared_eta_seconds,
        "progress_state": progress_state,
        "last_stream_at": last_stream_at,
        "adaptive_deadline": adaptive_deadline,
        "extended_slices": extended_slices,
        "timeout_reason": timeout_reason,
        "last_status": result["status"],
        "parsed": {
            **result,
            "parse_mode": "local",
            "confidence": 0.35,
            "needs_reply": result.get("next_request") not in {"", "없음"},
            "evidence_refs": ["local_fallback"],
            "priority": priority,
            "interrupt": interrupt,
            "codec": codec,
            "token_budget": token_budget,
            "compression_hint": compression_hint,
            "lane": lane or ("interrupt" if interrupt or priority == "interrupt" else "priority" if priority == "high" else "default"),
            "eta_seconds": declared_eta_seconds,
            "progress_state": progress_state,
            "raw": raw,
        },
    }


def _local_role_result(
    role: str,
    task_request: str,
    round_payload: Dict[str, Any],
    evidence: Dict[str, Any],
    steps: List[Dict[str, Any]],
    *,
    reason: str,
) -> Dict[str, str]:
    issue_ref = round_payload.get("issue_ref") or "미지정"
    topic = round_payload.get("topic") or "게임플레이 변경"
    evidence_line = "자동 플레이 evidence 기준" if evidence.get("ok") else "deterministic evidence 기준"
    if role == "pm" and "최종" in task_request:
        findings = _fallback_gameplay_findings(steps) or [
            "반복 플레이 감과 정보 밀도 균형을 우선 확인해야 한다.",
            "카메라, HUD, 입력은 직관성을 먼저 유지해야 한다.",
        ]
        payload = {
            "round_summary": f"{topic} 기준으로 즉시 수정과 백로그 분리를 마쳤다.",
            "retrospective": f"{evidence_line} {reason} 상황에서도 라운드를 끝까지 수렴시키는 폴백이 필요했다.",
            "gameplay_findings": findings[:3],
            "backlog_candidates": [],
        }
        result_text = (
            "즉시 수정 우선순위는 플레이 감 유지, 정보 과다 억제, 고정 카메라/입력 일관성이다."
        )
        raw = _render_five_section_text(
            {
                "status": "로컬 pm 최종 fallback",
                "understanding": f"{issue_ref} / {topic} 라운드의 최종 합성을 로컬에서 마무리한다.",
                "result": result_text,
                "blocker": "없음",
                "next_request": "없음",
            }
        )
        raw += "\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
        return {
            "status": "로컬 pm 최종 fallback",
            "understanding": f"{issue_ref} / {topic} 라운드의 최종 합성을 로컬에서 마무리한다.",
            "result": result_text,
            "blocker": "없음",
            "next_request": "없음",
            "raw": raw,
        }
    if role == "pm":
        result = {
            "status": "로컬 pm fallback",
            "understanding": f"{issue_ref} / {topic} 라운드에서 평가 축과 범위를 잠근다.",
            "result": "평가 축은 반복 플레이 감, 정보 밀도, 조작 명확성 세 가지로 유지한다. out of scope는 과도한 신규 시스템 확장이다.",
            "blocker": "없음",
            "next_request": "planning, design, dev는 각각 플레이 감을 해치지 않는 즉시 수정안과 backlog 분리를 제안한다.",
        }
    elif role == "planning":
        result = {
            "status": "로컬 planning fallback",
            "understanding": f"{topic} 변경을 기획 기준으로 정리한다.",
            "result": "좋은 점은 샷 루프와 반복 사용성이 선명해졌다는 점이다. 위험은 조작/정보가 조금만 늘어도 난이도가 급격히 오를 수 있다는 점이다. 즉시 수정은 입력 규칙과 상태 전이를 더 명확히 드러내는 것이다.",
            "blocker": "없음",
            "next_request": "design은 정보 계층을 더 압축하고 dev는 상태 전이를 더 안정화해야 한다.",
        }
    elif role == "design":
        result = {
            "status": "로컬 design fallback",
            "understanding": f"{topic} 변경을 화면과 상호작용 관점에서 본다.",
            "result": "좋은 점은 결과 카드와 실시간 배지가 게임 화면을 크게 방해하지 않는다는 점이다. 위험은 카메라/에이밍/과거 궤적이 겹칠 때 의미가 불명확해지는 것이다. 즉시 수정은 active 정보와 history 정보를 더 강하게 분리하는 것이다.",
            "blocker": "없음",
            "next_request": "dev는 오버레이 중첩과 라벨 충돌을 줄이고 planning은 노출 우선순위를 고정해야 한다.",
        }
    elif role == "gameplay_qa":
        result = _local_gameplay_qa_result(round_payload, evidence, steps, rebuttal=False)
        result["status"] = "로컬 gameplay_qa fallback"
    else:
        result = {
            "status": "로컬 dev fallback",
            "understanding": f"{topic} 변경의 구현 안정성과 회귀 위험을 본다.",
            "result": "좋은 점은 현재 구조가 상태 머신 중심이라 점진 수정이 가능하다는 점이다. 위험은 원격 팀 응답 대기나 복합 상태에서 라운드가 쉽게 멈출 수 있다는 점이다. 즉시 수정은 타임아웃, stale recovery, 단계별 저장 같은 운영 안정화다.",
            "blocker": "없음",
            "next_request": "pm은 즉시 수정과 backlog 경계를 잠그고 design은 오버레이 규칙을 더 명확히 해야 한다.",
        }
    result["result"] += f" 로컬 fallback 사유: {reason}."
    result["raw"] = _render_five_section_text(result)
    return result


def _persist_round_progress(round_payload: Dict[str, Any], steps: List[Dict[str, Any]], stage: str) -> None:
    existing = load_json(rounds_dir(REPO_ROOT) / f"{round_payload['id']}.json", {})
    if isinstance(existing, dict):
        for key in ("messages", "edges", "open_questions", "resolved_questions", "steering_events", "policy", "required_roles", "optional_roles"):
            if key in existing:
                round_payload[key] = existing[key]
    round_payload["steps"] = steps
    round_payload["current_stage"] = stage
    round_payload["updated_at"] = _now()
    save_round(REPO_ROOT, round_payload)


def _flush_interrupt_queue(
    client: MCPStdioClient,
    round_payload: Dict[str, Any],
    evidence: Dict[str, Any],
    steps: List[Dict[str, Any]],
) -> None:
    try:
        graph = client.call_tool("read_round_graph", {"round_id": round_payload["id"]})
    except Exception:  # noqa: BLE001
        return

    open_questions = graph.get("open_questions") or []
    pending = [
        question
        for question in open_questions
        if question.get("status") in {"open", "needs_steer"}
        and (question.get("interrupt") or question.get("priority") in {"interrupt", "high"} or question.get("status") == "needs_steer")
    ]
    if not pending:
        return

    pending.sort(key=_interrupt_sort_key)
    for question in pending[:INTERRUPT_FLUSH_LIMIT]:
        stage = f"interrupt_{str(question.get('id') or 'q').replace('-', '_')[:18]}"
        dispatch = _route_peer_turn(
            client,
            from_role="orchestrator",
            to_role="pm",
            stage=stage,
            intent="policy_change",
            role="pm",
            round_payload=round_payload,
            task_request="interrupt steering",
            prompt=_build_interrupt_steering_prompt(round_payload, steps, question, evidence),
            evidence=evidence,
            steps=steps,
            needs_reply=False,
            priority="interrupt",
            interrupt=True,
            codec="kv",
            token_budget=INTERRUPT_PACKET_BUDGET,
            compression_hint="primitive",
            lane="interrupt",
        )
        steps.append(_as_step(stage, len(steps) + 1, dispatch))
        _persist_round_progress(round_payload, steps, "interrupt_steering")
        resolution = dispatch.get("parsed", {}).get("summary") or dispatch.get("parsed", {}).get("result") or dispatch.get("last_status", "") or "interrupt reviewed"
        try:
            client.call_tool(
                "resolve_question",
                {
                    "round_id": round_payload["id"],
                    "question_id": question.get("id"),
                    "resolution": resolution,
                    "decided_by": "pm",
                    "resolved_via": "interrupt_steering",
                },
            )
        except Exception:  # noqa: BLE001
            continue


def _interrupt_sort_key(question: Dict[str, Any]) -> tuple[int, int, int, str]:
    interrupt_rank = 0 if question.get("interrupt") else 1
    status_rank = 0 if question.get("status") == "needs_steer" else 1
    priority = str(question.get("priority", "normal"))
    priority_rank = {"interrupt": 0, "high": 1, "normal": 2, "low": 3}.get(priority, 2)
    created = str(question.get("created_at", ""))
    return (interrupt_rank, status_rank, priority_rank, created)


def _step_requires_interrupt(step: Dict[str, Any] | None) -> bool:
    if not step:
        return False
    blocker = str(step.get("blocker", "")).strip()
    if blocker and blocker not in {"없음", "none", "None"}:
        return True
    text = " ".join(
        str(step.get(key, ""))
        for key in ("result", "last_status", "next_request", "understanding")
    ).lower()
    return any(keyword in text for keyword in ("urgent", "interrupt", "critical", "회귀", "막힘", "block"))


def _as_step(stage: str, turn_index: int, dispatch: Dict[str, Any]) -> Dict[str, Any]:
    parsed = dispatch.get("parsed") or {}
    return {
        "stage": stage,
        "role": dispatch.get("role", ""),
        "from_role": dispatch.get("from_role", ""),
        "to_roles": dispatch.get("to_roles", []),
        "turn_index": turn_index,
        "message_id": dispatch.get("message_id", ""),
        "intent": dispatch.get("intent", ""),
        "thread_id": dispatch.get("thread_id", ""),
        "turn_id": dispatch.get("turn_id", ""),
        "parse_status": dispatch.get("parse_status", ""),
        "parse_mode": dispatch.get("parse_mode", parsed.get("parse_mode", dispatch.get("parse_status", ""))),
        "fallback_kind": dispatch.get("fallback_kind", ""),
        "last_status": parsed.get("status") or dispatch.get("last_status", ""),
        "blocker": parsed.get("blocker", ""),
        "next_request": parsed.get("next_request", ""),
        "needs_reply": bool(parsed.get("needs_reply") or (parsed.get("next_request") and parsed.get("next_request") != "없음")),
        "priority": parsed.get("priority") or dispatch.get("priority", "normal"),
        "interrupt": bool(parsed.get("interrupt") or dispatch.get("interrupt")),
        "codec": parsed.get("codec") or dispatch.get("codec", "plain"),
        "token_budget": int(parsed.get("token_budget") or dispatch.get("token_budget") or 0),
        "compression_hint": parsed.get("compression_hint") or dispatch.get("compression_hint", ""),
        "lane": parsed.get("lane") or dispatch.get("lane", ""),
        "eta_seconds": int(parsed.get("eta_seconds") or dispatch.get("declared_eta_seconds") or 0),
        "progress_state": parsed.get("progress_state") or dispatch.get("progress_state", ""),
        "more_coming": bool(parsed.get("more_coming")),
        "last_stream_at": dispatch.get("last_stream_at", ""),
        "adaptive_deadline": dispatch.get("adaptive_deadline", ""),
        "extended_slices": int(dispatch.get("extended_slices") or 0),
        "timeout_reason": dispatch.get("timeout_reason", ""),
        "understanding": parsed.get("understanding", ""),
        "result": parsed.get("result", ""),
        "confidence": float(parsed.get("confidence") or 0),
        "evidence_refs": parsed.get("evidence_refs", []),
        "raw": parsed.get("raw", ""),
        "updated_at": _now(),
    }


def _steer_round(client: MCPStdioClient, round_payload: Dict[str, Any], *, goal: str, priorities: List[str]) -> None:
    client.call_tool(
        "steer_round",
        {
            "round_id": round_payload["id"],
            "actor": "orchestrator",
            "goal": goal,
            "priorities": priorities,
            "required_roles": list(REQUIRED_ROLES),
            "optional_roles": list(OPTIONAL_ROLES),
            "allowed_roles": list(ROLES),
            "budget": {
                "max_hops_per_question": 8,
                "max_unanswered": 2,
                "max_tokens_per_packet": DEFAULT_PACKET_BUDGET,
                "interrupt_window_secs": 15,
            },
            "reason": "worker bootstrap",
        },
    )


def _close_round(client: MCPStdioClient, round_payload: Dict[str, Any]) -> None:
    client.call_tool(
        "close_round",
        {
            "round_id": round_payload["id"],
            "summary": round_payload.get("summary") or "-",
            "retrospective": round_payload.get("retrospective") or "",
            "closed_by": "orchestrator",
        },
    )


def _append_local_graph_entry(round_payload: Dict[str, Any], step: Dict[str, Any]) -> None:
    round_payload.setdefault("messages", [])
    round_payload.setdefault("edges", [])
    now = _now()
    message_id = step.get("message_id") or f"local-{step.get('stage', 'step')}-{int(time.time() * 1000)}"
    round_payload["messages"].append(
        {
            "message_id": message_id,
            "round_id": round_payload.get("id", ""),
            "from_role": step.get("role") or step.get("from_role") or "local-fallback",
            "to_roles": step.get("to_roles") or [],
            "intent": step.get("intent") or "local_fallback",
            "summary": step.get("result") or step.get("last_status") or "",
            "requests": [step.get("next_request")] if step.get("next_request") and step.get("next_request") != "없음" else [],
            "risks": [step.get("blocker")] if step.get("blocker") and step.get("blocker") != "없음" else [],
            "confidence": step.get("confidence") or 0.35,
            "needs_reply": bool(step.get("needs_reply")),
            "protocol_status": "review",
            "priority": step.get("priority") or "normal",
            "interrupt": bool(step.get("interrupt")),
            "codec": step.get("codec") or "compact",
            "token_budget": step.get("token_budget") or DEFAULT_PACKET_BUDGET,
            "compression_hint": step.get("compression_hint") or "primitive",
            "lane": step.get("lane") or ("interrupt" if step.get("interrupt") else "default"),
            "eta_seconds": step.get("eta_seconds") or 0,
            "progress_state": step.get("progress_state") or "",
            "more_coming": bool(step.get("more_coming")),
            "last_stream_at": step.get("last_stream_at") or "",
            "adaptive_deadline": step.get("adaptive_deadline") or "",
            "extended_slices": step.get("extended_slices") or 0,
            "timeout_reason": step.get("timeout_reason") or "",
            "parse_mode": step.get("parse_mode") or "local",
            "fallback_kind": step.get("fallback_kind") or "synthetic_ok",
            "created_at": now,
        }
    )
    for target in step.get("to_roles") or []:
        round_payload["edges"].append(
            {
                "id": f"edge-{message_id}-{target}",
                "round_id": round_payload.get("id", ""),
                "from_role": step.get("from_role") or "orchestrator",
                "to_role": target,
                "message_id": message_id,
                "intent": step.get("intent") or "local_fallback",
                "accepted": False,
                "status": "warn",
                "priority": step.get("priority") or "normal",
                "interrupt": bool(step.get("interrupt")),
                "codec": step.get("codec") or "compact",
                "lane": step.get("lane") or ("interrupt" if step.get("interrupt") else "default"),
                "fallback_kind": step.get("fallback_kind") or "synthetic_ok",
                "created_at": now,
            }
        )


def _build_repair_sync_prompt(item: Dict[str, Any]) -> str:
    role = item.get("target_role") or "team"
    return "\n".join(
        [
            f"{role} 최신 판단만 짧게 다시 sync.",
            "- 자유 형식 또는 kv 둘 다 가능.",
            "- 핵심만 남겨라. 형식 채우기 금지.",
            "- blocker 없으면 굳이 없음 반복하지 마라.",
            "- 있으면 ask, risk, owner만 짧게 적어라.",
            "",
            f"reason: {item.get('reason', '-')}",
            "예시: st:ok | rs:hud cut keep | ask:pm lock",
        ]
    )


def _build_repair_parse_prompt(item: Dict[str, Any]) -> str:
    role = item.get("target_role") or "team"
    return "\n".join(
        [
            f"{role} 마지막 판단을 compact/free-form으로 짧게 다시 말해라.",
            "- ask, owner, bullet 1~3줄 허용.",
            "- 문맥만 살리고 형식 채우기 금지.",
            "- 결과와 남은 요청이 있으면 그것만 적어라.",
            "",
            f"reason: {item.get('reason', '-')}",
            "예시: rs:overlay cut, keep carry; ask:dev patch",
        ]
    )


def _build_dispatch_retry_prompt(item: Dict[str, Any]) -> str:
    role = item.get("target_role") or "team"
    dispatch_id = item.get("dispatch_id") or "-"
    return "\n".join(
        [
            f"{role} 응답 재시도.",
            "- 지난 open dispatch를 이어서 핵심만 답해라.",
            "- 현재 판단, 실제 리스크, 필요한 요청만 남겨라.",
            "- 자유 형식 또는 kv 허용.",
            "",
            f"dispatch_id: {dispatch_id}",
            f"reason: {item.get('reason', '-')}",
        ]
    )


def _build_interrupt_steering_prompt(
    round_payload: Dict[str, Any],
    steps: List[Dict[str, Any]],
    question: Dict[str, Any],
    evidence: Dict[str, Any],
) -> str:
    return f"""st:interrupt | sc:round {round_payload.get('id') or '-'} urgent steer | rs:q from {question.get('from_role') or '-'} to {','.join(question.get('to_roles') or []) or '-'} | bk:{question.get('status') or 'open'} | rq:none | pr:interrupt | cd:kv | tb:{INTERRUPT_PACKET_BUDGET} | ch:primitive

Context:
- topic: {round_payload.get('topic') or '-'}
- q_intent: {question.get('intent') or '-'}
- q_priority: {question.get('priority') or 'normal'}
- q_interrupt: {bool(question.get('interrupt'))}
- q_hops: {question.get('hop_count') or 0}
- q_unanswered: {question.get('unanswered_count') or 0}
- peer:
{_compact_peer_summary(steps)}
- evidence:
{_format_qa_evidence(evidence)}

Reply in compact packet first. Very short. Primitive words allowed.
Required:
- keep / cut / ask / owner
- risk only if truly blocking
- no essay
"""


def _build_peer_sync_prompt(
    from_role: str,
    to_role: str,
    round_payload: Dict[str, Any],
    steps: List[Dict[str, Any]],
    source_step: Dict[str, Any],
) -> str:
    return f"""너는 {to_role} 역할이다. {from_role} peer packet에 응답한다.

Context:
- parent: {round_payload.get('issue_ref') or '미지정'}
- topic: {round_payload.get('topic') or '-'}
- from_role: {from_role}
- source_stage: {source_step.get('stage') or '-'}
- source_summary: {source_step.get('result') or source_step.get('last_status') or '-'}
- peer:
{_compact_peer_summary(steps)}

Reply:
- 짧게.
- 형식 채우기 금지.
- 동의 / 반박 / 보완 중 하나를 먼저 말해라.
- 진짜 막히는 리스크만 말해라.
- 필요한 액션이 있으면 ask나 owner만 짧게 남겨라.
"""


def _build_gameplay_qa_prompt(round_payload: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    return f"""너는 gameplay_qa 역할이다.

Context:
- parent: {round_payload.get('issue_ref') or '미지정'}
- trigger: {round_payload.get('trigger') or '-'}
- topic: {round_payload.get('topic') or '-'}
- changed_files: {', '.join(round_payload.get('changed_files') or []) or '없음'}
- focus: 실플레이 체감, 재현 절차, 개선 포인트
- evidence:
{_format_qa_evidence(evidence)}

Reply:
- 짧게.
- 좋은 점 2개 이하.
- 플레이를 망치는 문제 3개 이하.
- 재현 절차.
- 다음 라운드 검증 포인트.
- 형식 채우기 금지.
"""


def _build_pm_frame_prompt(round_payload: Dict[str, Any], evidence: Dict[str, Any], steps: List[Dict[str, Any]]) -> str:
    return f"""너는 pm 역할이다. 이번 라운드의 목표와 판단 축을 잠가라.

Context:
- parent: {round_payload.get('issue_ref') or '미지정'}
- topic: {round_payload.get('topic') or '-'}
- changed_files: {', '.join(round_payload.get('changed_files') or []) or '없음'}
- gameplay_qa:
{_compact_peer_summary(steps, roles=('gameplay_qa',))}
- evidence:
{_format_qa_evidence(evidence)}

Reply:
- 짧게.
- 평가 축 3개 이하.
- in / out scope.
- planning/design/dev가 답할 질문.
- 정보 과다보다 플레이 감 우선.
- 형식 채우기 금지.
"""


def _build_role_analysis_prompt(role: str, round_payload: Dict[str, Any], evidence: Dict[str, Any], steps: List[Dict[str, Any]]) -> str:
    role_title = {
        "planning": "기획",
        "design": "디자인",
        "dev": "개발",
    }[role]
    return f"""너는 {role_title} 역할이다.

Context:
- parent: {round_payload.get('issue_ref') or '미지정'}
- topic: {round_payload.get('topic') or '-'}
- pm:
{_compact_peer_summary(steps, roles=('pm',))}
- gameplay_qa:
{_compact_peer_summary(steps, roles=('gameplay_qa',))}
- evidence:
{_format_qa_evidence(evidence)}

Reply:
- 짧게.
- 잘된 점.
- 위험 또는 망가지는 점.
- 바로 적용할 개선안 3개 이하.
- backlog로 미룰 것 2개 이하.
- 동료 역할에 던질 핵심 질문만 남겨라.
"""


def _build_rebuttal_prompt(role: str, round_payload: Dict[str, Any], evidence: Dict[str, Any], steps: List[Dict[str, Any]]) -> str:
    return f"""너는 {role} 역할의 2턴이다. peer summary만 보고 반박 또는 보완만 해라.

Context:
- parent: {round_payload.get('issue_ref') or '미지정'}
- topic: {round_payload.get('topic') or '-'}
- peer:
{_compact_peer_summary(steps)}
- evidence:
{_format_qa_evidence(evidence)}

Reply:
- 매우 짧게.
- 유지할 것.
- 바꿀 것.
- 이번 라운드에서 꼭 잠글 합의 2개 이하.
- pm에 넘길 핵심 ask 한 줄이면 충분하다.
"""


def _build_pm_final_prompt(round_payload: Dict[str, Any], evidence: Dict[str, Any], steps: List[Dict[str, Any]]) -> str:
    return f"""너는 pm 최종 합성 턴이다.

Context:
- parent: {round_payload.get('issue_ref') or '미지정'}
- topic: {round_payload.get('topic') or '-'}
- peer:
{_compact_peer_summary(steps)}
- evidence:
{_format_qa_evidence(evidence)}

Reply:
- 장문 금지.
- 최종 우선순위와 회고를 짧게 정리해라.
- 섹션 제목 쓰지 마라.
- 답변 마지막에는 아래 JSON block을 반드시 포함한다.

```json
{{
  "round_summary": "한 문장 요약",
  "retrospective": "이번 라운드 회고",
  "gameplay_findings": ["체감 finding 1", "체감 finding 2"],
  "backlog_candidates": [
    {{
      "title": "후속 이슈 제목",
      "summary": "왜 필요한지",
      "team_label": "planning",
      "acceptance_criteria": ["조건 1", "조건 2"]
    }}
  ]
}}
```
"""


def _compact_peer_summary(steps: List[Dict[str, Any]], roles: Tuple[str, ...] | None = None) -> str:
    selected = [step for step in steps if roles is None or step.get("role") in roles]
    if not selected:
        return "- 아직 없음"
    lines = []
    for step in selected[-8:]:
        lines.append(
            f"- {step.get('role')}[{step.get('stage')}]: {step.get('result') or step.get('last_status') or '-'}"
        )
        blocker = step.get("blocker", "")
        if blocker and blocker != "없음":
            lines.append(f"  risk: {blocker}")
        next_request = step.get("next_request", "")
        if next_request and next_request != "없음":
            lines.append(f"  ask: {next_request}")
    return "\n".join(lines)


def _format_qa_evidence(evidence: Dict[str, Any]) -> str:
    if not evidence.get("ok"):
        return "자동 플레이 실패: " + (evidence.get("stderr") or "원인 미상")
    payload = evidence.get("render_payload") or {}
    parts = [
        f"cameraMode={payload.get('cameraMode', '-')}",
        f"state={payload.get('sessionState', '-')}",
    ]
    current = payload.get("currentShot") or {}
    if current:
        parts.append(
            f"currentShot carry={current.get('carry_m', '-')}, total={current.get('total_m', '-')}, offline={current.get('offline_m', '-')}"
        )
    recent = payload.get("recentShots") or []
    parts.append(f"recentShots={len(recent)}")
    live = payload.get("liveFlight") or {}
    if live:
        parts.append(
            f"live distance={live.get('distanceMeters', '-')}, curve={live.get('curveMeters', '-')}"
        )
    return "\n".join(f"- {part}" for part in parts)


def _parse_harness_final_json(raw: str) -> Dict[str, Any]:
    match = re.search(r"```json\s*([\s\S]*?)\s*```", raw)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _fallback_gameplay_findings(steps: List[Dict[str, Any]]) -> List[str]:
    findings = []
    for step in steps:
        if step.get("role") == "gameplay_qa" and step.get("result"):
            findings.append(step["result"])
    return findings[:3]


def _write_round_artifacts(round_payload: Dict[str, Any], evidence: Dict[str, Any]) -> Tuple[Path, Path]:
    review_path = reviews_dir(REPO_ROOT) / f"{round_payload['id']}.md"
    backlog_path = backlog_drafts_dir(REPO_ROOT) / f"{round_payload['id']}.json"
    review_lines = [
        f"# {round_payload['id']}",
        "",
        f"- Parent: {round_payload.get('issue_ref') or '미지정'}",
        f"- Trigger: {round_payload.get('trigger') or '-'}",
        f"- Topic: {round_payload.get('topic') or '-'}",
        "",
        "## Round Summary",
        round_payload.get("summary") or "-",
        "",
        "## Retrospective",
        round_payload.get("retrospective") or "-",
        "",
        "## Gameplay Findings",
    ]
    for finding in round_payload.get("gameplay_findings") or []:
        review_lines.append(f"- {finding}")
    review_lines.extend(["", "## Issue Draft Results"])
    for item in round_payload.get("issue_draft_results") or []:
        status_line = f"- [{item.get('status', 'unknown')}] {item.get('title', '-')}"
        if item.get("url"):
            status_line += f" {item['url']}"
        if item.get("error"):
            status_line += f" ({item['error']})"
        review_lines.append(status_line)
    review_lines.extend(["", "## QA Evidence", _format_qa_evidence(evidence), "", "## Steps"])
    for step in round_payload.get("steps") or []:
        review_lines.append(
            f"- {step.get('stage')}: {step.get('role')} / {step.get('result') or step.get('last_status') or '-'}"
        )
    review_path.write_text("\n".join(review_lines) + "\n")
    save_json(backlog_path, round_payload.get("backlog_candidates") or [])
    return review_path, backlog_path


def _create_issue_drafts(round_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    issue_ref = (round_payload.get("issue_ref") or "").strip()
    for candidate in round_payload.get("backlog_candidates") or []:
        title = candidate.get("title") or "후속 작업"
        team_label = candidate.get("team_label") or "team"
        if not issue_ref:
            results.append(
                {
                    "title": title,
                    "status": "skipped",
                    "error": "parent issue missing",
                    "team_label": team_label,
                }
            )
            continue
        body_lines = [
            f"Parent: {issue_ref}",
            "",
            candidate.get("summary") or "",
            "",
            "Acceptance Criteria:",
        ]
        for criterion in candidate.get("acceptance_criteria") or []:
            body_lines.append(f"- {criterion}")
        command = [
            "gh",
            "issue",
            "create",
            "--title",
            f"[Draft][Harness] {title}",
            "--body",
            "\n".join(body_lines),
            "--label",
            "draft",
            "--label",
            "harness-generated",
            "--label",
            team_label.replace("_", "-"),
        ]
        proc = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode == 0:
            results.append(
                {
                    "title": title,
                    "status": "created",
                    "url": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "",
                    "team_label": team_label,
                }
            )
        else:
            results.append(
                {
                    "title": title,
                    "status": "error",
                    "error": (proc.stderr or proc.stdout).strip() or "gh issue create 실패",
                    "team_label": team_label,
                }
            )
    return results


def _log_round_event(status: str, round_payload: Dict[str, Any], details: List[str]) -> None:
    append_jsonl(
        ROUND_LOG_PATH,
        {
            "event_type": "round",
            "status": "block" if status == "failed" else ("warn" if status == "pending" else "ok"),
            "summary": f"{round_payload.get('id')} {status}",
            "details": details,
            "timestamp": _now(),
            "round_id": round_payload.get("id"),
            "round_status": status,
        },
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
