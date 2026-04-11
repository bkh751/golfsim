from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .checks import (
    collect_changed_files,
    derive_round_topic,
    run_selected_checks,
    select_checks,
    should_trigger_roundtable,
)
from .classify import classify_prompt
from .orchestrator_state import ROLES, has_blocker, summarize_orchestrator
from .rounds import create_round_request, load_worker_status, summarize_rounds

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = REPO_ROOT / ".codex" / "harness"
LOG_DIR = HARNESS_DIR / "logs"

LAST_FILES = {
    "context": HARNESS_DIR / "last-context.json",
    "intake": HARNESS_DIR / "last-intake.json",
    "orchestrator": HARNESS_DIR / "last-orchestrator-hint.json",
    "check": HARNESS_DIR / "last-check.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="golfsim Codex hook runner")
    parser.add_argument(
        "hook",
        choices=("context_guard", "intake_guard", "orchestrator_hint", "check_guard"),
    )
    parser.add_argument("--mode", choices=("contract", "codex"), default="contract")
    parser.add_argument("--phase", choices=("advisory", "blocking"), default="advisory")
    args = parser.parse_args()

    payload = _read_payload()
    result = run_hook(args.hook, args.phase, payload)
    _persist_result(result)

    if args.mode == "contract":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["status"] == "block" else 0

    codex_output = to_codex_output(result, payload)
    if codex_output:
        print(json.dumps(codex_output, ensure_ascii=False))
    return 0


def run_hook(hook: str, phase: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if hook == "context_guard":
        return run_context_guard(payload, phase)
    if hook == "intake_guard":
        return run_intake_guard(payload, phase)
    if hook == "orchestrator_hint":
        return run_orchestrator_hint(payload, phase)
    return run_check_guard(payload, phase)


def run_context_guard(payload: Dict[str, Any], phase: str) -> Dict[str, Any]:
    threshold = 15.0
    usage_percent, source = _extract_context_usage_percent(payload)
    event_name = payload.get("hook_event_name") or payload.get("hookEventName") or "UserPromptSubmit"
    details = [f"임계값: {threshold:.1f}%"]
    if source:
        details.append(f"감지 경로: {source}")

    if usage_percent is None:
        details.append("컨텍스트 사용량 필드를 찾지 못함")
        return _result(
            kind="context",
            status="ok",
            summary="컨텍스트 사용량 정보 없음",
            details=details,
            next_action="payload에 컨텍스트 사용량 필드가 들어오면 자동 차단이 동작한다.",
            phase=phase,
            extra={
                "context_usage_percent": None,
                "context_threshold_percent": threshold,
                "context_detected": False,
                "context_source": "",
                "session_id": _extract_session_id(payload),
                "hook_event_name": event_name,
            },
        )

    details.append(f"컨텍스트 사용량: {usage_percent:.1f}%")
    status = "ok"
    summary = "컨텍스트 사용량 임계값 이내"
    next_action = "현재 세션을 계속 진행한다."
    if usage_percent >= threshold:
        status = "block"
        summary = f"세션 컨텍스트 {usage_percent:.1f}%로 임계값 {threshold:.1f}% 초과"
        next_action = "즉시 새 세션으로 전환하거나 짧은 요약만 남기고 다시 시작한다."

    return _result(
        kind="context",
        status=status,
        summary=summary,
        details=details,
        next_action=next_action,
        phase=phase,
        extra={
            "context_usage_percent": usage_percent,
            "context_threshold_percent": threshold,
            "context_detected": True,
            "context_source": source,
            "session_id": _extract_session_id(payload),
            "hook_event_name": event_name,
        },
    )


def run_intake_guard(payload: Dict[str, Any], phase: str) -> Dict[str, Any]:
    prompt = payload.get("prompt", "")
    classified = classify_prompt(prompt)
    details = [
        f"Issue: {', '.join(classified['issues']) or '없음'}",
        f"역할 키워드: {', '.join(classified['mentioned_roles']) or '없음'}",
    ]
    if classified["generic_keywords"]:
        details.append(f"일반 팀 키워드: {', '.join(classified['generic_keywords'])}")
    if classified["meta_keywords"]:
        details.append(f"메타 키워드: {', '.join(classified['meta_keywords'])}")
    if classified["orchestration_verbs"]:
        details.append(f"실행 의도: {', '.join(classified['orchestration_verbs'])}")

    if classified["session_mode"] == "meta_harness":
        summary = "하네스 메타 세션으로 분류됨"
        next_action = "메타파일, 대시보드, 훅, 프로토콜 작업을 현재 세션에서 계속한다."
        status = "ok"
    elif classified["orchestrator_candidate"]:
        summary = f"{', '.join(classified['issues'])} 기준 오케스트레이션 후보 감지"
        next_action = "메인 세션에서 관련 역할을 확인하고 오케스트레이터 사용 여부를 판단한다."
        status = "warn"
    elif classified["needs_parent_issue"]:
        summary = "팀 조율 요청이지만 대표 Issue 식별자가 없다"
        next_action = "대표 또는 하위 Issue 번호를 먼저 명시한 뒤 오케스트레이션 여부를 다시 판단한다."
        status = "warn"
    else:
        summary = "단일 작업 입력으로 분류됨"
        next_action = "현재 세션에서 범위 내 구현 또는 분석을 계속한다."
        status = "ok"

    return _result(
        kind="intake",
        status=status,
        summary=summary,
        details=details,
        next_action=next_action,
        phase=phase,
        extra={
            "classification": classified,
            "session_mode": classified.get("session_mode", "single"),
            "session_id": _extract_session_id(payload),
            "hook_event_name": payload.get("hook_event_name") or payload.get("hookEventName"),
        },
    )


def run_orchestrator_hint(payload: Dict[str, Any], phase: str) -> Dict[str, Any]:
    prompt = payload.get("prompt", "")
    classified = classify_prompt(prompt) if prompt else {
        "issues": [],
        "mentioned_roles": [],
        "generic_keywords": [],
        "meta_keywords": [],
        "orchestration_verbs": [],
        "suppression_keywords": [],
        "execution_intent": False,
        "session_mode": "single",
        "meta_harness": False,
        "orchestrator_candidate": False,
        "needs_parent_issue": False,
        "should_run_orchestrator_hint": False,
        "recommended_roles": list(ROLES),
    }
    summary = summarize_orchestrator(REPO_ROOT)
    rounds = summarize_rounds(REPO_ROOT)
    worker = load_worker_status(REPO_ROOT)
    target_roles = classified.get("recommended_roles") or list(ROLES)
    unbound = [role for role in target_roles if role in summary["unbound_roles"]]
    stale = [role for role in target_roles if role in summary["stale_roles"]]
    parse_error = [role for role in target_roles if role in summary["parse_error_roles"]]
    blockers = [role for role in target_roles if role in summary["blocking_roles"]]

    details = [
        f"추천 역할: {', '.join(target_roles) or '없음'}",
        f"targets bound: {'예' if summary['targets_bound'] else '아니오'}",
    ]
    if worker:
        details.append(f"worker 상태: {worker.get('state', 'unknown')}")
    if rounds["counts"]["pending"] or rounds["counts"]["running"]:
        details.append(
            "round 상태: "
            + ", ".join(
                [
                    f"pending {rounds['counts']['pending']}",
                    f"running {rounds['counts']['running']}",
                ]
            )
        )
    if unbound:
        details.append(f"bind 필요: {', '.join(unbound)}")
    if stale:
        details.append(f"stale role: {', '.join(stale)}")
    if parse_error:
        details.append(f"parse_error role: {', '.join(parse_error)}")
    if blockers:
        details.append(f"blocker role: {', '.join(blockers)}")

    if classified.get("session_mode") == "meta_harness":
        return _result(
            kind="orchestrator",
            status="ok",
            summary="메타 하네스 세션에서는 오케스트레이터 경고를 억제함",
            details=details,
            next_action="현재 세션에서 메타 프로토콜과 대시보드 작업을 계속한다.",
            phase=phase,
            extra={"classification": classified, "orchestrator": summary, "session_mode": "meta_harness"},
        )

    if classified.get("needs_parent_issue"):
        return _result(
            kind="orchestrator",
            status="warn",
            summary="대표 Issue가 없어 오케스트레이션 후보를 잠글 수 없다",
            details=details,
            next_action="대표 또는 하위 Issue 번호를 먼저 지정한다.",
            phase=phase,
            extra={"classification": classified, "orchestrator": summary},
        )

    if not classified.get("should_run_orchestrator_hint") and payload.get("hook_event_name") == "UserPromptSubmit":
        return _result(
            kind="orchestrator",
            status="ok",
            summary="오케스트레이션 후보 아님",
            details=details,
            next_action="현재 세션에서 작업을 계속한다.",
            phase=phase,
            extra={"classification": classified, "orchestrator": summary},
        )

    status = "ok"
    headline = "오케스트레이터 사용 가능"
    next_action = "메인 세션에서 필요한 역할만 선택해 dispatch 여부를 결정한다."
    if unbound:
        status = "warn"
        headline = "오케스트레이터 targets 바인딩 확인 필요"
        next_action = "먼저 bind_targets로 누락된 역할 바인딩을 맞춘다."
    elif stale:
        status = "warn"
        headline = "오케스트레이터 상태가 오래됨"
        next_action = f"{', '.join(stale)} 역할을 우선 다시 sync할지 판단한다."
    elif parse_error:
        status = "warn"
        headline = "일부 팀 응답 파싱 오류"
        next_action = f"{', '.join(parse_error)} 역할 응답 형식을 다시 점검한다."
    elif blockers:
        status = "warn"
        headline = "일부 팀에 blocker 존재"
        next_action = f"{', '.join(blockers)} 역할의 blocker를 먼저 해소한다."
    elif rounds["counts"]["pending"] and worker.get("state") not in {"running", "polling"}:
        status = "warn"
        headline = "pending round가 있지만 worker가 비활성 상태"
        next_action = "harness worker를 실행하거나 pending round를 정리한다."

    return _result(
        kind="orchestrator",
        status=status,
        summary=headline,
        details=details,
        next_action=next_action,
        phase=phase,
        extra={
            "classification": classified,
            "orchestrator": summary,
            "worker": worker,
            "rounds": rounds,
        },
    )


def run_check_guard(payload: Dict[str, Any], phase: str) -> Dict[str, Any]:
    changed_files = collect_changed_files(REPO_ROOT)
    selected = select_checks(changed_files)
    details = [f"변경 파일 수: {len(changed_files)}"]
    if changed_files:
        details.append(f"변경 파일: {', '.join(changed_files[:12])}" + (" ..." if len(changed_files) > 12 else ""))
    if not selected:
        return _result(
            kind="check",
            status="ok",
            summary="검증 대상 변경 파일 없음",
            details=details,
            next_action="추가 검증 없이 현재 흐름을 계속한다.",
            phase=phase,
            extra={"changed_files": changed_files, "checks": []},
        )

    results = run_selected_checks(REPO_ROOT, selected)
    failures = [result for result in results if not result["ok"]]
    for result in results:
        state = "ok" if result["ok"] else "fail"
        details.append(f"[{state}] {result['label']}")
        if result["stderr"]:
            details.append(result["stderr"])

    round_request = None
    if failures and phase == "blocking":
        summary = "최소 검증 실패로 완료를 차단함"
        next_action = failures[0]["label"] + " 실패 원인을 먼저 해소한다."
        status = "block"
    elif failures:
        summary = "최소 검증 실패"
        next_action = failures[0]["label"] + " 실패 원인을 먼저 확인한다."
        status = "warn"
    else:
        summary = "선택된 최소 검증 통과"
        next_action = "현재 변경 범위 기준으로 다음 작업을 계속한다."
        status = "ok"
        if phase == "blocking" and should_trigger_roundtable(changed_files):
            issue_ref = _last_issue_ref()
            session_id = _extract_session_id(payload)
            round_payload, dedupe_hit = create_round_request(
                REPO_ROOT,
                issue_ref=issue_ref,
                trigger="stop_hook",
                changed_files=changed_files,
                topic=derive_round_topic(changed_files),
                session_id=session_id,
                source="hook",
            )
            round_request = {
                "round_id": round_payload["id"],
                "dedupe_hit": dedupe_hit,
                "issue_ref": issue_ref,
            }
            details.append(
                f"[ok] round enqueue {'중복 생략' if dedupe_hit else '등록'}: {round_payload['id']}"
            )

    return _result(
        kind="check",
        status=status,
        summary=summary,
        details=details,
        next_action=next_action,
        phase=phase,
        extra={
            "changed_files": changed_files,
            "checks": results,
            "round_request": round_request,
        },
    )


def to_codex_output(result: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    event_name = payload.get("hook_event_name") or payload.get("hookEventName") or "UserPromptSubmit"
    if result["status"] == "block":
        return {
            "decision": "block",
            "reason": result["summary"],
        }
    if event_name == "Stop":
        return {}

    return {}


def _build_additional_context(result: Dict[str, Any]) -> str | None:
    if result["status"] == "ok":
        return None
    lines = [result["summary"]]
    if result["next_action"]:
        lines.append("다음: " + result["next_action"])
    first_detail = next((detail for detail in result["details"] if detail), None)
    if first_detail:
        lines.append("근거: " + first_detail)
    return "\n".join(lines)


def _persist_result(result: Dict[str, Any]) -> None:
    HARNESS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    last_path = LAST_FILES[result["kind"]]
    last_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    log_path = LOG_DIR / f"{result['kind']}.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + "\n")


def _result(
    *,
    kind: str,
    status: str,
    summary: str,
    details: list[str],
    next_action: str,
    phase: str,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "kind": kind,
        "status": status,
        "summary": summary,
        "details": details,
        "next_action": next_action,
        "phase": phase,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


def _read_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def _extract_context_usage_percent(payload: Dict[str, Any]) -> tuple[float | None, str]:
    for path, value in _walk_payload(payload):
        if not path:
            continue
        key = path[-1]
        normalized = _normalize_key(key)
        if _looks_like_context_percent_key(normalized):
            percent = _coerce_percent(value)
            if percent is not None:
                return percent, ".".join(path)
        if _looks_like_context_ratio_key(normalized):
            percent = _coerce_ratio_as_percent(value)
            if percent is not None:
                return percent, ".".join(path)

    for path, value in _walk_payload(payload):
        if not isinstance(value, dict):
            continue
        percent = _percent_from_usage_dict(path, value)
        if percent is not None:
            return percent, ".".join(path)

    return None, ""


def _walk_payload(node: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    items: list[tuple[tuple[str, ...], Any]] = [(path, node)]
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                items.extend(_walk_payload(value, path + (key,)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            items.extend(_walk_payload(value, path + (str(index),)))
    return items


def _percent_from_usage_dict(path: tuple[str, ...], value: Dict[str, Any]) -> float | None:
    joined = ".".join(path)
    normalized_path = _normalize_key(joined)
    normalized_keys = {_normalize_key(key): key for key in value.keys() if isinstance(key, str)}
    if not any(token in normalized_path for token in ("context", "window", "usage", "token")):
        if "context" not in normalized_keys and "window" not in normalized_keys:
            return None

    for used_key, total_key in (
        ("used", "total"),
        ("current", "max"),
        ("consumed", "limit"),
        ("usedtokens", "maxtokens"),
        ("inputtokens", "maxinputtokens"),
    ):
        if used_key in normalized_keys and total_key in normalized_keys:
            used = _coerce_number(value[normalized_keys[used_key]])
            total = _coerce_number(value[normalized_keys[total_key]])
            if used is None or total is None or total <= 0:
                return None
            return round((used / total) * 100.0, 2)
    return None


def _looks_like_context_percent_key(normalized: str) -> bool:
    return (
        "percent" in normalized or normalized.endswith("pct")
    ) and any(token in normalized for token in ("context", "usage", "window"))


def _looks_like_context_ratio_key(normalized: str) -> bool:
    return "ratio" in normalized and any(token in normalized for token in ("context", "usage", "window"))


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().rstrip("%")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _coerce_percent(value: Any) -> float | None:
    number = _coerce_number(value)
    if number is None:
        return None
    if 0.0 <= number <= 1.0:
        number *= 100.0
    if 0.0 <= number <= 100.0:
        return round(number, 2)
    return None


def _coerce_ratio_as_percent(value: Any) -> float | None:
    number = _coerce_number(value)
    if number is None:
        return None
    if 0.0 <= number <= 1.0:
        return round(number * 100.0, 2)
    return None


def _extract_session_id(payload: Dict[str, Any]) -> str:
    for key in ("session_id", "sessionId", "thread_id", "threadId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _last_issue_ref() -> str:
    payload = LAST_FILES["intake"]
    if not payload.exists():
        return ""
    try:
        data = json.loads(payload.read_text())
    except json.JSONDecodeError:
        return ""
    classification = data.get("classification") if isinstance(data, dict) else None
    if not isinstance(classification, dict):
        return ""
    issues = classification.get("issues")
    if isinstance(issues, list) and issues:
        value = issues[0]
        if isinstance(value, str):
            return value
    return ""
