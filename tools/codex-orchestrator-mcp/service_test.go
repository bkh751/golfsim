package main

import (
	"context"
	"testing"
	"time"
)

func TestServiceDispatchUpdatesDashboard(t *testing.T) {
	repoRoot := t.TempDir()
	client := NewAppServerClient(helperConfig(repoRoot))
	defer client.Close()

	service, err := NewService(repoRoot, client)
	if err != nil {
		t.Fatalf("NewService 실패: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if _, err := service.BindTargets(ctx, BindTargetsArgs{
		Bindings: map[string]string{"pm": "thread-pm"},
	}); err != nil {
		t.Fatalf("BindTargets 실패: %v", err)
	}

	waitForCompletion := true
	result, err := service.DispatchTurn(ctx, DispatchTurnArgs{
		Role:              "pm",
		ParentIssue:       "#25",
		TaskRequest:       "fake dispatch",
		PromptOverride:    "테스트 프롬프트",
		WaitForCompletion: &waitForCompletion,
	})
	if err != nil {
		t.Fatalf("DispatchTurn 실패: %v", err)
	}
	if result.ParseStatus != "ok" {
		t.Fatalf("parse_status = %s", result.ParseStatus)
	}
	if result.Parsed == nil || result.Parsed.Blocker != "없음" {
		t.Fatalf("parsed 결과가 예상과 다름: %#v", result.Parsed)
	}

	dashboard, err := service.ReadDashboard(ctx)
	if err != nil {
		t.Fatalf("ReadDashboard 실패: %v", err)
	}
	entry := dashboard.Entries["pm"]
	if entry.LastStatus != "진행 가능" {
		t.Fatalf("dashboard last_status = %q", entry.LastStatus)
	}
	if entry.Stale {
		t.Fatal("방금 갱신한 entry가 stale=true 임")
	}
	if time.Since(entry.UpdatedAt) > time.Minute {
		t.Fatalf("updated_at가 너무 오래됨: %v", entry.UpdatedAt)
	}

	team, err := service.ReadTeam(ctx, ReadTeamArgs{Role: "pm", IncludeTurns: true})
	if err != nil {
		t.Fatalf("ReadTeam 실패: %v", err)
	}
	if team.Thread == nil || len(team.Thread.Turns) == 0 {
		t.Fatalf("raw thread turns가 비어 있음: %#v", team.Thread)
	}
}

func TestServiceRouteTurnAndSteerRound(t *testing.T) {
	repoRoot := t.TempDir()
	client := NewAppServerClient(helperConfig(repoRoot))
	defer client.Close()

	service, err := NewService(repoRoot, client)
	if err != nil {
		t.Fatalf("NewService 실패: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if _, err := service.BindTargets(ctx, BindTargetsArgs{
		Bindings: map[string]string{
			"pm":       "thread-pm",
			"planning": "thread-planning",
			"design":   "thread-design",
			"dev":      "thread-dev",
		},
	}); err != nil {
		t.Fatalf("BindTargets 실패: %v", err)
	}

	start, err := service.RoundtableStart(ctx, RoundtableStartArgs{
		Trigger: "manual_test",
		Topic:   "peer collaboration",
	})
	if err != nil {
		t.Fatalf("RoundtableStart 실패: %v", err)
	}

	if _, err := service.SteerRound(ctx, SteerRoundArgs{
		RoundID:    start.Round.ID,
		Actor:      "pm",
		Goal:       "peer route를 통한 의사결정 수렴",
		Priorities: []string{"routing", "closure"},
	}); err != nil {
		t.Fatalf("SteerRound 실패: %v", err)
	}

	routed, err := service.RouteTurn(ctx, RouteTurnArgs{
		FromRole:    "planning",
		ToRoles:     []string{"design"},
		RoundID:     start.Round.ID,
		Intent:      "role_conflict",
		Message:     "design과 우선순위를 맞춰 달라",
		WaitMode:    "completion",
		NeedsReply:  true,
		Priority:    "interrupt",
		Interrupt:   true,
		Codec:       "kv",
		TokenBudget: 48,
	})
	if err != nil {
		t.Fatalf("RouteTurn 실패: %v", err)
	}
	if len(routed.Results) != 1 || routed.Results[0].Role != "design" {
		t.Fatalf("route 결과가 예상과 다름: %#v", routed.Results)
	}

	graph, err := service.ReadRoundGraph(ctx, ReadRoundGraphArgs{RoundID: start.Round.ID})
	if err != nil {
		t.Fatalf("ReadRoundGraph 실패: %v", err)
	}
	if len(graph.Messages) == 0 || len(graph.Edges) == 0 {
		t.Fatalf("graph가 비어 있음: %#v", graph)
	}
	if graph.Edges[0].FromRole != "planning" || graph.Edges[0].ToRole != "design" {
		t.Fatalf("peer edge가 기록되지 않음: %#v", graph.Edges[0])
	}
	if graph.Messages[0].Codec != "kv" || graph.Messages[0].Priority != "interrupt" || !graph.Messages[0].Interrupt {
		t.Fatalf("compact interrupt packet이 기록되지 않음: %#v", graph.Messages[0])
	}
}

func TestServiceDeltaUpdatesHeartbeatAndAckState(t *testing.T) {
	repoRoot := t.TempDir()
	client := NewAppServerClient(helperConfig(repoRoot))
	defer client.Close()

	service, err := NewService(repoRoot, client)
	if err != nil {
		t.Fatalf("NewService 실패: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if _, err := service.BindTargets(ctx, BindTargetsArgs{
		Bindings: map[string]string{"design": "thread-design"},
	}); err != nil {
		t.Fatalf("BindTargets 실패: %v", err)
	}

	service.handleNotification(appServerNotification{
		Method:   "item/agentMessage/delta",
		ThreadID: "thread-design",
		TurnID:   "turn-ack",
		Delta:    "st:ack | eta:75 | more:1 | risk:none | ask:none",
	})

	team, err := service.ReadTeam(ctx, ReadTeamArgs{Role: "design"})
	if err != nil {
		t.Fatalf("ReadTeam 실패: %v", err)
	}
	if team.Raw == nil {
		t.Fatal("team raw state가 비어 있음")
	}
	if team.Raw.ProgressState != "ack" {
		t.Fatalf("progress_state = %q", team.Raw.ProgressState)
	}
	if team.Raw.DeclaredEtaSeconds != 75 {
		t.Fatalf("declared_eta_seconds = %d", team.Raw.DeclaredEtaSeconds)
	}
	if team.Raw.LastStreamAt.IsZero() {
		t.Fatal("last_stream_at가 기록되지 않음")
	}
}
