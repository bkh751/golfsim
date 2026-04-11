package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type AppServerClient struct {
	config AppServerConfig

	mu            sync.Mutex
	cmd           *exec.Cmd
	stdin         io.WriteCloser
	pending       map[string]chan rpcCallResult
	waiters       map[string][]chan appTurnCompleted
	completed     map[string]appTurnCompleted
	notifyHandler func(appServerNotification)
	nextID        int64
	initialized   bool
	starting      bool
	startReady    chan error
}

func NewAppServerClient(config AppServerConfig) *AppServerClient {
	return &AppServerClient{
		config:    config,
		pending:   map[string]chan rpcCallResult{},
		waiters:   map[string][]chan appTurnCompleted{},
		completed: map[string]appTurnCompleted{},
	}
}

func (c *AppServerClient) Close() {
	c.markDead(io.EOF)
}

func (c *AppServerClient) SetNotificationHandler(handler func(appServerNotification)) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.notifyHandler = handler
}

func (c *AppServerClient) ListThreads(ctx context.Context, cwd, searchTerm string) ([]AppThread, error) {
	threads := make([]AppThread, 0)
	var cursor *string
	for {
		params := map[string]any{
			"limit": 100,
			"cwd":   cwd,
		}
		if cursor != nil {
			params["cursor"] = *cursor
		}
		if strings.TrimSpace(searchTerm) != "" {
			params["searchTerm"] = searchTerm
		}

		var response AppThreadListResponse
		if err := c.call(ctx, "thread/list", params, &response); err != nil {
			return nil, err
		}
		threads = append(threads, response.Data...)
		if response.NextCursor == nil || *response.NextCursor == "" {
			return threads, nil
		}
		cursor = response.NextCursor
	}
}

func (c *AppServerClient) ReadThread(ctx context.Context, threadID string, includeTurns bool) (AppThread, error) {
	var response AppThreadReadResponse
	err := c.call(ctx, "thread/read", map[string]any{
		"threadId":     threadID,
		"includeTurns": includeTurns,
	}, &response)
	return response.Thread, err
}

func (c *AppServerClient) ResumeThread(ctx context.Context, threadID string) (AppThread, error) {
	var response struct {
		Thread AppThread `json:"thread"`
	}
	err := c.call(ctx, "thread/resume", map[string]any{
		"threadId":               threadID,
		"persistExtendedHistory": false,
	}, &response)
	return response.Thread, err
}

func (c *AppServerClient) StartTurn(ctx context.Context, threadID, prompt, cwd string) (AppTurn, error) {
	var response AppTurnStartResponse
	err := c.call(ctx, "turn/start", map[string]any{
		"threadId": threadID,
		"cwd":      cwd,
		"input": []map[string]any{
			{
				"type":          "text",
				"text":          prompt,
				"text_elements": []map[string]any{},
			},
		},
	}, &response)
	return response.Turn, err
}

func (c *AppServerClient) WaitForTurnCompletion(ctx context.Context, threadID, turnID string) error {
	key := c.turnKey(threadID, turnID)

	c.mu.Lock()
	if completed, ok := c.completed[key]; ok {
		c.mu.Unlock()
		return completedError(completed)
	}
	ch := make(chan appTurnCompleted, 1)
	c.waiters[key] = append(c.waiters[key], ch)
	c.mu.Unlock()

	select {
	case <-ctx.Done():
		c.removeWaiter(key, ch)
		return ctx.Err()
	case completed := <-ch:
		return completedError(completed)
	}
}

func (c *AppServerClient) WaitForTurnTerminal(ctx context.Context, threadID, turnID string) (AppTurn, error) {
	waitCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	if err := c.WaitForTurnCompletion(waitCtx, threadID, turnID); err == nil {
		thread, readErr := c.ReadThread(ctx, threadID, true)
		if readErr != nil {
			return AppTurn{}, readErr
		}
		return selectTurn(thread, turnID)
	}

	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		thread, err := c.ReadThread(ctx, threadID, true)
		if err == nil {
			turn, turnErr := selectTurn(thread, turnID)
			if turnErr == nil && !strings.EqualFold(string(turn.Status), "inProgress") && !strings.EqualFold(string(turn.Status), "running") {
				if strings.EqualFold(string(turn.Status), "failed") {
					return AppTurn{}, fmt.Errorf("turn 실패: %s", string(turn.Status))
				}
				return turn, nil
			}
		}

		select {
		case <-ctx.Done():
			return AppTurn{}, ctx.Err()
		case <-ticker.C:
		}
	}
}

