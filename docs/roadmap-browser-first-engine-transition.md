# Browser-First Roadmap

## 1. 방향
- `golfsim`은 당분간 브라우저 시뮬레이터를 제품 기준 구현이자 `physics benchmark / harness` 기준 자산으로 유지한다.
- 다음 큰 목표는 `브라우저 기반 제품 완성 + 하네스 정교화`다.
- 차기 엔진 전환은 그 다음 단계의 `데스크톱 알파` 준비 트랙으로 분리한다.
- 엔진 feasibility는 우선 `Godot`을 기준 후보로 검토한다.

## 2. 마일스톤

### M1. 브라우저 제품 완성 기준선 고정
- 목표: 반복 플레이, 결과 해석, 물리 신뢰도, 최소 검증 경로를 브라우저 제품 안에서 안정화한다.
- 완료 기준:
  - 핵심 플레이 루프가 혼동 없이 닫힌다.
  - `npm test`, `npm run benchmark:flight`, 하네스 경고가 먼저 회귀를 잡는다.
  - 하네스가 실제 팀 상태, fallback 의존도, relay 품질을 대시보드에 드러낸다.
- 관련 이슈:
  - `#19 [Parent] Golfsim 제품 완성`
  - `#30 [Dev] 고탄도 드라이버 물리 2차 보정과 benchmark matrix 확대`
  - `#31 [Dev] 하네스에 physics benchmark 자동 회귀 감지 추가`
  - `#13 [Parent] 내부 리팩토링 분리`
  - `#32 [Parent] Harness 2.0 운영 고도화`

### M2. 브라우저 Vertical Slice
- 목표: 브라우저에서 먼저 “작지만 출시 감 있는 골프 체험”을 만든다.
- 범위:
  - 샷 루프 완성도
  - 클럽/볼 입력 체계
  - 기본 환경 아트 방향성
  - 사운드 최소 세트
  - 세션/리플레이/튜토리얼 최소형
- 완료 기준:
  - 처음 보는 사용자가 `easy to start, hard to master`를 체감한다.
  - 최소 감성층이 붙은 vertical slice가 된다.
- 관련 이슈:
  - `#33 [Parent] 브라우저 Vertical Slice`
  - `#40 [Planning] 클럽/볼/세션 규칙 정리`
  - `#41 [Design] HUD/피드백/튜토리얼 1차`
  - `#42 [Dev] 세션/리플레이/입력 구조 정리`
  - `#43 [PM/Design] 사운드/임팩트/환경 피드백 최소 세트`
  - `#44 [PM] 콘텐츠 컷라인과 vertical slice acceptance`

### M3. 콘텐츠/자산 파이프라인 설계
- 목표: 나중에 엔진으로 넘어가도 재사용 가능한 자산 규격과 제작 흐름을 먼저 정한다.
- 범위:
  - 골프장 필드 메시 구조
  - 티박스/타깃/거리 마커 자산 규격
  - 클럽/볼 모델 규격
  - 충돌 메시와 렌더 메시 분리 정책
  - 오디오 이벤트 목록과 트리거 규칙
- 완료 기준:
  - 자산 제작 규격과 공통 scene/physics data contract 초안이 정리된다.
- 관련 이슈:
  - `#34 [Parent] 자산 파이프라인과 3D 규격 정의`
  - `#45 [Planning/Design] 골프장 필드 구성과 카메라 기준 좌표계`
  - `#46 [Planning] 클럽/볼 자산 규격과 상호작용 모델`
  - `#47 [PM] 오디오 이벤트 매핑과 피드백 우선순위`
  - `#48 [Dev] 공통 scene/physics data contract 초안`

### M4. 엔진 Feasibility와 데스크톱 알파 준비
- 목표: 브라우저 기준 구현을 바탕으로 데스크톱 알파 패키징 가능성을 검증한다.
- 범위:
  - Godot로 최소 장면/카메라/입력/공 비행 재현
  - 브라우저 physics benchmark를 엔진과 비교
  - 데스크톱 패키징, 설정, 해상도, 입력 장치 검증
- 완료 기준:
  - 엔진 전환 가능 여부를 `benchmark`, `vertical slice 포팅 난이도`, `패키징` 기준으로 판단할 수 있다.
- 관련 이슈:
  - `#35 [Parent] 데스크톱 알파 엔진 feasibility`
  - `#49 [Dev/R&D] Godot scene bootstrap과 input/camera 재현`
  - `#50 [Dev/R&D] 브라우저 physics benchmark를 Godot 비교 harness로 이식`
  - `#51 [PM] 데스크톱 알파 acceptance와 패키징 목표 정의`

## 3. Harness 운영 방향
- 유지 팀:
  - `pm`
  - `planning`
  - `design`
  - `dev`
  - `gameplay_qa`
- 당장 라이브 세션으로 추가하지 않을 팀:
  - `3d_env_art`
  - `equipment_modeling`
  - `audio_design`
- 위 역할은 M3에서 자산 규격이 정리된 뒤 필요 시 라이브 세션으로 승격한다.
- Harness 2.0 관련 이슈:
  - `#32 [Parent] Harness 2.0 운영 고도화`
  - `#36 [Dev] 하네스 상호작용 품질 정량화와 대시보드 개선`
  - `#37 [Dev] gameplay_qa 실세션 바인딩과 direct round 회복`
  - `#38 [Dev] relay prompt parse_error 감소와 5섹션 강제`
  - `#39 [PM] roundtable 결과에서 backlog draft 생성 기준 정교화`
  - `#31 [Dev] 하네스에 physics benchmark 자동 회귀 감지 추가`

## 4. Harness가 보여줘야 할 운영 지표
- 라우팅 건강도:
  - `targets bound ratio`
  - `dispatch success rate`
  - `open dispatch count`
  - `stale role count`
  - `parse_error count`
- 라운드 품질:
  - `round completion rate`
  - `latest round fallback ratio`
  - `role coverage per round`
  - `turn budget 준수`
  - `rebuttal step 존재 여부`
- 제품 검증 연결:
  - `physics benchmark pass/fail`
  - `gameplay QA evidence 존재 여부`
  - `backlog candidate 생성 수`
  - `draft issue 생성 결과`
- 운영 종합:
  - `working`
  - `weak points`
  - `next actions`
  - `latest turn synthesis`

## 5. 공통 계약
- 브라우저 버전은 계속 `physics source of truth`로 유지한다.
- 차기 엔진 feasibility도 아래 기준을 공유한다.
  - `ball speed / launch / backspin / sidespin / aim` 입력 계약
  - 공통 benchmark matrix
  - 공통 거리 단위와 좌표계 정의
  - 공통 acceptance 샘플 샷 세트
- M3 자산 파이프라인에서는 아래 contract를 문서화한다.
  - 필드 메시 규격
  - 충돌 메시 vs 렌더 메시 분리
  - 클럽/볼 pivot 기준
  - 카메라 기준 좌표와 scale
  - 환경/오디오 이벤트 ID 체계

## 6. 검증 원칙
- 제품/물리:
  - `npm test`
  - `npm run benchmark:flight`
- 하네스:
  - round completion / fallback / parse_error / stale 탐지 테스트
  - dashboard payload contract 테스트
  - gameplay QA evidence 유무 테스트
- 엔진 feasibility 이후:
  - 브라우저 vs 엔진 benchmark 비교
  - 입력/카메라/거리 결과 비교
  - 데스크톱 패키징 smoke test
