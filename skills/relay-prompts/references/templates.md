# Role Templates

Use these defaults when generating prompts manually or validating script output.

## Preferred Operating Mode

When a task crosses ownership boundaries, prefer:
- PM orchestrator template first
- specialist relay prompts second
- development handoff prompt last

Use the prompt documents below as the source templates:
- `/Users/user/.codex/worktrees/1c16/golfsim/docs/prompts/pm-orchestrator-master.md`
- `/Users/user/.codex/worktrees/1c16/golfsim/docs/prompts/dev-handoff-template.md`

## Common Base

Every prompt should include:
- role declaration
- `/Users/user/workspace/game/golfsim/AGENTS.md`
- `/Users/user/workspace/game/golfsim/docs/product.md`
- user-as-relay assumption
- fixed response order
- current parent issue
- optional `현재 확정 내용`
- optional `현재 blocker`
- current request

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
- 구현 내용:
- 테스트 결과:
- 남은 리스크:

## `review`

Focus:
- findings
- validation gaps
- remaining risk

Keep review prompts oriented around concrete regressions and missing validation, not redesign.