func (c *AppServerClient) call(ctx context.Context, method string, params any, out any) error {
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		if err := c.ensureStarted(ctx); err != nil {
			return err
		}

		result, err := c.request(ctx, method, params)
		if err == nil {
			if out == nil {
				return nil
			}
			if len(result) == 0 {
				return nil
			}
			if err := json.Unmarshal(result, out); err != nil {
				return fmt.Errorf("%s 응답 해석 실패: %w", method, err)
			}
			return nil
		}

		lastErr = err
		c.markDead(err)
	}
	return lastErr
}

func (c *AppServerClient) ensureStarted(ctx context.Context) error {
	c.mu.Lock()
	if c.cmd != nil && c.initialized {
		c.mu.Unlock()
		return nil
	}
	if c.starting {
		ready := c.startReady
		c.mu.Unlock()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case err := <-ready:
			return err
		}
	}

	c.starting = true
	c.startReady = make(chan error, 1)
	ready := c.startReady
	c.mu.Unlock()

	err := c.startAndInitialize(ctx)

	c.mu.Lock()
	c.starting = false
	if err == nil {
		c.initialized = true
	}
	c.startReady = nil
	c.mu.Unlock()

	ready <- err
	close(ready)
	return err
}

func (c *AppServerClient) startAndInitialize(ctx context.Context) error {
	cmd := exec.CommandContext(context.Background(), c.config.Command, c.config.Args...)
	cmd.Dir = c.config.RepoRoot
	if len(c.config.Env) > 0 {
		cmd.Env = append(os.Environ(), c.config.Env...)
	}

	stdin, err := cmd.StdinPipe()
	if err != nil {
		return err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return err
	}
	if err := cmd.Start(); err != nil {
		return err
	}

	c.mu.Lock()
	c.cmd = cmd
	c.stdin = stdin
	c.pending = map[string]chan rpcCallResult{}
	c.waiters = map[string][]chan appTurnCompleted{}
	c.initialized = false
	c.mu.Unlock()

	go c.readLoop(stdout)
	go io.Copy(os.Stderr, stderr)
	go func() {
		err := cmd.Wait()
		if err != nil && !errors.Is(err, io.EOF) {
			log.Printf("app-server 종료: %v", err)
		}
		c.markDead(err)
	}()

	if _, err := c.requestRaw(ctx, "initialize", map[string]any{
		"clientInfo": map[string]any{
			"name":    serverName,
			"version": serverVersion,
		},
		"capabilities": map[string]any{},
	}); err != nil {
		return err
	}
	return c.notify("initialized", map[string]any{})
}

func (c *AppServerClient) request(ctx context.Context, method string, params any) (json.RawMessage, error) {
	return c.requestRaw(ctx, method, params)
}

func (c *AppServerClient) requestRaw(ctx context.Context, method string, params any) (json.RawMessage, error) {
	id := atomic.AddInt64(&c.nextID, 1)
	idString := fmt.Sprintf("%d", id)
	ch := make(chan rpcCallResult, 1)

	req := rpcRequest{
		JSONRPC: "2.0",
		ID:      idString,
		Method:  method,
		Params:  params,
	}
	payload, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	payload = append(payload, '\n')

	c.mu.Lock()
	if c.stdin == nil {
		c.mu.Unlock()
		return nil, fmt.Errorf("app-server stdin이 없습니다")
	}
	c.pending[idString] = ch
	stdin := c.stdin
	c.mu.Unlock()

	if _, err := stdin.Write(payload); err != nil {
		c.mu.Lock()
		delete(c.pending, idString)
		c.mu.Unlock()
		return nil, err
	}

	select {
	case <-ctx.Done():
		c.mu.Lock()
		delete(c.pending, idString)
		c.mu.Unlock()
		return nil, ctx.Err()
	case result, ok := <-ch:
		if !ok {
			return nil, fmt.Errorf("%s 응답 채널이 닫혔습니다", method)
		}
		return result.Result, result.Err
	}
}

func (c *AppServerClient) notify(method string, params any) error {
	req := rpcRequest{
		JSONRPC: "2.0",
		Method:  method,
		Params:  params,
	}
	payload, err := json.Marshal(req)
	if err != nil {
		return err
	}
	payload = append(payload, '\n')

	c.mu.Lock()
	defer c.mu.Unlock()
	if c.stdin == nil {
		return fmt.Errorf("app-server stdin이 없습니다")
	}
	_, err = c.stdin.Write(payload)
	return err
}

