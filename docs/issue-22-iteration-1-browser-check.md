# Issue #22 Iteration 1 브라우저 검증 경로

## 목적
- `ready -> impact -> flight -> result -> comparison -> auto reset -> ready` 루프를 Playwright 기반으로 검증한다.
- 현재 환경에서 실행이 막히면 같은 지점에서 다음 iteration이 바로 재개되도록 경로를 고정한다.

## 실행 명령
1. 정적 마커 확인
   - `node --test test/ui-markers.test.mjs`
2. 브라우저 상호작용 테스트
   - `node --test test/ui-interaction.test.mjs`
3. 전체 테스트 묶음
   - `npm test`
4. 수동 앱 기동
   - `npm run dev`
5. 수동 액션 재생
   - `npm run action:test`

## 필요한 전제 조건
- 현재 작업 디렉터리: `/Users/user/workspace/game/golfsim`
- Node 환경에서 `127.0.0.1` loopback bind가 허용되어야 한다.
- `playwright` 패키지가 설치된 현재 저장소 상태여야 한다.
- GUI 가능한 세션이 있거나, headless 브라우저 실행이 가능한 샌드박스여야 한다.

## 앱 기동 방법 또는 URL
- 수동 서버:
  - `npm run dev`
  - 기본 URL: `http://127.0.0.1:4173`
- 테스트 서버:
  - `test/ui-interaction.test.mjs`가 내부에서 임시 HTTP 서버를 띄운 뒤 `http://127.0.0.1:<random-port>/index.html`로 진입한다.
- 액션 재생:
  - `scripts/run-action.mjs`가 자체 HTTP 서버를 띄우고 Playwright로 `index.html`을 연다.

## 실제 실패 지점
- 명령: `npm test`
- 실패 파일: `test/ui-interaction.test.mjs`
- 실패 코드 경로:
  - `createServer()`
  - `server.listen(0, '127.0.0.1')`
- 실제 오류:
  - `listen EPERM: operation not permitted 127.0.0.1`

## 현재 환경에서 막히는 이유
- Playwright 상호작용 이전 단계에서 테스트용 로컬 HTTP 서버가 `127.0.0.1`에 바인딩되지 않는다.
- 즉 현재 환경의 blocker는 브라우저 조작 자체가 아니라 loopback listen 권한 제약이다.

## 다음 iteration 재개 조건
1. `127.0.0.1` loopback bind가 허용되는 환경으로 세션을 옮긴다.
2. 같은 저장소 루트에서 `node --test test/ui-interaction.test.mjs`를 먼저 실행한다.
3. 통과하면 `npm test`로 전체 회귀를 다시 확인한다.
4. GUI 가능한 세션이 있으면 아래 두 시나리오를 추가로 눈으로 확인한다.
   - `결과가 있는 상태에서 초기화`
   - `변경된 입력이 있는 상태에서 초기화`
