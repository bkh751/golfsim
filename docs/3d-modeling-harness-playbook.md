# 3D Modeling Harness Playbook

이 문서는 `#34 [Parent] 자산 파이프라인과 3D 규격 정의`의 v0 운영 기준이다.

## 1. 현재 결정
- 이번 단계는 `docs-first`다. live 3D 팀을 추가하지 않고, 문서와 skill, advisory hook 정비까지만 진행한다.
- 자산 제작 기준 툴은 `Blender-first`로 잠근다.
- 공통 interchange 포맷은 `glTF/GLB`로 통일한다.
- 실시간 확인 기준은 `Blender authoring -> glTF/GLB export -> Three.js preview` 흐름으로 둔다.
- 브라우저 구현은 계속 `physics source of truth`이며, 3D 자산 규격은 `#45`, `#46`, `#48`과 함께 맞춘다.

## 2. 툴 선택 근거
- Blender는 공개 레퍼런스와 커뮤니티 자산이 가장 풍부하고, 모델링 기준 툴로 설명과 검토를 공유하기 쉽다.
- glTF/GLB는 브라우저와 차기 엔진 사이의 교환 포맷으로 가장 실용적이다.
- Three.js preview는 현재 로컬 환경에서 가장 바로 검증 가능한 경로다.
- Godot는 차기 엔진 feasibility 소비자로 유지하되, 이번 단계의 제작 자동화 기준으로는 삼지 않는다.

## 3. Blender 설치 전제
- 현재 저장소와 로컬 머신은 Blender 바이너리 설치를 전제로 자동화하지 않는다.
- 따라서 v0의 목표는 `설치 스크립트`가 아니라 `작업 기준과 export 규격 문서화`다.
- 실제 모델 제작 또는 Blender MCP 연결은 후속 이슈에서 별도로 다룬다.

## 4. Export / Import Baseline
- authoring: Blender
- interchange: `glTF(.gltf)` 또는 `GLB(.glb)`
- preview consumer: Three.js `GLTFLoader`
- future consumer: Godot glTF import

기본 규칙:
- 렌더 메시와 충돌 메시를 분리할 수 있게 네이밍과 계층을 나눈다.
- pivot/origin 기준은 임팩트 계산과 카메라 기준을 해치지 않게 문서로 먼저 잠근다.
- scale과 좌표계는 `#45`와 `#48`에서 확정할 때까지 임의 확장을 피한다.
- custom DCC 전용 포맷이나 엔진 종속 포맷을 source of truth로 삼지 않는다.

## 5. 학습 병행 규칙
- 사용자가 3D 모델링 비전문가라는 점을 기본 전제로 둔다.
- 모든 3D 작업 응답에는 최소한 아래 세 줄을 포함한다.
  - `상태`
  - `왜 지금 이 작업을 하는지`
  - `다음 피드백 요청`
- 긴 이론 설명은 기본값이 아니다. 막히는 지점이나 새 용어가 실제 결정을 바꿀 때만 짧게 설명한다.

## 6. 피드백 Cadence
- 한 번에 큰 자산 세트를 확정하지 않는다.
- 먼저 `용어/규격`, 다음 `미리보기`, 마지막 `후속 제작` 순으로 나눈다.
- 사용자에게 요청하는 피드백은 항상 하나의 판단으로 압축한다.
  - 예: `이 축을 Y-up으로 고정할지`
  - 예: `클럽/볼 pivot 기준을 물리 기준으로 둘지`

## 7. Live 팀 승격 Gate
- 아래 조건이 모두 충족되기 전까지 `3d_env_art`, `equipment_modeling`은 live 팀으로 승격하지 않는다.
- `#45` 필드/카메라 좌표 기준이 문서로 확정됨
- `#46` 클럽/볼 규격과 pivot 기준이 문서로 확정됨
- `#48` scene/physics data contract 초안이 문서로 확정됨
- Blender -> glTF/GLB -> preview 검증 예시가 최소 1개 확보됨
- 하네스에서 3D 논의를 기존 `pm/planning/design/dev/gameplay_qa` 흐름과 충돌 없이 기록할 수 있음

## 8. 이번 단계의 비범위
- live 3D 팀 추가
- Blender 설치 자동화
- Blender MCP 실연결
- 실제 필드/클럽/볼 자산 제작 착수
- 오케스트레이터 role enum 확장

## 9. 참고
- [OpenAI Codex app 소개](https://openai.com/index/introducing-the-codex-app/)
- [openai/skills](https://github.com/openai/skills)
- [Blender MCP](https://github.com/ahujasid/blender-mcp)
- [three.js](https://github.com/mrdoob/three.js)
- [Blender glTF 2.0 manual](https://docs.blender.org/manual/en/4.5/addons/import_export/scene_gltf2.html)
- [Three.js GLTFLoader docs](https://threejs.org/docs/pages/GLTFLoader.html)
- [Godot scene import docs](https://docs.godotengine.org/en/4.0/tutorials/assets_pipeline/importing_scenes.html)
