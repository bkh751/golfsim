package main

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"
)

type Service struct {
	repoRoot string
	store    *Store
	prompts  *PromptBuilder
	app      *AppServerClient

	mu      sync.RWMutex
	targets Targets
}

func NewService(repoRoot string, app *AppServerClient) (*Service, error) {
	store := NewStore(repoRoot)
	if err := store.EnsureDirs(); err != nil {
		return nil, err
	}
	targets, err := store.LoadTargets()
	if err != nil {
		return nil, err
	}
	if targets == nil {
		targets = Targets{}
	}
	svc := &Service{
		repoRoot: repoRoot,
		store:    store,
		prompts:  NewPromptBuilder(repoRoot),
		app:      app,
		targets:  targets,
	}
	app.SetNotificationHandler(svc.handleNotification)
	return svc, nil
}

func (s *Service) DiscoverThreads(ctx context.Context, args DiscoverThreadsArgs) (DiscoverThreadsResult, error) {
	cwd := strings.TrimSpace(args.CWD)
	if cwd == "" {
		cwd = s.repoRoot
	}
	threads, err := s.app.ListThreads(ctx, cwd, strings.TrimSpace(args.SearchTerm))
	if err != nil {
		return DiscoverThreadsResult{}, err
	}
	summaries := make([]ThreadSummary, 0, len(threads))
	for _, thread := range threads {
		summaries = append(summaries, threadSummary(thread))
	}
	sort.Slice(summaries, func(i, j int) bool {
		return summaries[i].UpdatedAt.After(summaries[j].UpdatedAt)
	})
	return DiscoverThreadsResult{Threads: summaries}, nil
}

func (s *Service) BindTargets(ctx context.Context, args BindTargetsArgs) (BindTargetsResult, error) {
	if len(args.Bindings) == 0 {
		return BindTargetsResult{}, fmt.Errorf("bindings가 비어 있습니다")
	}

	currentTargets := s.copyTargets()
	validated := map[string]ThreadSummary{}

	for role, threadID := range args.Bindings {
		if !roleSupported(role) {
			return BindTargetsResult{}, fmt.Errorf("지원하지 않는 role: %s", role)
		}
		thread, err := s.app.ReadThread(ctx, threadID, false)
		if err != nil {
			return BindTargetsResult{}, fmt.Errorf("%s thread 확인 실패: %w", role, err)
		}
		summary := threadSummary(thread)
		validated[role] = summary
		currentTargets[role] = threadID

		if _, err := s.store.UpdateState(role, func(state *TeamState) {
			state.Role = role
			state.ThreadID = threadID
			state.ThreadTitle = summary.Title
			if state.LastStatus == "" {
				state.LastStatus = summary.Status
			}
			state.LastError = ""
		}); err != nil {
			return BindTargetsResult{}, err
		}
	}

	if err := s.store.SaveTargets(currentTargets); err != nil {
		return BindTargetsResult{}, err
	}
	s.setTargets(currentTargets)

	return BindTargetsResult{
		Bindings:  currentTargets,
		Validated: validated,
	}, nil
}

