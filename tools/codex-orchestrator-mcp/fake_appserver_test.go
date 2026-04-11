package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestHelperProcessAppServer(t *testing.T) {
	if os.Getenv("GO_WANT_HELPER_PROCESS") != "1" {
		return
	}
	runFakeAppServer()
	os.Exit(0)
}

type fakeThreadState struct {
	thread AppThread
}

type fakeAppServer struct {
	mu          sync.Mutex
	writer      *bufio.Writer
	threads     map[string]*fakeThreadState
	turnCounter int
}

func runFakeAppServer() {
	cwd := os.Getenv("FAKE_APP_SERVER_CWD")
	if cwd == "" {
		cwd = "/tmp/golfsim"
	}

	pmTitle := "PM Team"
	planningTitle := "Planning Team"
	designTitle := "Design Team"
	devTitle := "Dev Team"
	qaTitle := "Gameplay QA Team"
	server := &fakeAppServer{
		writer: bufio.NewWriter(os.Stdout),
		threads: map[string]*fakeThreadState{
			"thread-pm": {
				thread: AppThread{
					ID:        "thread-pm",
					Preview:   "pm preview",
					CreatedAt: time.Now().Unix(),
					UpdatedAt: time.Now().Unix(),
					Status:    "idle",
					CWD:       cwd,
					Name:      &pmTitle,
				},
			},
			"thread-planning": {
				thread: AppThread{
					ID:        "thread-planning",
					Preview:   "planning preview",
					CreatedAt: time.Now().Unix(),
					UpdatedAt: time.Now().Unix(),
					Status:    "idle",
					CWD:       cwd,
					Name:      &planningTitle,
				},
			},
			"thread-design": {
				thread: AppThread{
					ID:        "thread-design",
					Preview:   "design preview",
					CreatedAt: time.Now().Unix(),
					UpdatedAt: time.Now().Unix(),
					Status:    "idle",
					CWD:       cwd,
					Name:      &designTitle,
				},
			},
			"thread-dev": {
				thread: AppThread{
					ID:        "thread-dev",
					Preview:   "dev preview",
					CreatedAt: time.Now().Unix(),
					UpdatedAt: time.Now().Unix(),
					Status:    "idle",
					CWD:       cwd,
					Name:      &devTitle,
				},
			},
			"thread-gameplay_qa": {
				thread: AppThread{
					ID:        "thread-gameplay_qa",
					Preview:   "qa preview",
					CreatedAt: time.Now().Unix(),
					UpdatedAt: time.Now().Unix(),
					Status:    "idle",
					CWD:       cwd,
					Name:      &qaTitle,
				},
			},
		},
	}

	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 1024), 10*1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var request rpcRequest
		if err := json.Unmarshal([]byte(line), &request); err != nil {
			continue
		}
		server.handleRequest(request)
	}
}

func (s *fakeAppServer) handleRequest(request rpcRequest) {
	switch request.Method {
	case "initialize":
		s.respond(request.ID, map[string]any{
			"serverInfo": map[string]any{"name": "fake-app-server"},
		})
	case "initialized":
	case "thread/list":
		var params struct {
			CWD        string `json:"cwd"`
			SearchTerm string `json:"searchTerm"`
		}
		_ = decodeInto(request.Params, &params)

		s.mu.Lock()
		threads := make([]AppThread, 0, len(s.threads))
		for _, state := range s.threads {
			if params.CWD != "" && state.thread.CWD != params.CWD {
				continue
			}
			title := strings.ToLower(threadTitle(state.thread) + " " + state.thread.Preview)
			if params.SearchTerm != "" && !strings.Contains(title, strings.ToLower(params.SearchTerm)) {
				continue
			}
			copyThread := state.thread
			copyThread.Turns = nil
			threads = append(threads, copyThread)
		}
		s.mu.Unlock()

		s.respond(request.ID, map[string]any{
			"data":       threads,
			"nextCursor": nil,
		})
	case "thread/read":
		var params struct {
			ThreadID     string `json:"threadId"`
			IncludeTurns bool   `json:"includeTurns"`
		}
		_ = decodeInto(request.Params, &params)
		s.mu.Lock()
		state := s.threads[params.ThreadID]
		copyThread := state.thread
		if !params.IncludeTurns {
			copyThread.Turns = nil
		}
		s.mu.Unlock()
		s.respond(request.ID, map[string]any{"thread": copyThread})
	case "thread/resume":
		var params struct {
			ThreadID string `json:"threadId"`
		}
		_ = decodeInto(request.Params, &params)
		s.mu.Lock()
		copyThread := s.threads[params.ThreadID].thread
		s.mu.Unlock()
		s.respond(request.ID, map[string]any{"thread": copyThread})
	case "turn/start":
		var params struct {
			ThreadID string `json:"threadId"`
		}
		_ = decodeInto(request.Params, &params)

		s.mu.Lock()
		s.turnCounter++
		turnID := fmt.Sprintf("turn-%d", s.turnCounter)
		state := s.threads[params.ThreadID]
		state.thread.Status = "running"
		state.thread.UpdatedAt = time.Now().Unix()
		s.mu.Unlock()

		s.respond(request.ID, map[string]any{
			"turn": AppTurn{
				ID:     turnID,
				Status: "running",
				Items:  []AppThreadItem{},
			},
		})

		go func() {
			time.Sleep(10 * time.Millisecond)
			s.notify("thread/status/changed", map[string]any{
				"threadId": params.ThreadID,
				"status":   "running",
			})
			s.notify("item/agentMessage/delta", map[string]any{
				"threadId": params.ThreadID,
				"turnId":   turnID,
				"itemId":   "agent-1",
				"delta":    "상태:",
			})

			finalText := `상태: 진행 가능
이해한 범위: fake app-server dispatch 확인
결과: thread 라우팅과 응답 파싱을 검증했다
blocker: 없음
다음 요청: 없음`

			s.mu.Lock()
			state := s.threads[params.ThreadID]
			state.thread.Status = "idle"
			state.thread.UpdatedAt = time.Now().Unix()
			state.thread.Turns = append(state.thread.Turns, AppTurn{
				ID:     turnID,
				Status: "completed",
				Items: []AppThreadItem{
					{
						Type:  "agentMessage",
						ID:    "agent-1",
						Text:  finalText,
						Phase: nil,
					},
				},
			})
			s.mu.Unlock()

			s.notify("turn/completed", map[string]any{
				"threadId": params.ThreadID,
				"turn": map[string]any{
					"id":     turnID,
					"status": "completed",
					"items":  []any{},
					"error":  nil,
				},
			})
		}()
	}
}

func (s *fakeAppServer) respond(id interface{}, result interface{}) {
	s.write(map[string]any{
		"jsonrpc": "2.0",
		"id":      id,
		"result":  result,
	})
}

func (s *fakeAppServer) notify(method string, params interface{}) {
	s.write(map[string]any{
		"jsonrpc": "2.0",
		"method":  method,
		"params":  params,
	})
}

func (s *fakeAppServer) write(payload interface{}) {
	bytes, _ := json.Marshal(payload)
	bytes = append(bytes, '\n')

	s.mu.Lock()
	defer s.mu.Unlock()
	_, _ = s.writer.Write(bytes)
	_ = s.writer.Flush()
}
