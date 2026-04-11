from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REFERENCE_REPO_URL = "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill"
REFERENCE_REPO_NAME = "ui-ux-pro-max-skill"


UIUX_ITERATION_SPECS: List[Dict[str, Any]] = [
    {
        "iteration": 1,
        "layer": "abstract",
        "title": "운영자 미션 스트립과 핵심 과업 3개 고정",
        "topic": "운영 사용자의 핵심 과업과 mental model을 정의한다.",
        "tab_target": "overview",
        "screen_target": "overview-hero",
        "trigger_state": "dashboard_load",
        "reference_keys": ["dashboard_pattern", "visual_style", "anti_patterns"],
        "allow_rebuttal": False,
        "default_problem": "현재 오버뷰는 상태 지표는 보여주지만 이 화면이 운영자에게 무엇을 판단시키는지 한 줄로 잠겨 있지 않아 각 탭의 목적이 흐린다.",
        "default_proposal": "오버뷰 상단에 운영자 미션 스트립을 고정하고, 이 화면에서 즉시 해야 하는 핵심 과업 3개를 명시해 이후 탭과 카드가 모두 같은 판단 축을 따르게 한다.",
        "default_anti_patterns": [
            "목적 없는 요약 숫자 나열",
            "운영 판단과 기록 열람을 같은 계층에 혼합",
        ],
        "default_acceptance_hint": "오버뷰 첫 화면만 보고도 운영자가 이 화면의 1차 목적과 즉시 수행할 과업 3개를 5초 안에 말할 수 있어야 한다.",
        "default_priority": "immediate",
        "default_status": "priority",
        "default_owner": "pm",
    },
    {
        "iteration": 2,
        "layer": "navigation",
        "title": "탭 정보구조를 운영 과업 기준으로 재분류",
        "topic": "현재 탭 구조를 재분류한다.",
        "tab_target": "overview",
        "screen_target": "workspace-tabs",
        "trigger_state": "workspace_tab_render",
        "reference_keys": ["dashboard_pattern", "anti_patterns", "checklist"],
        "allow_rebuttal": True,
        "default_problem": "현재 탭은 데이터 출처 기준으로 나뉘어 있어 운영자의 과업 흐름과 직접 맞지 않고, 오버뷰/작업 개선/근거 탭 간 의미 중첩이 있다.",
        "default_proposal": "탭 레이블 아래에 과업 설명을 짧게 붙이고, 오버뷰는 판단·작업 개선은 실행·근거/초안은 검증이라는 3개 운영 축으로 재정렬한다.",
        "default_anti_patterns": [
            "탭 이름만 있고 행동 목적이 없음",
            "같은 카드가 여러 탭에서 중복 노출됨",
        ],
        "default_acceptance_hint": "각 탭은 '왜 들어가는지'를 설명하는 한 줄 설명을 가지며, 동일 정보가 기본 화면에서 두 탭 이상 반복 노출되지 않아야 한다.",
        "default_priority": "immediate",
        "default_status": "priority",
        "default_owner": "planning",
    },
    {
        "iteration": 3,
        "layer": "abstract",
        "title": "추상화 탭 후보와 게이트 조건 정의",
        "topic": "추상화 탭 필요성을 평가한다.",
        "tab_target": "abstract",
        "screen_target": "abstract-tab-candidate",
        "trigger_state": "cross_tab_synthesis_needed",
        "reference_keys": ["dashboard_pattern", "anti_patterns", "visual_style"],
        "allow_rebuttal": True,
        "default_problem": "오버뷰보다 더 높은 수준의 종합 판단층이 필요한지 불명확해서 추상화 탭이 실제 가치인지, 중복인지만 반복 논쟁된다.",
        "default_proposal": "추상화 탭은 고유 정보층, 고유 행동 목적, 낮은 오버뷰 중복도라는 3개 게이트를 모두 통과할 때만 후보로 남기고, 그렇지 않으면 follow-up issue로 내린다.",
        "default_anti_patterns": [
            "오버뷰의 다른 이름인 탭 추가",
            "행동 없이 해석만 늘리는 상위 요약 레이어",
        ],
        "default_acceptance_hint": "추상화 탭 후보는 고유 정보층·고유 행동 목적·오버뷰 중복도 낮음 3개 평가 결과를 함께 가진다.",
        "default_priority": "follow-up",
        "default_status": "follow-up",
        "default_owner": "pm",
    },
    {
        "iteration": 4,
        "layer": "navigation",
        "title": "상태 변화 기반 탭 강조 규칙",
        "topic": "글로벌 탭 전환 규칙을 정한다.",
        "tab_target": "overview",
        "screen_target": "workspace-shell",
        "trigger_state": "state_shift_detected",
        "reference_keys": ["dashboard_pattern", "motion_rules", "anti_patterns"],
        "allow_rebuttal": True,
        "default_problem": "상태가 바뀌어도 운영자가 다음에 어느 탭을 봐야 하는지 시스템이 안내하지 않아, 경고와 카드가 늘어날수록 탐색 비용이 커진다.",
        "default_proposal": "상태 전이를 감지하면 관련 탭만 강조 배지와 보조 카피로 띄우고, 자동 탭 전환은 하지 않되 '지금 볼 탭' 힌트를 일관되게 제공한다.",
        "default_anti_patterns": [
            "상태 변화 때 탭 자동 점프",
            "모든 탭을 동시에 같은 강도로 강조",
        ],
        "default_acceptance_hint": "warn/block/repair/follow-up 상태마다 추천 탭이 하나로 수렴하고, 자동 강제 전환 없이도 다음 위치를 명확히 가리켜야 한다.",
        "default_priority": "immediate",
        "default_status": "priority",
        "default_owner": "planning",
    },
    {
        "iteration": 5,
        "layer": "state",
        "title": "운영 상태 taxonomy와 카드 톤 계약",
        "topic": "상태 변화 taxonomy를 정한다.",
        "tab_target": "overview",
        "screen_target": "priority-cards",
        "trigger_state": "new_signal_classified",
        "reference_keys": ["visual_style", "color_rules", "anti_patterns"],
        "allow_rebuttal": False,
        "default_problem": "warn, block, active, follow-up이 섞여 카드 톤이 임시로만 적용되어 있어 운영자가 상태의 심각도와 처리 성격을 즉시 구분하기 어렵다.",
        "default_proposal": "info / warn / block / active / settled / follow-up 6단 taxonomy를 정의하고, 카드 배경·테두리·배지 톤을 상태 의미와 1:1로 고정한다.",
        "default_anti_patterns": [
            "심각도와 작업 성격이 같은 색으로 표현됨",
            "배지가 톤만 있고 설명이 없음",
        ],
        "default_acceptance_hint": "동일 상태는 어느 탭에서나 같은 톤과 배지 표현을 사용하고, follow-up과 block은 시각적으로 혼동되지 않아야 한다.",
        "default_priority": "immediate",
        "default_status": "priority",
        "default_owner": "design",
    },
    {
        "iteration": 6,
        "layer": "card",
        "title": "summary / priority / synthesis 카드 계층 분리",
        "topic": "summary/priority/synthesis 카드의 계층을 재정의한다.",
        "tab_target": "overview",
        "screen_target": "overview-card-stack",
        "trigger_state": "overview_render",
        "reference_keys": ["dashboard_pattern", "chart_style", "anti_patterns"],
        "allow_rebuttal": False,
        "default_problem": "현재 overview 카드들은 판단, 관측, 기록이 섞여 있어 요약 카드가 많아질수록 어떤 것이 지금의 결론인지 읽기 어렵다.",
        "default_proposal": "summary는 현재 상태, priority는 즉시 행동, synthesis는 해석과 회고로 역할을 분리하고 각 카드 그룹의 제목과 데이터 밀도를 다르게 설정한다.",
        "default_anti_patterns": [
            "현재 판단과 과거 회고를 같은 카드 크기로 배치",
            "요약 카드가 모두 같은 시각적 무게를 가짐",
        ],
        "default_acceptance_hint": "overview 카드만 봐도 '지금 상태 / 지금 액션 / 왜 그런가'의 순서를 혼동 없이 읽을 수 있어야 한다.",
        "default_priority": "next",
        "default_status": "candidate",
        "default_owner": "planning",
    },
    {
        "iteration": 7,
        "layer": "card",
        "title": "확정 카드 contract와 상태 배지 고정",
        "topic": "확정 카드 패턴을 설계한다.",
        "tab_target": "improvements",
        "screen_target": "design-backlog-cards",
        "trigger_state": "item_confirmed",
        "reference_keys": ["visual_style", "checklist", "anti_patterns"],
        "allow_rebuttal": True,
        "default_problem": "approved, follow-up, blocked, dismissed 같은 결정 상태가 카드 수준에서 일관되게 구분되지 않아 backlog와 queue의 처리 결과를 추적하기 어렵다.",
        "default_proposal": "확정 카드에 상태 바, 배지, 이유, acceptance hint, owner를 고정 슬롯으로 두고, 결정 상태마다 시각 톤과 메타 행을 표준화한다.",
        "default_anti_patterns": [
            "상태만 있고 결정 이유가 없음",
            "카드 확정 후 메타데이터가 사라짐",
        ],
        "default_acceptance_hint": "결정 상태가 다른 카드 두 장은 색, 메타, 행동 가능 여부에서 즉시 구분돼야 하며, acceptance hint가 항상 노출돼야 한다.",
        "default_priority": "next",
        "default_status": "candidate",
        "default_owner": "design",
    },
    {
        "iteration": 8,
        "layer": "interaction",
        "title": "라우팅 그래프와 window turns 5초 이해성 개선",
        "topic": "라우팅 그래프와 window turns의 읽힘을 재설계한다.",
        "tab_target": "rounds",
        "screen_target": "routing-graph-and-turns",
        "trigger_state": "routing_window_changed",
        "reference_keys": ["dashboard_pattern", "chart_style", "anti_patterns"],
        "allow_rebuttal": True,
        "default_problem": "현재 라우팅 영역은 시각 정보는 풍부하지만 운영자가 '누가 왜 누구와 대화했는가'를 5초 안에 파악하기 어렵다.",
        "default_proposal": "라우팅 그래프는 사건 이유를 edge label로 축약하고, window turns는 prompt/message preview와 outcome을 한 카드 안에서 요약해 원인-결과를 한 번에 보여준다.",
        "default_anti_patterns": [
            "그래프와 턴 카드가 서로 다른 서사를 말함",
            "이벤트 이유 없이 source/target만 반복",
        ],
        "default_acceptance_hint": "운영자는 window turns 첫 3개만 보고도 대화 목적, 결과, fallback 여부를 5초 안에 판단할 수 있어야 한다.",
        "default_priority": "immediate",
        "default_status": "priority",
        "default_owner": "design",
    },
    {
        "iteration": 9,
        "layer": "state",
        "title": "팀 상태 정보 밀도와 기본/접힘 구간 고정",
        "topic": "팀 상태 탭의 정보 밀도를 정리한다.",
        "tab_target": "teams",
        "screen_target": "team-state-cards",
        "trigger_state": "team_state_render",
        "reference_keys": ["checklist", "typography_rules", "anti_patterns"],
        "allow_rebuttal": False,
        "default_problem": "freshness, parse, blocker, eta, progress가 모두 기본 영역에 노출되어 카드가 길어지고, 무엇이 상시 노출 정보인지 합의가 없다.",
        "default_proposal": "상시 노출은 freshness / parse / blocker / progress로 줄이고, eta / next request / raw context는 details에 넣는 정보 밀도 규칙을 고정한다.",
        "default_anti_patterns": [
            "상시 노출 메타가 카드 본문을 밀어냄",
            "상태 탭에서만 볼 정보와 어디서나 볼 정보가 분리되지 않음",
        ],
        "default_acceptance_hint": "팀 상태 카드의 첫 화면은 3줄 이내에서 핵심 상태를 보여주고, 나머지 메타는 접힘 없이도 읽기 흐름을 깨지 않아야 한다.",
        "default_priority": "next",
        "default_status": "candidate",
        "default_owner": "planning",
    },
    {
        "iteration": 10,
        "layer": "interaction",
        "title": "작업 개선 탭에서 repair와 UI/UX backlog 분리",
        "topic": "작업 개선 탭의 흐름을 운영 queue와 디자인 backlog로 분리한다.",
        "tab_target": "improvements",
        "screen_target": "improvements-workspace",
        "trigger_state": "repair_or_backlog_present",
        "reference_keys": ["dashboard_pattern", "visual_style", "anti_patterns"],
        "allow_rebuttal": True,
        "default_problem": "운영 repair queue와 UI/UX 탐색 backlog가 같은 개선 탭 안에서 같은 톤으로 보이면 실행 항목과 탐색 항목이 섞여 보인다.",
        "default_proposal": "작업 개선 탭 안에서 repair queue는 즉시 실행 레일, UI/UX backlog는 탐색/후속 설계 레일로 분리하고 각 레일의 카드 메타와 카피를 다르게 설계한다.",
        "default_anti_patterns": [
            "수정 가능한 queue와 탐색 backlog를 같은 행동 버튼으로 다룸",
            "follow-up 항목이 즉시 실행처럼 보임",
        ],
        "default_acceptance_hint": "작업 개선 탭에서 repair와 UI/UX backlog는 첫눈에 다른 레일로 보이고, 사용자는 어느 쪽이 승인 대상인지 혼동하지 않아야 한다.",
        "default_priority": "immediate",
        "default_status": "priority",
        "default_owner": "pm",
    },
    {
        "iteration": 11,
        "layer": "interaction",
        "title": "근거/초안 탭을 evidence workspace로 재정의",
        "topic": "근거/초안 탭을 evidence workspace로 다듬는다.",
        "tab_target": "evidence",
        "screen_target": "evidence-workspace",
        "trigger_state": "evidence_available",
        "reference_keys": ["dashboard_pattern", "anti_patterns", "checklist"],
        "allow_rebuttal": True,
        "default_problem": "근거, issue draft, follow-up, reference digest가 한곳에 있지만 각각의 역할과 관계가 명시되지 않아 탭의 목적이 모호하다.",
        "default_proposal": "근거/초안 탭을 evidence workspace로 정의하고 findings / issue drafts / reference digest / follow-up issues의 순서를 고정해 검증 맥락을 따라 읽게 만든다.",
        "default_anti_patterns": [
            "근거 없이 draft만 먼저 노출",
            "레퍼런스가 백로그 결과와 연결되지 않음",
        ],
        "default_acceptance_hint": "이 탭에서는 근거가 먼저, 제안/초안이 나중에 오며 각 섹션의 관계를 한 줄 설명으로 이해할 수 있어야 한다.",
        "default_priority": "next",
        "default_status": "candidate",
        "default_owner": "design",
    },
    {
        "iteration": 12,
        "layer": "state",
        "title": "로그 탭 synthetic/derived 이벤트 기본 노출 규칙",
        "topic": "로그 탭 노이즈를 줄인다.",
        "tab_target": "logs",
        "screen_target": "logs-stream",
        "trigger_state": "logs_loaded",
        "reference_keys": ["chart_style", "checklist", "anti_patterns"],
        "allow_rebuttal": False,
        "default_problem": "현재 로그 탭은 operator가 바로 조치할 사건과 synthetic/derived 이벤트가 같은 강도로 보이기 때문에 실제 사건 파악이 느리다.",
        "default_proposal": "operator action과 직접 연결된 사건만 기본 스트림에 남기고, synthetic/derived 이벤트는 접힘 또는 secondary filter에서만 기본 노출한다.",
        "default_anti_patterns": [
            "사건 스트림이 내부 파생 이벤트로 과밀해짐",
            "같은 근본 원인 이벤트가 여러 줄로 반복 노출됨",
        ],
        "default_acceptance_hint": "로그 탭 기본 화면에서는 operator가 조치할 가치가 있는 사건이 상단을 차지하고, 파생 이벤트는 보조 계층에 있어야 한다.",
        "default_priority": "next",
        "default_status": "candidate",
        "default_owner": "planning",
    },
    {
        "iteration": 13,
        "layer": "visual",
        "title": "탭/카드 상태 전이 모션 규칙 150-250ms 고정",
        "topic": "화면 전환과 상태 전환의 motion 규칙을 정한다.",
        "tab_target": "overview",
        "screen_target": "workspace-motion-system",
        "trigger_state": "tab_or_card_transition",
        "reference_keys": ["motion_rules", "anti_patterns", "checklist"],
        "allow_rebuttal": False,
        "default_problem": "탭 전환과 카드 확정/해제 모션이 암묵적으로만 존재해 일관성이 없고, reduced-motion 계약도 UI 레벨에서 명시되지 않았다.",
        "default_proposal": "탭 전환, 카드 확정, pending→resolved 변화는 150~250ms 범위의 짧은 모션으로 통일하고, reduced-motion에서는 opacity와 위치 변화를 최소화한다.",
        "default_anti_patterns": [
            "지속적인 장식 모션",
            "상태 전이를 과장하는 과도한 bounce/scale",
        ],
        "default_acceptance_hint": "모션은 상태 변화를 보조하되 시선을 빼앗지 않아야 하고, reduced-motion 설정에서는 실질적 의미 손실 없이 단순화돼야 한다.",
        "default_priority": "next",
        "default_status": "candidate",
        "default_owner": "design",
    },
    {
        "iteration": 14,
        "layer": "visual",
        "title": "반응형 접힘 우선순위와 접근성 계약",
        "topic": "반응형/접힘/접근성 기준을 정한다.",
        "tab_target": "overview",
        "screen_target": "responsive-contract",
        "trigger_state": "viewport_narrowed",
        "reference_keys": ["checklist", "typography_rules", "motion_rules"],
        "allow_rebuttal": False,
        "default_problem": "좁은 폭에서 어떤 패널이 먼저 접히는지, focus/keyboard/reduced-motion 계약이 무엇인지 명시가 없어 운영 화면 접근성이 우연에 맡겨져 있다.",
        "default_proposal": "좁은 폭에서는 그래프·로그·세부 메타 순으로 접히게 하고, focus ring, 키보드 탐색, reduced-motion, 대비 기준을 운영 대시보드 기본 계약으로 고정한다.",
        "default_anti_patterns": [
            "작은 화면에서 핵심 판단 카드보다 보조 그래프가 먼저 남음",
            "키보드 포커스와 접힘 상태가 불일치",
        ],
        "default_acceptance_hint": "좁은 폭에서도 핵심 판단 카드와 다음 액션은 남고, 키보드만으로 탭 전환과 details 열기가 가능해야 한다.",
        "default_priority": "next",
        "default_status": "candidate",
        "default_owner": "design",
    },
    {
        "iteration": 15,
        "layer": "follow-up",
        "title": "UI/UX backlog 우선순위 레일과 acceptance lock",
        "topic": "최종 정리 라운드에서 backlog를 우선순위화한다.",
        "tab_target": "improvements",
        "screen_target": "uiux-backlog-rail",
        "trigger_state": "backlog_review",
        "reference_keys": ["dashboard_pattern", "checklist", "anti_patterns"],
        "allow_rebuttal": True,
        "default_problem": "백로그 아이템이 쌓이기만 하고 immediate / next / follow-up 구분과 acceptance lock이 없으면 실제 구현 우선순위로 이어지기 어렵다.",
        "default_proposal": "UI/UX backlog에 immediate / next / follow-up 3개 우선순위 레일을 두고, 각 아이템에 acceptance hint와 owner를 잠가 구현 직전의 판단 손실을 줄인다.",
        "default_anti_patterns": [
            "우선순위 없는 아이디어 목록",
            "수용 기준 없는 스타일 제안",
        ],
        "default_acceptance_hint": "최종 backlog는 15개 anchor item을 유지하되 각 항목이 immediate / next / follow-up 중 하나와 acceptance hint를 반드시 가져야 한다.",
        "default_priority": "immediate",
        "default_status": "priority",
        "default_owner": "pm",
    },
]

