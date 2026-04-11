---
name: 3d-modeling-harness
description: Use when working on 3D modeling, asset pipeline, Blender-first authoring rules, glTF/GLB interchange, or user-facing 3D guidance in the golfsim repository. This skill keeps the work tied to issue #34 unless a linked child issue is explicitly given.
---

# 3D Modeling Harness

Use this skill for `golfsim` 3D modeling and asset-pipeline work.

This skill assumes:
- the default parent issue is `#34 [Parent] 자산 파이프라인과 3D 규격 정의`
- the current stage is `docs-first`
- Blender is the authoring standard
- `glTF/GLB` is the interchange format
- live 3D teams are deferred until promotion gates are met

## Read First
- [`AGENTS.md`](/Users/user/workspace/game/golfsim/AGENTS.md)
- [`docs/product.md`](/Users/user/workspace/game/golfsim/docs/product.md)
- [`docs/3d-modeling-harness-playbook.md`](/Users/user/workspace/game/golfsim/docs/3d-modeling-harness-playbook.md)

Load references only as needed:
- [references/blender-first.md](references/blender-first.md) for toolchain and export rules
- [references/prompt-recipes.md](references/prompt-recipes.md) for user-facing prompt patterns and feedback cadence

## Workflow
1. Confirm whether the request belongs to `#34` or an explicitly linked child issue such as `#45`, `#46`, or `#48`.
2. If no issue is specified, default to `#34` instead of inventing a new track.
3. Keep the work in the smallest valid slice: terminology, contract, preview, or follow-up task.
4. Prefer documentation, validation, and guidance over premature asset production or tool automation.
5. Do not assume Blender or Godot is installed locally unless verified in the current environment.

## Output Rules
- Every 3D response should include these short headings in order:
  - `상태`
  - `왜 지금 이 작업인지`
  - `모델링 작업`
  - `리스크`
  - `사용자 확인`
- Add `학습 메모` only when a short explanation materially helps the user make the next decision.
- Keep explanations compact. Teach only what is necessary for the current choice.
- If the request suggests a live 3D team, explain that v0 is still `docs-first` unless the user explicitly asks to plan promotion work.

## Guardrails
- Do not change `supportedRoles` or add live 3D team bindings unless the task explicitly targets the orchestrator role model.
- Do not make Blender-first mean Blender-only. Preview and interchange still need browser-friendly validation.
- Prefer `glTF/GLB` over engine-specific source formats when documenting shared contracts.
- Separate observed facts, recommended defaults, and unresolved decisions.
