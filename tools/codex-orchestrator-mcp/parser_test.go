package main

import "testing"

func TestParseTeamResponseOK(t *testing.T) {
	text := `상태: 진행 중
이해한 범위: 24번 이슈 범위 확인
결과: 핵심 변경 정리
blocker: 없음
다음 요청: PM 확인`

	parsed, err := ParseTeamResponse(text)
	if err != nil {
		t.Fatalf("예상치 못한 에러: %v", err)
	}
	if parsed.ParseStatus != "ok" {
		t.Fatalf("parse_status = %s", parsed.ParseStatus)
	}
	if parsed.Blocker != "없음" {
		t.Fatalf("blocker = %q", parsed.Blocker)
	}
	if parsed.ParseMode != "strict" {
		t.Fatalf("parse_mode = %s", parsed.ParseMode)
	}
}

func TestParseTeamResponseShuffledOrder(t *testing.T) {
	text := `결과: 결과 먼저
다음 요청: 다음 단계
상태: 검토 필요
blocker: 없음
이해한 범위: 순서가 바뀐 응답`

	parsed, err := ParseTeamResponse(text)
	if err != nil {
		t.Fatalf("순서가 바뀌어도 파싱되어야 함: %v", err)
	}
	if parsed.Status != "검토 필요" {
		t.Fatalf("status = %q", parsed.Status)
	}
	if parsed.NextRequest != "다음 단계" {
		t.Fatalf("next_request = %q", parsed.NextRequest)
	}
}

func TestParseTeamResponseRelaxedHeaders(t *testing.T) {
	text := `## Status - 진행 가능
Scope - relaxed header 허용
Summary - 요약만 있음
Risk - 없음
Next - 없음`

	parsed, err := ParseTeamResponse(text)
	if err != nil {
		t.Fatalf("relaxed parse는 허용되어야 함: %v", err)
	}
	if parsed == nil || parsed.ParseStatus != "relaxed" {
		t.Fatalf("relaxed 예상, got %#v", parsed)
	}
}

func TestParseTeamResponsePartialWithoutHeaders(t *testing.T) {
	text := `핵심 변경은 direct peer route와 steering event를 추가하는 것이다.
blocker는 없고 다음 요청은 대시보드에 drag factor를 반영하는 것이다.`

	parsed, err := ParseTeamResponse(text)
	if err != nil {
		t.Fatalf("partial parse는 허용되어야 함: %v", err)
	}
	if parsed == nil || parsed.ParseStatus != "partial" {
		t.Fatalf("partial 예상, got %#v", parsed)
	}
	if parsed.Result == "" {
		t.Fatal("heuristic result가 비어 있음")
	}
}

func TestParseTeamResponseCompactPacket(t *testing.T) {
	text := `st:ok | sc:peer align | rs:hud cut keep curve | bk:none | rq:pm lock | cf:0.81 | nr:1 | pr:interrupt | cd:kv | ix:1 | tb:48`

	parsed, err := ParseTeamResponse(text)
	if err != nil {
		t.Fatalf("compact parse는 허용되어야 함: %v", err)
	}
	if parsed == nil || parsed.ParseMode != "compact" {
		t.Fatalf("compact parse 예상, got %#v", parsed)
	}
	if parsed.Priority != "interrupt" || !parsed.Interrupt {
		t.Fatalf("priority/interrupt 해석 실패: %#v", parsed)
	}
	if parsed.Codec != "kv" || parsed.TokenBudget != 48 {
		t.Fatalf("codec/token_budget 해석 실패: %#v", parsed)
	}
}

func TestParseTeamResponseCompactAckPacket(t *testing.T) {
	text := `st:ack | eta:90 | more:1 | risk:none | ask:none`

	parsed, err := ParseTeamResponse(text)
	if err != nil {
		t.Fatalf("ack packet parse는 허용되어야 함: %v", err)
	}
	if parsed.ParseMode != "compact" {
		t.Fatalf("compact parse 예상, got %#v", parsed)
	}
	if parsed.ProgressState != "ack" || parsed.EtaSeconds != 90 || !parsed.MoreComing {
		t.Fatalf("ack progress 해석 실패: %#v", parsed)
	}
}

func TestParseTeamResponseAckPrefixDoesNotOverrideFinalBody(t *testing.T) {
	text := `st:ack | eta:90 | more:1 | risk:none | ask:none

상태: 진행 가능
이해한 범위: ack 뒤 본문
결과: 최종 답변 본문
blocker: 없음
다음 요청: 없음`

	parsed, err := ParseTeamResponse(text)
	if err != nil {
		t.Fatalf("ack prefix parse는 허용되어야 함: %v", err)
	}
	if parsed.ParseStatus != "ok" {
		t.Fatalf("strict parse 예상, got %#v", parsed)
	}
	if parsed.Result != "최종 답변 본문" {
		t.Fatalf("ack line이 결과를 덮어쓰면 안 됨: %#v", parsed)
	}
	if parsed.EtaSeconds != 90 {
		t.Fatalf("ack eta는 유지되어야 함: %#v", parsed)
	}
}

func TestParseTeamResponseHeuristicAskOwnerBullets(t *testing.T) {
	text := `- owner: design
- ask: pm lock
- overlay reduce, carry keep`

	parsed, err := ParseTeamResponse(text)
	if err != nil {
		t.Fatalf("bullet heuristic parse는 허용되어야 함: %v", err)
	}
	if parsed.ParseStatus != "partial" {
		t.Fatalf("partial 예상, got %#v", parsed)
	}
	if parsed.Scope != "design" {
		t.Fatalf("owner 해석 실패: %#v", parsed)
	}
	if parsed.NextRequest != "pm lock" {
		t.Fatalf("ask 해석 실패: %#v", parsed)
	}
	if parsed.Result == "" {
		t.Fatalf("bullet result가 비어 있음: %#v", parsed)
	}
}

func TestParseTeamResponseRelaxedAskHeader(t *testing.T) {
	text := `status: review
owner: gameplay_qa
summary: repeat feel keeps readable
risk: overlay crowd
ask: dev trim labels`

	parsed, err := ParseTeamResponse(text)
	if err != nil {
		t.Fatalf("ask/owner relaxed parse는 허용되어야 함: %v", err)
	}
	if parsed.ParseStatus != "relaxed" {
		t.Fatalf("relaxed 예상, got %#v", parsed)
	}
	if parsed.Scope != "gameplay_qa" || parsed.NextRequest != "dev trim labels" {
		t.Fatalf("owner/ask 해석 실패: %#v", parsed)
	}
}
