---
name: relay-prompts
description: Generate relay-style prompts for PM, planning, design, development, and review work in the golfsim repository. Use when you need a reusable prompt that follows this repo's AGENTS.md, docs/product.md, parent-issue workflow, and fixed response protocol.
---

# Relay Prompts

Use this skill to generate copy-paste prompts for team handoff in this repository.

This skill is repo-specific. It always assumes:
- [`AGENTS.md`](/Users/user/workspace/game/golfsim/AGENTS.md) is the collaboration policy
- [`docs/product.md`](/Users/user/workspace/game/golfsim/docs/product.md) is the product policy
- the user is the relay between teams
- prompts must enforce the fixed response order:
  - 상태
  - 이해한 범위
  - 결과
  - blocker
  - 다음 요청

## Inputs

Required:
- `role`: `pm`, `planning`, `design`, `dev`, or `review`
- `parent_issue`: issue number and title, for example `#3 [Parent] 결과 패널 경험 개선`
- `task_request`: one-line request to the target team

Optional:
- `confirmed_context`: prior decisions that are already fixed
- `blocker_context`: blocker text or follow-up question

If any required input is missing, do not invent it. Ask for the missing field directly.

## Workflow

1. Read [`AGENTS.md`](/Users/user/workspace/game/golfsim/AGENTS.md) and [`docs/product.md`](/Users/user/workspace/game/golfsim/docs/product.md) if you need to confirm current rules.
2. Generate a relay prompt for the requested role.
3. Include `confirmed_context` only as an explicit `현재 확정 내용` section.
4. Include `blocker_context` only as an explicit `현재 blocker` section.
5. Keep the prompt short and mechanical. Do not add long explanations.

## Preferred Path

Use the bundled script for deterministic output:

```bash
python3 skills/relay-prompts/scripts/build_prompt.py \
  --role dev \
  --parent-issue "#3 [Parent] 결과 패널 경험 개선" \
  --task-request "대표 이슈 #3에 연결될 개발 하위 이슈 초안을 작성하라."
```

If the script is not appropriate, follow the role defaults in [references/templates.md](references/templates.md).

## Output Rules

- Always include absolute repo paths.
- Always include the fixed response order.
- Always include the parent issue section.
- Never invent confirmed decisions or blockers.
- Keep role-specific additions limited to what that team needs next.