ALLOWED_LAYERS = {"abstract", "navigation", "state", "card", "interaction", "visual", "follow-up"}
ALLOWED_STATUSES = {"candidate", "priority", "follow-up", "rejected"}
ALLOWED_PRIORITIES = {"immediate", "next", "follow-up"}


def reference_snapshot_dir(repo_root: Path) -> Path:
    return repo_root / ".codex" / "references" / REFERENCE_REPO_NAME


def reference_digest_path(repo_root: Path) -> Path:
    return repo_root / ".codex" / "harness" / "reference" / "ui-ux-dashboard-digest.json"


def design_backlog_path(repo_root: Path) -> Path:
    return repo_root / ".codex" / "harness" / "design-backlog.json"


def design_backlog_drafts_dir(repo_root: Path) -> Path:
    return repo_root / ".codex" / "harness" / "backlog-drafts" / "uiux"


def ensure_uiux_dirs(repo_root: Path) -> None:
    reference_digest_path(repo_root).parent.mkdir(parents=True, exist_ok=True)
    design_backlog_path(repo_root).parent.mkdir(parents=True, exist_ok=True)
    design_backlog_drafts_dir(repo_root).mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_reference_digest(repo_root: Path) -> Dict[str, Any]:
    snapshot = reference_snapshot_dir(repo_root)
    readme = snapshot / "README.md"
    claude = snapshot / "CLAUDE.md"
    mode = "snapshot" if readme.exists() else "fallback_readme"

    sources = []
    if readme.exists():
        sources.append(str(readme))
    if claude.exists():
        sources.append(str(claude))

    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_mode": mode,
        "reference_repo_url": REFERENCE_REPO_URL,
        "sources": sources,
        "dashboard_pattern": [
            "Executive Dashboard",
            "Real-Time Monitoring",
            "Comparative Analysis Dashboard",
        ],
        "visual_style": [
            "Dimensional Layering",
            "Minimalism & Swiss Style",
            "Data-Dense Dashboard",
        ],
        "chart_style": [
            "Comparative change over time",
            "Status density with restrained highlights",
            "Network graph that explains why, not only who",
        ],
        "anti_patterns": [
            "AI purple/pink gradients or neon-heavy glass",
            "Ornate visuals with no filtering or decision path",
            "Slow rendering or decorative motion on operational surfaces",
            "Summary-only cards without action context",
        ],
        "checklist": [
            "high contrast for operational states",
            "prefers-reduced-motion respected",
            "keyboard navigation and focus visible",
            "data density reduced before decorative treatment",
        ],
        "motion_rules": [
            "150-250ms for state transitions",
            "continuous motion only for live/loader meaning",
            "reduced-motion keeps meaning while dropping flourish",
        ],
        "color_rules": [
            "dark graphite base with restrained cyan accent",
            "amber for warn and red for block only",
            "semantic colors must map 1:1 to state taxonomy",
        ],
        "typography_rules": [
            "functional sans for body and labels",
            "14-16px minimum operational body size",
            "tabular alignment for counts and status numbers",
        ],
    }
    return digest


