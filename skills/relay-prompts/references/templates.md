# Role Templates

Use these defaults when generating prompts manually or validating script output.

## Common Base

Every prompt should include:
- role declaration
- 저장소 기본 정책은 이미 적용돼 있다고 보는 전제
- user-as-relay assumption
- current parent issue
- optional `현재 확정 내용`
- optional `현재 막힘 또는 주의`
- current request
- short free-form response expectation

## `pm`

Focus:
- issue structure
- labels
- links
- triage
- scope alignment

Typical asks:
- audit parent issue
- resolve blocker with policy decisions
- propose linked issue text

## `planning`

Focus:
- Goal
- Problem
- User Value
- Scope
- Out of Scope
- Acceptance Criteria
- Open Questions
- Completion Notes

## `design`

Focus:
- Target Surface
- Scope
- Out of Scope
- States and Transitions
- Feedback and Copy
- Open Questions
- Completion Notes

## `dev`

Focus:
- Scope
- Out of Scope
- Dependencies
- Test Plan
- Open Questions
- Completion Notes

Completion note format:
- 구현 내용, 테스트 결과, 남은 리스크만 짧게 정리

## `review`

Focus:
- findings
- validation gaps
- remaining risk

Keep review prompts oriented around concrete regressions and missing validation, not redesign.
