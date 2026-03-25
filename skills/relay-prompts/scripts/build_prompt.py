#!/usr/bin/env python3
import argparse
from textwrap import dedent
from typing import Optional


REPO = "/Users/user/workspace/game/golfsim"
AGENTS = f"{REPO}/AGENTS.md"
PRODUCT = f"{REPO}/docs/product.md"
ORDER = dedent(
    """\
    - 상태:
    - 이해한 범위:
    - 결과:
    - blocker:
    - 다음 요청:
    """
).rstrip()


ROLE_NAMES = {
    "pm": "PM 담당",
    "planning": "기획 담당",
    "design": "디자인 담당",
    "dev": "개발 담당",
    "review": "리뷰 담당",
}


ROLE_RULES = {
    "pm": [
        "- 이슈 구조, 라벨, 링크, 트리아지 관점으로 정리한다.",
        "- 구현 상세나 디자인 상세를 대신 결정하지 않는다.",
    ],
    "planning": [
        "- Goal, Problem, User Value, Scope, Out of Scope, Acceptance Criteria 중심으로 정리한다.",
        "- 디자인/개발 결정을 대신하지 않는다.",
    ],
    "design": [
        "- Target Surface, States and Transitions, Feedback and Copy 중심으로 정리한다.",
        "- 전체 UI 리디자인으로 범위를 넓히지 않는다.",
    ],
    "dev": [
        "- Scope, Out of Scope, Dependencies, Test Plan, Completion Notes 중심으로 정리한다.",
        "- 완료 보고 시 결과에는 구현 내용, 테스트 결과, 남은 리스크만 포함한다.",
    ],
    "review": [
        "- 실제 회귀, 검증 누락, 남은 리스크 중심으로 정리한다.",
        "- 스타일 취향이나 재설계 제안으로 범위를 넓히지 않는다.",
    ],
}


def build_prompt(
    role: str,
    parent_issue: str,
    task_request: str,
    confirmed_context: Optional[str],
    blocker_context: Optional[str],
) -> str:
    header = [
        f"당신은 golfsim 저장소의 {ROLE_NAMES[role]}이다.",
        "",
        "반드시 아래 규칙을 따른다.",
        f"- {AGENTS} 를 따른다.",
        f"- {PRODUCT} 를 따른다.",
        "- 사용자가 팀 간 중계자라고 가정한다.",
        "- 모든 응답은 아래 순서를 따른다.",
        ORDER,
        "- blocker가 없으면 `blocker: 없음`으로 쓴다.",
        "- 추가 입력이 필요하면 `다음 요청`에만 적는다.",
    ]

    body = [
        "",
        "현재 대표 이슈:",
        f"- GitHub Issue {parent_issue}",
    ]

    if confirmed_context:
        body.extend([
            "",
            "현재 확정 내용:",
            confirmed_context.rstrip(),
        ])

    if blocker_context:
        body.extend([
            "",
            "현재 blocker:",
            blocker_context.rstrip(),
        ])

    body.extend([
        "",
        "이번 요청:",
        task_request.rstrip(),
        "",
        "추가 규칙:",
    ])
    body.extend(ROLE_RULES[role])
    return "\n".join(header + body).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build relay prompts for golfsim team handoff.")
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