def load_reference_digest(repo_root: Path) -> Dict[str, Any]:
    payload = load_json(reference_digest_path(repo_root), {})
    return payload if isinstance(payload, dict) else {}


def save_reference_digest(repo_root: Path, payload: Dict[str, Any]) -> None:
    ensure_uiux_dirs(repo_root)
    save_json(reference_digest_path(repo_root), payload)


def reference_digest_summary(digest: Dict[str, Any]) -> Dict[str, Any]:
    patterns = digest.get("dashboard_pattern") or []
    styles = digest.get("visual_style") or []
    charts = digest.get("chart_style") or []
    anti_patterns = digest.get("anti_patterns") or []
    checklist = digest.get("checklist") or []
    motion = digest.get("motion_rules") or []
    typography = digest.get("typography_rules") or []
    return {
        "reference_mode": digest.get("reference_mode", "missing"),
        "pattern": " · ".join(patterns[:3]),
        "style": " · ".join(styles[:2]),
        "chart": " · ".join(charts[:2]),
        "anti_patterns": anti_patterns[:4],
        "checklist": checklist[:4],
        "motion_rules": motion[:3],
        "typography_rules": typography[:3],
        "source_count": len(digest.get("sources") or []),
    }


def empty_design_backlog() -> Dict[str, Any]:
    return {
        "generated_at": "",
        "reference_mode": "missing",
        "reference_digest_summary": {},
        "orchestration": {
            "iterations_requested": len(UIUX_ITERATION_SPECS),
            "iterations_completed": 0,
            "execution_mode": "not_run",
            "participants": ["pm", "planning", "design"],
        },
        "items": [],
        "iteration_rationale": [],
        "counts": {
            "total": 0,
            "priority": 0,
            "candidate": 0,
            "follow_up": 0,
            "rejected": 0,
            "immediate": 0,
            "next": 0,
        },
        "abstract_gate": {
            "candidate_allowed": False,
            "signals": {},
        },
    }


