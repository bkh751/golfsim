# Codex Orchestrator MCP

`golfsim` 메인 세션 또는 승인된 harness worker가 `pm`, `planning`, `design`, `dev`, `gameplay_qa` 팀 세션에 직접 턴을 라우팅할 수 있게 하는 repo-local MCP 서버다.

주요 역할:

- Codex `app-server` child를 통해 기존 thread에 `turn/start`를 전송한다.
- `.codex/orchestrator/` 아래에 바인딩, 대시보드 상태, dispatch 로그, prompt snapshot을 저장한다.
- `.codex/harness/rounds/` 아래에 라운드테이블 요청과 산출물을 저장한다.
- `skills/relay-prompts/scripts/build_prompt.py`를 재사용해 compact relay prompt를 만든다.
- 팀 응답을 free-form, compact packet, kv packet까지 포함해 파싱하고 대시보드에 반영한다.

기본 사용 흐름:

1. `discover_threads`로 현재 프로젝트 thread 후보를 찾는다.
2. `bind_targets`로 `pm/planning/design/dev/gameplay_qa -> thread_id`를 고정한다.
3. `dispatch_turn` 또는 `broadcast_turn`으로 팀 세션에 턴을 보낸다.
4. `roundtable_start`, `roundtable_read`, `roundtable_list`로 라운드 큐와 산출물을 관리한다.
5. `read_dashboard`와 `read_team`으로 최신 상태를 읽는다.

실행:

```sh
scripts/start-codex-orchestrator-mcp.sh
```

테스트:

```sh
go test ./...
```
