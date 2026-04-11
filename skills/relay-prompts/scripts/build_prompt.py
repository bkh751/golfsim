#!/usr/bin/env python3
import argparse
from typing import Optional


ROLE_NAMES = {
    "pm": "PM",
    "planning": "기획",
    "design": "디자인",
    "dev": "개발",
    "gameplay_qa": "게임플레이 QA",
    "review": "리뷰",
}


ROLE_RULES = {
    "pm": "이슈 구조, 범위 잠금, 역할 간 결정 정렬에 집중하고 구현 상세는 대신 결정하지 마라.",
    "planning": "Goal, Scope, Acceptance Criteria, Open Questions를 짧게 정리하고 디자인/개발 결정을 대신하지 마라.",
    "design": "표면, 상태 전이, 피드백, 정보 밀도를 짧게 정리하고 전체 리디자인으로 범위를 넓히지 마라.",
    "dev": "구현 범위, 의존성, 테스트, 남은 리스크를 짧게 정리하고 승인 범위를 넘지 마라.",
    "gameplay_qa": "실플레이 감각, 재현 절차, 개선 가설, 다음 검증 포인트만 남기고 코드 수정은 하지 마라.",
    "review": "회귀, 검증 누락, 남은 리스크만 우선 지적하고 취향성 재설계로 퍼뜨리지 마라.",
}


def section(title: str, value: Optional[str]) -> str:
    if not value or not value.strip():
        return ""
    return f"{title}\n{value.strip()}\n"


def build_prompt(
    role: str,
    parent_issue: str,
    task_request: str,
    confirmed_context: Optional[str],
    blocker_context: Optional[str],
) -> str:
    parts = [
        f"너는 golfsim 저장소의 {ROLE_NAMES[role]} 역할이다.",
        "응답은 자유 형식으로 짧고 정확하게 써라. 템플릿 채우기 금지.",
        "핵심 판단, 실제 리스크, 필요한 액션, 소유자만 남겨라.",
        "저장소 기본 협업 규칙과 제품 방향은 이미 적용돼 있다고 보고 다시 설명하지 마라.",
        "",
        f"Parent Issue\n- {parent_issue.strip()}",
    ]

    if confirmed_context and confirmed_context.strip():
        parts.append(section("현재 확정 내용", confirmed_context).rstrip())
    if blocker_context and blocker_context.strip():
        parts.append(section("현재 막힘 또는 주의", blocker_context).rstrip())

    parts.extend(
        [
            f"이번 요청\n{task_request.strip()}",
            f"역할 초점\n{ROLE_RULES[role]}",
        ]
    )
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build short relay prompts for golfsim team handoff.")
    parser.add_argument("--role", choices=sorted(ROLE_NAMES.keys()), required=True)
    parser.add_argument("--parent-issue", required=True)
    parser.add_argument("--task-request", required=True)
    parser.add_argument("--confirmed-context")
    parser.add_argument("--blocker-context")
    args = parser.parse_args()

    prompt = build_prompt(
        role=args.role,
        parent_issue=args.parent_issue,
        task_request=args.task_request,
        confirmed_context=args.confirmed_context,
        blocker_context=args.blocker_context,
    )
    print(prompt, end="")


if __name__ == "__main__":
    main()