def normalize_design_backlog_item(raw_item: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    item = {
        "id": str(raw_item.get("id") or f"uiux-{spec['iteration']:02d}").strip(),
        "iteration": int(raw_item.get("iteration") or spec["iteration"]),
        "layer": str(raw_item.get("layer") or spec["layer"]).strip() or spec["layer"],
        "title": str(raw_item.get("title") or spec["title"]).strip() or spec["title"],
        "tab_target": str(raw_item.get("tab_target") or spec["tab_target"]).strip() or spec["tab_target"],
        "screen_target": str(raw_item.get("screen_target") or spec["screen_target"]).strip() or spec["screen_target"],
        "trigger_state": str(raw_item.get("trigger_state") or spec["trigger_state"]).strip() or spec["trigger_state"],
        "problem": str(raw_item.get("problem") or spec["default_problem"]).strip(),
        "proposal": str(raw_item.get("proposal") or spec["default_proposal"]).strip(),
        "reference_basis": [
            str(value).strip()
            for value in (raw_item.get("reference_basis") or [])
            if str(value).strip()
        ],
        "anti_patterns": [
            str(value).strip()
            for value in (raw_item.get("anti_patterns") or spec["default_anti_patterns"])
            if str(value).strip()
        ],
        "acceptance_hint": str(raw_item.get("acceptance_hint") or spec["default_acceptance_hint"]).strip(),
        "priority": str(raw_item.get("priority") or spec["default_priority"]).strip(),
        "status": str(raw_item.get("status") or spec["default_status"]).strip(),
        "owner": str(raw_item.get("owner") or spec["default_owner"]).strip(),
        "source_round_id": str(raw_item.get("source_round_id") or f"uiux-iteration-{spec['iteration']:02d}").strip(),
        "reference_mode": str(raw_item.get("reference_mode") or "").strip(),
    }
    if item["layer"] not in ALLOWED_LAYERS:
        item["layer"] = spec["layer"]
    if item["status"] not in ALLOWED_STATUSES:
        item["status"] = spec["default_status"]
    if item["priority"] not in ALLOWED_PRIORITIES:
        item["priority"] = spec["default_priority"]
    if not item["reference_basis"]:
        item["reference_basis"] = ["Executive Dashboard", "Dimensional Layering", "Pre-delivery checklist"]
    return item


def summarize_design_backlog(payload: Dict[str, Any]) -> Dict[str, Any]:
    items = payload.get("items") or []
    status_counter = {
        "priority": sum(1 for item in items if item.get("status") == "priority"),
        "candidate": sum(1 for item in items if item.get("status") == "candidate"),
        "follow_up": sum(1 for item in items if item.get("status") == "follow-up"),
        "rejected": sum(1 for item in items if item.get("status") == "rejected"),
        "immediate": sum(1 for item in items if item.get("priority") == "immediate"),
        "next": sum(1 for item in items if item.get("priority") == "next"),
        "total": len(items),
    }
    enriched = dict(payload)
    enriched["counts"] = status_counter
    return enriched


def load_design_backlog(repo_root: Path) -> Dict[str, Any]:
    payload = load_json(design_backlog_path(repo_root), {})
    if not isinstance(payload, dict) or not payload:
        return empty_design_backlog()
    return summarize_design_backlog(payload)


def save_design_backlog(repo_root: Path, payload: Dict[str, Any]) -> None:
    ensure_uiux_dirs(repo_root)
    save_json(design_backlog_path(repo_root), summarize_design_backlog(payload))