func (s *Service) DispatchTurn(ctx context.Context, args DispatchTurnArgs) (DispatchResult, error) {
	if !roleSupported(args.Role) {
		return DispatchResult{}, fmt.Errorf("지원하지 않는 role: %s", args.Role)
	}
	threadID, ok := s.targetForRole(args.Role)
	if !ok || strings.TrimSpace(threadID) == "" {
		return DispatchResult{}, fmt.Errorf("%s role에 바인딩된 thread가 없습니다", args.Role)
	}

	waitForCompletion := boolValue(args.WaitForCompletion, true)
	prompt, err := s.prompts.Build(ctx, args.Role, args.ParentIssue, args.TaskRequest, args.ConfirmedContext, args.BlockerContext, args.PromptOverride)
	if err != nil {
		return DispatchResult{}, err
	}

	now := time.Now().UTC()
	dispatch := dispatchID(args.Role, now)
	promptPath, err := s.store.WritePromptSnapshot(args.Role, prompt, now)
	if err != nil {
		return DispatchResult{}, err
	}

	thread, err := s.app.ReadThread(ctx, threadID, false)
	if err != nil {
		return DispatchResult{}, fmt.Errorf("dispatch 전 thread 읽기 실패: %w", err)
	}
	title := threadTitle(thread)

	if _, err := s.store.UpdateState(args.Role, func(state *TeamState) {
		state.Role = args.Role
		state.LastDispatchID = dispatch
		state.ThreadID = threadID
		state.ThreadTitle = title
		state.LastStatus = "dispatching"
		state.LastError = ""
	}); err != nil {
		return DispatchResult{}, err
	}

	if err := s.store.AppendDispatch(dispatchEvent{
		Event:       "started",
		DispatchID:  dispatch,
		Role:        args.Role,
		ThreadID:    threadID,
		ThreadTitle: title,
		PromptPath:  promptPath,
		ParentIssue: args.ParentIssue,
		TaskRequest: args.TaskRequest,
		Waited:      waitForCompletion,
		CreatedAt:   now,
	}); err != nil {
		return DispatchResult{}, err
	}

	if _, err := s.app.ResumeThread(ctx, threadID); err != nil {
		s.recordDispatchError(args.Role, dispatch, err)
		return DispatchResult{}, fmt.Errorf("thread/resume 실패: %w", err)
	}
	turn, err := s.app.StartTurn(ctx, threadID, prompt, s.repoRoot)
	if err != nil {
		s.recordDispatchError(args.Role, dispatch, err)
		return DispatchResult{}, fmt.Errorf("turn/start 실패: %w", err)
	}

	if _, err := s.store.UpdateState(args.Role, func(state *TeamState) {
		state.LastTurnID = turn.ID
		state.LastStatus = string(turn.Status)
	}); err != nil {
		return DispatchResult{}, err
	}

	if !waitForCompletion {
		return DispatchResult{
			Role:         args.Role,
			DispatchID:   dispatch,
			ThreadID:     threadID,
			ThreadTitle:  title,
			TurnID:       turn.ID,
			Waited:       false,
			PromptPath:   promptPath,
			LastStatus:   string(turn.Status),
			CompletedNow: false,
		}, nil
	}

	if _, err := s.app.WaitForTurnTerminal(ctx, threadID, turn.ID); err != nil {
		s.recordDispatchError(args.Role, dispatch, err)
		return DispatchResult{}, err
	}
	return s.refreshRoleFromThread(ctx, args.Role, threadID, turn.ID, dispatch, false)
}

func (s *Service) BroadcastTurn(ctx context.Context, args BroadcastTurnArgs) (BroadcastTurnResult, error) {
	roles := args.Roles
	if len(roles) == 0 {
		roles = supportedRoles
	}

	results := make([]DispatchResult, 0, len(roles))
	for _, role := range roles {
		routed, err := s.RouteTurn(ctx, RouteTurnArgs{
			FromRole:   "orchestrator",
			ToRoles:    []string{role},
			Intent:     "wide_impact",
			Message:    args.TaskRequest,
			WaitMode:   "completion",
			NeedsReply: true,
		})
		if err != nil {
			results = append(results, DispatchResult{Role: role, Error: err.Error(), ParseStatus: "dispatch_error"})
			continue
		}
		results = append(results, routed.Results...)
	}
	return BroadcastTurnResult{Results: results}, nil
}

func (s *Service) ReadDashboard(context.Context) (DashboardResult, error) {
	state, err := s.store.LoadState()
	if err != nil {
		return DashboardResult{}, err
	}

	entries := map[string]DashboardEntry{}
	targets := s.copyTargets()
	for _, role := range supportedRoles {
		var current *TeamState
		if value, ok := state[role]; ok {
			if value.ThreadID == "" {
				value.ThreadID = targets[role]
			}
			current = &value
		} else {
			current = &TeamState{
				Role:     role,
				ThreadID: targets[role],
			}
		}
		entries[role] = dashboardEntryFromState(role, current)
	}
	return DashboardResult{Entries: entries}, nil
}

func (s *Service) ReadTeam(ctx context.Context, args ReadTeamArgs) (ReadTeamResult, error) {
	if !roleSupported(args.Role) {
		return ReadTeamResult{}, fmt.Errorf("지원하지 않는 role: %s", args.Role)
	}

	state, err := s.store.LoadState()
	if err != nil {
		return ReadTeamResult{}, err
	}
	var currentState *TeamState
	if value, ok := state[args.Role]; ok {
		copyValue := value
		currentState = &copyValue
	}

	result := ReadTeamResult{
		Role: args.Role,
		Raw:  currentState,
	}
	if currentState != nil {
		entry := dashboardEntryFromState(args.Role, currentState)
		result.State = &entry
	}

	if args.IncludeTurns {
		threadID, ok := s.targetForRole(args.Role)
		if ok && threadID != "" {
			thread, err := s.app.ReadThread(ctx, threadID, true)
			if err != nil {
				return ReadTeamResult{}, err
			}
			result.Thread = &thread
		}
	}
	return result, nil
}

