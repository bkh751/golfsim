package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestStoreRoundTrip(t *testing.T) {
	repoRoot := t.TempDir()
	store := NewStore(repoRoot)
	if err := store.EnsureDirs(); err != nil {
		t.Fatalf("EnsureDirs 실패: %v", err)
	}

	targets := Targets{"pm": "thread-pm"}
	if err := store.SaveTargets(targets); err != nil {
		t.Fatalf("SaveTargets 실패: %v", err)
	}
	loadedTargets, err := store.LoadTargets()
	if err != nil {
		t.Fatalf("LoadTargets 실패: %v", err)
	}
	if loadedTargets["pm"] != "thread-pm" {
		t.Fatalf("targets round trip 실패: %#v", loadedTargets)
	}

	if _, err := store.UpdateState("pm", func(state *TeamState) {
		state.ThreadID = "thread-pm"
		state.LastStatus = "진행 중"
		state.UpdatedAt = time.Now().UTC()
	}); err != nil {
		t.Fatalf("UpdateState 실패: %v", err)
	}
	loadedState, err := store.LoadState()
	if err != nil {
		t.Fatalf("LoadState 실패: %v", err)
	}
	if loadedState["pm"].LastStatus != "진행 중" {
		t.Fatalf("state round trip 실패: %#v", loadedState["pm"])
	}

	promptPath, err := store.WritePromptSnapshot("pm", "hello", time.Unix(1712600000, 0).UTC())
	if err != nil {
		t.Fatalf("WritePromptSnapshot 실패: %v", err)
	}
	if !strings.Contains(promptPath, filepath.Join(".codex", "orchestrator", "prompts")) {
		t.Fatalf("prompt path가 예상과 다름: %s", promptPath)
	}
	if _, err := os.Stat(promptPath); err != nil {
		t.Fatalf("prompt snapshot 파일이 없음: %v", err)
	}

	if err := store.AppendDispatch(dispatchEvent{
		Event:      "started",
		DispatchID: "pm-1",
		Role:       "pm",
		CreatedAt:  time.Now().UTC(),
	}); err != nil {
		t.Fatalf("AppendDispatch 실패: %v", err)
	}
	payload, err := os.ReadFile(filepath.Join(repoRoot, ".codex", "orchestrator", "dispatches.jsonl"))
	if err != nil {
		t.Fatalf("dispatches.jsonl 읽기 실패: %v", err)
	}
	if !strings.Contains(string(payload), `"dispatch_id":"pm-1"`) {
		t.Fatalf("dispatch log 내용이 예상과 다름: %s", string(payload))
	}
}

func TestStoreRoundRequestDedupesPendingRounds(t *testing.T) {
	repoRoot := t.TempDir()
	store := NewStore(repoRoot)
	if err := store.EnsureDirs(); err != nil {
		t.Fatalf("EnsureDirs 실패: %v", err)
	}

	args := RoundtableStartArgs{
		IssueRef:     "#24",
		Trigger:      "stop_hook",
		ChangedFiles: []string{"index.html", "test/ui-interaction.test.mjs"},
		Topic:        "UI/플레이 루프",
	}
	first, dedupeHit, err := store.CreateRoundRequest(args, "test")
	if err != nil {
		t.Fatalf("CreateRoundRequest 첫 호출 실패: %v", err)
	}
	second, dedupeHitSecond, err := store.CreateRoundRequest(args, "test")
	if err != nil {
		t.Fatalf("CreateRoundRequest 두 번째 호출 실패: %v", err)
	}

	if dedupeHit {
		t.Fatal("첫 라운드 생성에서 dedupeHit=true 이면 안 됨")
	}
	if !dedupeHitSecond {
		t.Fatal("중복 라운드 생성에서 dedupeHit=true 이어야 함")
	}
	if first.ID != second.ID {
		t.Fatalf("중복 라운드 ID가 다름: %s vs %s", first.ID, second.ID)
	}

	rounds, err := store.ListRounds(0)
	if err != nil {
		t.Fatalf("ListRounds 실패: %v", err)
	}
	if len(rounds) != 1 {
		t.Fatalf("round 개수 = %d, 1이어야 함", len(rounds))
	}
	if rounds[0].Status != "pending" {
		t.Fatalf("round status = %s", rounds[0].Status)
	}
}
