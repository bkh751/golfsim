package main

import (
	"context"
	"os"
	"testing"
	"time"
)

func helperConfig(repoRoot string) AppServerConfig {
	return AppServerConfig{
		Command:  os.Args[0],
		Args:     []string{"-test.run=TestHelperProcessAppServer"},
		RepoRoot: repoRoot,
		Env: []string{
			"GO_WANT_HELPER_PROCESS=1",
			"FAKE_APP_SERVER_CWD=" + repoRoot,
		},
	}
}

func TestAppServerClientListAndDispatch(t *testing.T) {
	repoRoot := t.TempDir()
	client := NewAppServerClient(helperConfig(repoRoot))
	defer client.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	threads, err := client.ListThreads(ctx, repoRoot, "PM")
	if err != nil {
		t.Fatalf("ListThreads 실패: %v", err)
	}
	if len(threads) != 1 || threads[0].ID != "thread-pm" {
		t.Fatalf("thread 검색 결과가 예상과 다름: %#v", threads)
	}

	if _, err := client.ResumeThread(ctx, "thread-pm"); err != nil {
		t.Fatalf("ResumeThread 실패: %v", err)
	}

	turn, err := client.StartTurn(ctx, "thread-pm", "ping", repoRoot)
	if err != nil {
		t.Fatalf("StartTurn 실패: %v", err)
	}
	if turn.ID == "" {
		t.Fatal("turn id가 비어 있음")
	}

	if err := client.WaitForTurnCompletion(ctx, "thread-pm", turn.ID); err != nil {
		t.Fatalf("WaitForTurnCompletion 실패: %v", err)
	}

	thread, err := client.ReadThread(ctx, "thread-pm", true)
	if err != nil {
		t.Fatalf("ReadThread 실패: %v", err)
	}
	if len(thread.Turns) == 0 {
		t.Fatal("완료된 turn이 저장되지 않음")
	}
	if got := latestAgentMessage(thread.Turns[len(thread.Turns)-1]); got == "" {
		t.Fatal("final agent message가 비어 있음")
	}
}
