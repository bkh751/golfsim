from __future__ import annotations

import re
from typing import Dict, List

ROLES = ("pm", "planning", "design", "dev", "gameplay_qa")

ISSUE_PATTERNS = (
    re.compile(r"#(\d+)"),
    re.compile(r"(\d+)번\s*이슈"),
    re.compile(r"\bissue\s+(\d+)\b", re.IGNORECASE),
)

ROLE_PATTERNS = {
    "pm": (re.compile(r"\bpm\b", re.IGNORECASE),),
    "planning": (re.compile(r"기획"), re.compile(r"\bplanning\b", re.IGNORECASE)),
    "design": (re.compile(r"디자인"), re.compile(r"\bdesign\b", re.IGNORECASE)),
    "dev": (
        re.compile(r"개발"),
        re.compile(r"\bdev\b", re.IGNORECASE),
        re.compile(r"\bdevelopment\b", re.IGNORECASE),
    ),
    "gameplay_qa": (
        re.compile(r"게임플레이\s*qa", re.IGNORECASE),
        re.compile(r"게임\s*qa", re.IGNORECASE),
        re.compile(r"\bgameplay[_ -]?qa\b", re.IGNORECASE),
        re.compile(r"\bqa\b", re.IGNORECASE),
        re.compile(r"플레이\s*테스트"),
    ),
}

GENERIC_TEAM_PATTERNS = (
    re.compile(r"팀"),
    re.compile(r"세션"),
    re.compile(r"오케스트레이션"),
    re.compile(r"\borchestration\b", re.IGNORECASE),
)

META_HARNESS_PATTERNS = (
    re.compile(r"AGENTS", re.IGNORECASE),
    re.compile(r"rules?", re.IGNORECASE),
    re.compile(r"harness", re.IGNORECASE),
    re.compile(r"3d", re.IGNORECASE),
    re.compile(r"blender", re.IGNORECASE),
    re.compile(r"gltf", re.IGNORECASE),
    re.compile(r"glb", re.IGNORECASE),
    re.compile(r"asset\s+pipeline", re.IGNORECASE),
    re.compile(r"dashboard", re.IGNORECASE),
    re.compile(r"history", re.IGNORECASE),
    re.compile(r"hook", re.IGNORECASE),
    re.compile(r"protocol", re.IGNORECASE),
    re.compile(r"steering", re.IGNORECASE),
    re.compile(r"peer", re.IGNORECASE),
    re.compile(r"router", re.IGNORECASE),
    re.compile(r"mesh", re.IGNORECASE),
    re.compile(r"conversation", re.IGNORECASE),
    re.compile(r"메타"),
    re.compile(r"대시보드"),
    re.compile(r"히스토리"),
    re.compile(r"규칙"),
    re.compile(r"프로토콜"),
    re.compile(r"하네스"),
    re.compile(r"3D"),
    re.compile(r"모델링"),
    re.compile(r"자산\s*파이프라인"),
    re.compile(r"환경\s*아트"),
    re.compile(r"장비\s*모델링"),
    re.compile(r"equipment", re.IGNORECASE),
    re.compile(r"훅"),
)

ORCHESTRATION_INTENT_PATTERNS = (
    re.compile(r"조율"),
    re.compile(r"dispatch", re.IGNORECASE),
    re.compile(r"bind", re.IGNORECASE),
    re.compile(r"roundtable", re.IGNORECASE),
    re.compile(r"broadcast", re.IGNORECASE),
    re.compile(r"보내"),
    re.compile(r"돌려"),
    re.compile(r"연결"),
    re.compile(r"대화시켜"),
)

SUPPRESS_ORCHESTRATION_PATTERNS = (
    re.compile(r"설명"),
    re.compile(r"분석"),
    re.compile(r"비교"),
    re.compile(r"가이드"),
    re.compile(r"컨설팅"),
    re.compile(r"상담"),
)


def classify_prompt(prompt: str) -> Dict[str, object]:
    prompt = prompt or ""
    issues = _extract_issues(prompt)
    mentioned_roles = [role for role in ROLES if _matches_any(prompt, ROLE_PATTERNS[role])]
    generic_hits = [pat.pattern for pat in GENERIC_TEAM_PATTERNS if pat.search(prompt)]
    meta_hits = [pat.pattern for pat in META_HARNESS_PATTERNS if pat.search(prompt)]
    orchestration_verbs = [pat.pattern for pat in ORCHESTRATION_INTENT_PATTERNS if pat.search(prompt)]
    suppress_hits = [pat.pattern for pat in SUPPRESS_ORCHESTRATION_PATTERNS if pat.search(prompt)]
    team_keyword_hit = bool(mentioned_roles or generic_hits)
    meta_harness = bool(meta_hits) and not orchestration_verbs
    execution_intent = bool(orchestration_verbs) and not suppress_hits
    orchestrator_candidate = bool(issues and team_keyword_hit and execution_intent)
    needs_parent_issue = bool(team_keyword_hit and execution_intent and not issues)
    session_mode = "single"
    if meta_harness:
        session_mode = "meta_harness"
    elif team_keyword_hit and execution_intent:
        session_mode = "orchestration"
    recommended_roles = mentioned_roles or (list(ROLES) if session_mode == "orchestration" else [])
    return {
        "issues": issues,
        "mentioned_roles": mentioned_roles,
        "generic_keywords": generic_hits,
        "meta_keywords": meta_hits,
        "orchestration_verbs": orchestration_verbs,
        "suppression_keywords": suppress_hits,
        "team_keyword_hit": team_keyword_hit,
        "execution_intent": execution_intent,
        "session_mode": session_mode,
        "meta_harness": meta_harness,
        "orchestrator_candidate": orchestrator_candidate,
        "needs_parent_issue": needs_parent_issue,
        "recommended_roles": recommended_roles,
        "task_kind": session_mode if session_mode != "single" else "single",
        "should_run_orchestrator_hint": session_mode == "orchestration",
    }


def _extract_issues(prompt: str) -> List[str]:
    found = []
    for pattern in ISSUE_PATTERNS:
        found.extend(match.group(1) for match in pattern.finditer(prompt))
    unique = sorted({f"#{value}" for value in found}, key=lambda item: int(item[1:]))
    return unique


def _matches_any(prompt: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(prompt) for pattern in patterns)