func (s *Service) handleNotification(note appServerNotification) {
	role, ok := s.roleForThreadID(note.ThreadID)
	if !ok {
		return
	}

	switch note.Method {
	case "thread/status/changed":
		_, _ = s.store.UpdateState(role, func(state *TeamState) {
			state.Role = role
			if state.ThreadID == "" {
				state.ThreadID = note.ThreadID
			}
			if note.Status != "" {
				state.LastStatus = note.Status
			}
		})
	case "item/agentMessage/delta":
		_, _ = s.store.UpdateState(role, func(state *TeamState) {
			state.Role = role
			if state.ThreadID == "" {
				state.ThreadID = note.ThreadID
			}
			now := time.Now().UTC()
			state.LastStreamAt = now
			state.StreamText = appendStreamText(state.StreamText, note.Delta)
			if state.LastStatus == "" || state.LastStatus == "dispatching" {
				state.LastStatus = "streaming"
			}
			parsed, _ := ParseTeamResponse(state.StreamText)
			if parsed != nil {
				state.ParseStatus = parsed.ParseStatus
				state.ParseMode = parsed.ParseMode
				state.ParseConfidence = parsed.ParseConfidence
				state.Parsed = parsed
				state.Blocker = parsed.Blocker
				state.NextRequest = parsed.NextRequest
				if parsed.EtaSeconds > 0 {
					state.DeclaredEtaSeconds = parsed.EtaSeconds
				}
				if parsed.ProgressState != "" {
					state.ProgressState = parsed.ProgressState
					state.LastStatus = parsed.ProgressState
				} else if state.LastStatus == "streaming" {
					state.ProgressState = "work"
				}
			}
		})
	case "turn/completed":
		go func() {
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			_, _ = s.refreshRoleFromThread(ctx, role, note.ThreadID, note.TurnID, "", true)
		}()
	}
}

func (s *Service) refreshRoleFromThread(ctx context.Context, role, threadID, turnID, dispatch string, appendCompletionLog bool) (DispatchResult, error) {
	thread, err := s.app.ReadThread(ctx, threadID, true)
	if err != nil {
		return DispatchResult{}, err
	}

	turn, err := selectTurn(thread, turnID)
	if err != nil {
		return DispatchResult{}, err
	}

	finalText := latestAgentMessage(turn)
	parsed, parseErr := ParseTeamResponse(finalText)
	parseStatus := "ok"
	lastStatus := string(turn.Status)
	blocker := ""
	nextRequest := ""
	if parsed != nil {
		parseStatus = parsed.ParseStatus
		if parsed.Status != "" {
			lastStatus = parsed.Status
		}
		blocker = parsed.Blocker
		nextRequest = parsed.NextRequest
	}
	if parseErr != nil && parsed == nil {
		parseStatus = "unparsed"
	}

	updatedAt := time.Now().UTC()
	var completionDispatchID string
	state, err := s.store.UpdateState(role, func(state *TeamState) {
		state.Role = role
		state.ThreadID = thread.ID
		state.ThreadTitle = threadTitle(thread)
		state.LastTurnID = turn.ID
		state.LastStatus = lastStatus
		state.Blocker = blocker
		state.NextRequest = nextRequest
		state.UpdatedAt = updatedAt
		state.ParseStatus = parseStatus
		state.ParseMode = parseStatus
		state.ParseConfidence = 0.25
		state.Freshness = freshnessFromTime(updatedAt)
		state.RiskState = "clear"
		state.Source = "thread"
		state.RequiredRole = requiredRole(role)
		state.LastPeerMessageAt = updatedAt
		state.LastStreamAt = updatedAt
		state.ResponseAcceptRate = 0
		state.StreamText = finalText
		state.RawFinalText = finalText
		state.Parsed = parsed
		if parsed != nil {
			state.ParseMode = parsed.ParseMode
			state.ParseConfidence = parsed.ParseConfidence
			state.RiskState = parsed.ProtocolStatus
			state.DeclaredEtaSeconds = parsed.EtaSeconds
			state.ProgressState = parsed.ProgressState
			if state.ProgressState == "" || state.ProgressState == "ack" || state.ProgressState == "work" {
				state.ProgressState = "final"
			}
			if acceptedParseStatus(parsed.ParseStatus) {
				state.ResponseAcceptRate = 1
			}
		}
		if parseErr != nil {
			state.LastError = parseErr.Error()
		} else {
			state.LastError = ""
		}
		if dispatch != "" {
			state.LastDispatchID = dispatch
		}
		completionDispatchID = state.LastDispatchID
	})
	if err != nil {
		return DispatchResult{}, err
	}

	if appendCompletionLog {
		_ = s.store.AppendDispatch(dispatchEvent{
			Event:       "completed",
			DispatchID:  completionDispatchID,
			Role:        role,
			ThreadID:    thread.ID,
			ThreadTitle: threadTitle(thread),
			TurnID:      turn.ID,
			Waited:      false,
			ParseStatus: parseStatus,
			Error:       errorString(parseErr),
			CompletedAt: updatedAt,
		})
	}

	return DispatchResult{
		Role:         role,
		DispatchID:   state.LastDispatchID,
		ThreadID:     thread.ID,
		ThreadTitle:  threadTitle(thread),
		TurnID:       turn.ID,
		Waited:       true,
		LastStatus:   lastStatus,
		ParseStatus:  parseStatus,
		Parsed:       parsed,
		Error:        errorString(parseErr),
		CompletedNow: true,
	}, nil
}

