---
name: relay-prompts
description: Generate short relay prompts for PM, planning, design, development, and review work in the golfsim repository. Use when you need a reusable prompt that follows this repo's policy context, parent-issue workflow, and free-form compact collaboration style without repeating boilerplate file paths.
---

# Relay Prompts

Use this skill to generate copy-paste prompts for team handoff in this repository.

This skill is repo-specific. It always assumes:
- 저장소 기본 협업 정책과 제품 방향은 이미 컨텍스트에 적용돼 있다
- the user is the relay between teams
- prompts should be short, explicit, and free-form
- fixed response templates should not be enforced

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

1. 필요할 때만 [`AGENTS.md`](/Users/user/workspace/game/golfsim/AGENTS.md) 와 [`docs/product.md`](/Users/user/workspace/game/golfsim/docs/product.md) 를 확인한다.
2. Generate a relay prompt for the requested role.
3. Include `confirmed_context` only when it changes the next decision.
4. Include `blocker_context` only when it is truly blocking or redirects the ask.
5. Keep the prompt short, direct, and easy to relay. Do not add long explanations.

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
- Always include the parent issue section.
- Do not restate `AGENTS.md` or `docs/product.md` paths in the prompt unless the user explicitly asks for them.
- Never invent confirmed decisions or blockers.
- Keep role-specific additions limited to what that team needs next.
- Prefer compact asks over verbose templates.