func (c *AppServerClient) readLoop(stdout io.Reader) {
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 1024), 10*1024*1024)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		var envelope rpcEnvelope
		if err := json.Unmarshal([]byte(line), &envelope); err != nil {
			log.Printf("app-server 응답 파싱 실패: %v", err)
			continue
		}

		if envelope.ID != nil && len(*envelope.ID) > 0 {
			c.handleResponse(envelope)
			continue
		}
		if envelope.Method != "" {
			c.handleNotification(envelope)
		}
	}

	if err := scanner.Err(); err != nil {
		c.markDead(err)
		return
	}
	c.markDead(io.EOF)
}

func (c *AppServerClient) handleResponse(envelope rpcEnvelope) {
	id := normalizeID(*envelope.ID)

	c.mu.Lock()
	ch, ok := c.pending[id]
	if ok {
		delete(c.pending, id)
	}
	c.mu.Unlock()
	if !ok {
		return
	}

	defer close(ch)
	if envelope.Error != nil {
		ch <- rpcCallResult{Err: fmt.Errorf("rpc error %d: %s", envelope.Error.Code, envelope.Error.Message)}
		return
	}
	ch <- rpcCallResult{Result: envelope.Result}
}

func (c *AppServerClient) handleNotification(envelope rpcEnvelope) {
	switch envelope.Method {
	case "turn/completed":
		var payload appTurnCompleted
		if err := json.Unmarshal(envelope.Params, &payload); err != nil {
			return
		}
		key := c.turnKey(payload.ThreadID, payload.Turn.ID)

		c.mu.Lock()
		c.completed[key] = payload
		waiters := c.waiters[key]
		delete(c.waiters, key)
		handler := c.notifyHandler
		c.mu.Unlock()

		for _, ch := range waiters {
			ch <- payload
			close(ch)
		}
		if handler != nil {
			handler(appServerNotification{
				Method:   envelope.Method,
				ThreadID: payload.ThreadID,
				TurnID:   payload.Turn.ID,
				Status:   string(payload.Turn.Status),
			})
		}
	case "thread/status/changed":
		var payload appThreadStatusChanged
		if err := json.Unmarshal(envelope.Params, &payload); err != nil {
			return
		}
		c.mu.Lock()
		handler := c.notifyHandler
		c.mu.Unlock()
		if handler != nil {
			handler(appServerNotification{
				Method:   envelope.Method,
				ThreadID: payload.ThreadID,
				Status:   payload.Status,
			})
		}
	case "item/agentMessage/delta":
		var payload appAgentMessageDelta
		if err := json.Unmarshal(envelope.Params, &payload); err != nil {
			return
		}
		c.mu.Lock()
		handler := c.notifyHandler
		c.mu.Unlock()
		if handler != nil {
			handler(appServerNotification{
				Method:   envelope.Method,
				ThreadID: payload.ThreadID,
				TurnID:   payload.TurnID,
				Delta:    payload.Delta,
			})
		}
	}
}

func (c *AppServerClient) removeWaiter(key string, target chan appTurnCompleted) {
	c.mu.Lock()
	defer c.mu.Unlock()
	waiters := c.waiters[key]
	kept := waiters[:0]
	for _, waiter := range waiters {
		if waiter != target {
			kept = append(kept, waiter)
		}
	}
	if len(kept) == 0 {
		delete(c.waiters, key)
		return
	}
	c.waiters[key] = kept
}

func (c *AppServerClient) markDead(reason error) {
	c.mu.Lock()
	cmd := c.cmd
	stdin := c.stdin
	pending := c.pending
	waiters := c.waiters
	c.cmd = nil
	c.stdin = nil
	c.pending = map[string]chan rpcCallResult{}
	c.waiters = map[string][]chan appTurnCompleted{}
	c.initialized = false
	c.mu.Unlock()

	if stdin != nil {
		_ = stdin.Close()
	}
	if cmd != nil && cmd.Process != nil {
		_ = cmd.Process.Kill()
	}

	err := reason
	if err == nil {
		err = fmt.Errorf("app-server가 종료되었습니다")
	}

	for _, ch := range pending {
		ch <- rpcCallResult{Err: err}
		close(ch)
	}
	for _, waitersForTurn := range waiters {
		for _, ch := range waitersForTurn {
			close(ch)
		}
	}
}

func (c *AppServerClient) turnKey(threadID, turnID string) string {
	return threadID + "::" + turnID
}

func completedError(payload appTurnCompleted) error {
	if strings.EqualFold(string(payload.Turn.Status), "failed") {
		return fmt.Errorf("turn 실패: %s", string(payload.Turn.Status))
	}
	return nil
}

func normalizeID(raw json.RawMessage) string {
	if len(raw) == 0 {
		return ""
	}
	var asString string
	if err := json.Unmarshal(raw, &asString); err == nil {
		return asString
	}
	return string(raw)
}