func appendStreamText(current, delta string) string {
	trimmedDelta := strings.TrimSpace(delta)
	if trimmedDelta == "" {
		return current
	}
	combined := current
	if strings.TrimSpace(combined) == "" {
		combined = trimmedDelta
	} else {
		combined = combined + trimmedDelta
	}
	const maxStreamChars = 2048
	if len(combined) > maxStreamChars {
		return combined[len(combined)-maxStreamChars:]
	}
	return combined
}

func (s *Service) recordDispatchError(role, dispatch string, err error) {
	_, _ = s.store.UpdateState(role, func(state *TeamState) {
		state.Role = role
		state.LastDispatchID = dispatch
		state.LastError = err.Error()
		state.ParseStatus = "dispatch_error"
		state.ParseMode = "dispatch_error"
		state.ParseConfidence = 0
		state.Freshness = freshnessFromTime(state.UpdatedAt)
		state.RiskState = "blocked"
		state.RequiredRole = requiredRole(role)
	})
	_ = s.store.AppendDispatch(dispatchEvent{
		Event:       "completed",
		DispatchID:  dispatch,
		Role:        role,
		Error:       err.Error(),
		ParseStatus: "dispatch_error",
		CompletedAt: time.Now().UTC(),
	})
}

func (s *Service) targetForRole(role string) (string, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	threadID, ok := s.targets[role]
	return threadID, ok
}

func (s *Service) copyTargets() Targets {
	s.mu.RLock()
	defer s.mu.RUnlock()
	copyTargets := Targets{}
	for role, threadID := range s.targets {
		copyTargets[role] = threadID
	}
	return copyTargets
}

func (s *Service) setTargets(targets Targets) {
	s.mu.Lock()
	defer s.mu.Unlock()
	copyTargets := Targets{}
	for role, threadID := range targets {
		copyTargets[role] = threadID
	}
	s.targets = copyTargets
}

func (s *Service) roleForThreadID(threadID string) (string, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for role, boundThreadID := range s.targets {
		if boundThreadID == threadID {
			return role, true
		}
	}
	return "", false
}

func selectTurn(thread AppThread, turnID string) (AppTurn, error) {
	if turnID != "" {
		for _, turn := range thread.Turns {
			if turn.ID == turnID {
				return turn, nil
			}
		}
	}
	if len(thread.Turns) == 0 {
		return AppTurn{}, fmt.Errorf("thread에 turn이 없습니다")
	}
	return thread.Turns[len(thread.Turns)-1], nil
}

func latestAgentMessage(turn AppTurn) string {
	lastAny := ""
	lastFinal := ""
	for _, item := range turn.Items {
		if item.Type != "agentMessage" {
			continue
		}
		text := strings.TrimSpace(item.Text)
		if text == "" {
			continue
		}
		lastAny = text
		if item.Phase == nil || strings.EqualFold(*item.Phase, "final") {
			lastFinal = text
		}
	}
	if lastFinal != "" {
		return lastFinal
	}
	return lastAny
}

func errorString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
