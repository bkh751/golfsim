package main

import (
	"context"
	"fmt"
	"strings"
	"time"
)

func (s *Service) RoundtableStart(ctx context.Context, args RoundtableStartArgs) (RoundtableStartResult, error) {
	_ = ctx
	if strings.TrimSpace(args.Trigger) == "" {
		return RoundtableStartResult{}, fmt.Errorf("trigger가 비어 있습니다")
	}
	round, dedupeHit, err := s.store.CreateRoundRequest(args, "manual")
	if err != nil {
		return RoundtableStartResult{}, err
	}
	return RoundtableStartResult{
		Round:     round,
		DedupeHit: dedupeHit,
		Enqueued:  !dedupeHit,
	}, nil
}

func (s *Service) RoundtableRead(ctx context.Context, args RoundtableReadArgs) (RoundtableReadResult, error) {
	_ = ctx
	if strings.TrimSpace(args.RoundID) == "" {
		return RoundtableReadResult{}, fmt.Errorf("round_id가 비어 있습니다")
	}
	round, err := s.store.LoadRound(args.RoundID)
	if err != nil {
		return RoundtableReadResult{}, err
	}
	return RoundtableReadResult{Round: round}, nil
}

func (s *Service) RoundtableList(ctx context.Context, args RoundtableListArgs) (RoundtableListResult, error) {
	_ = ctx
	rounds, err := s.store.ListRounds(args.Limit)
	if err != nil {
		return RoundtableListResult{}, err
	}
	return RoundtableListResult{Rounds: rounds}, nil
}

func (s *Service) RouteTurn(ctx context.Context, args RouteTurnArgs) (RouteTurnResult, error) {
	if len(args.ToRoles) == 0 {
		return RouteTurnResult{}, fmt.Errorf("to_roles가 비어 있습니다")
	}
	fromRole := strings.TrimSpace(args.FromRole)
	if fromRole == "" {
		fromRole = "orchestrator"
	}
	if len(args.ToRoles) > 1 && !broadcastAllowed(args.Intent) {
		return RouteTurnResult{}, fmt.Errorf("broadcast는 role_conflict, wide_impact, policy_change intent에서만 허용됩니다")
	}

	waitForCompletion := strings.TrimSpace(args.WaitMode) != "none"
	now := time.Now().UTC()
	codec := normalizeCodec(args.Codec)
	priority := normalizePriority(args.Priority)
	interrupt := args.Interrupt || priority == "interrupt"
	lane := normalizeLane(firstNonEmptyString(strings.TrimSpace(args.Lane), interruptLane(interrupt, priority)))
	compressionHint := strings.TrimSpace(args.CompressionHint)
	result := RouteTurnResult{
		RoundID:         strings.TrimSpace(args.RoundID),
		MessageID:       messageID("msg", now),
		Priority:        priority,
		Interrupt:       interrupt,
		Codec:           codec,
		TokenBudget:     args.TokenBudget,
		CompressionHint: compressionHint,
		Lane:            lane,
		Results:         make([]DispatchResult, 0, len(args.ToRoles)),
	}

	var round *RoundArtifact
	if result.RoundID != "" {
		loaded, err := s.store.LoadRound(result.RoundID)
		if err != nil {
			return RouteTurnResult{}, err
		}
		if loaded == nil {
			return RouteTurnResult{}, fmt.Errorf("round를 찾을 수 없습니다: %s", result.RoundID)
		}
		round = loaded
		if result.TokenBudget <= 0 && round.Policy.Budget.MaxTokensPerPacket > 0 {
			result.TokenBudget = round.Policy.Budget.MaxTokensPerPacket
		}
		if result.Codec == "plain" && strings.TrimSpace(args.Codec) == "" && round.Policy.DefaultCodec != "" {
			result.Codec = normalizeCodec(round.Policy.DefaultCodec)
		}
		if result.Priority == "normal" && strings.TrimSpace(args.Priority) == "" && round.Policy.DefaultPriority != "" {
			result.Priority = normalizePriority(round.Policy.DefaultPriority)
			result.Interrupt = result.Interrupt || result.Priority == "interrupt"
			result.Lane = normalizeLane(firstNonEmptyString(result.Lane, interruptLane(result.Interrupt, result.Priority)))
		}
		if result.CompressionHint == "" && result.Codec != "plain" {
			result.CompressionHint = "primitive"
		}
		outbound := RoundMessage{
			MessageID:       result.MessageID,
			RoundID:         round.ID,
			FromRole:        fromRole,
			ToRoles:         uniqueRoles(args.ToRoles),
			ReplyTo:         strings.TrimSpace(args.ReplyTo),
			Intent:          strings.TrimSpace(args.Intent),
			Summary:         strings.TrimSpace(args.Message),
			NeedsReply:      args.NeedsReply,
			ProtocolStatus:  "accepted",
			Priority:        result.Priority,
			Interrupt:       result.Interrupt,
			Codec:           result.Codec,
			TokenBudget:     result.TokenBudget,
			CompressionHint: result.CompressionHint,
			Lane:            result.Lane,
			ParseMode:       "direct",
			CreatedAt:       now,
		}
		round.Messages = append(round.Messages, outbound)
		if args.NeedsReply && len(outbound.ToRoles) == 1 {
			question := RoundQuestion{
				ID:              messageID("question", now),
				RoundID:         round.ID,
				FromRole:        fromRole,
				ToRoles:         outbound.ToRoles,
				Intent:          outbound.Intent,
				MessageID:       outbound.MessageID,
				Status:          "open",
				HopCount:        1,
				ReplyCount:      0,
				UnansweredCount: 0,
				Priority:        result.Priority,
				Interrupt:       result.Interrupt,
				Codec:           result.Codec,
				TokenBudget:     result.TokenBudget,
				Lane:            result.Lane,
				CreatedAt:       now,
			}
			applyQuestionPolicy(round, &question, "initial")
			result.OpenQuestionID = question.ID
			round.OpenQuestions = append(round.OpenQuestions, question)
		}
	}

	for _, target := range uniqueRoles(args.ToRoles) {
		roleWait := waitForCompletion
		dispatch, err := s.DispatchTurn(ctx, DispatchTurnArgs{
			Role:              target,
			ParentIssue:       roundIssue(round),
			TaskRequest:       fmt.Sprintf("%s -> %s (%s)", fromRole, target, strings.TrimSpace(args.Intent)),
			PromptOverride:    buildPeerPrompt(fromRole, target, result.RoundID, args.Intent, args.Message, args.NeedsReply, args.ReplyTo, result.Codec, result.Priority, result.Interrupt, result.TokenBudget, result.CompressionHint, result.Lane),
			WaitForCompletion: &roleWait,
		})
		if err != nil {
			result.Results = append(result.Results, DispatchResult{
				Role:        target,
				ParseStatus: "dispatch_error",
				Error:       err.Error(),
			})
			if round != nil {
				round.Edges = append(round.Edges, RoundEdge{
					ID:        messageID("edge", time.Now().UTC()),
					RoundID:   round.ID,
					FromRole:  fromRole,
					ToRole:    target,
					MessageID: result.MessageID,
					Intent:    strings.TrimSpace(args.Intent),
					Accepted:  false,
					Status:    "warn",
					Priority:  result.Priority,
					Interrupt: result.Interrupt,
					Codec:     result.Codec,
					Lane:      result.Lane,
					CreatedAt: time.Now().UTC(),
				})
				incrementQuestionUnanswered(round, result.OpenQuestionID)
			}
			continue
		}
		result.Results = append(result.Results, dispatch)
		if round == nil {
			continue
		}

		accepted := acceptedParseStatus(dispatch.ParseStatus)
		round.Edges = append(round.Edges, RoundEdge{
			ID:        messageID("edge", time.Now().UTC()),
			RoundID:   round.ID,
			FromRole:  fromRole,
			ToRole:    target,
			MessageID: result.MessageID,
			ReplyTo:   strings.TrimSpace(args.ReplyTo),
			Intent:    strings.TrimSpace(args.Intent),
			Accepted:  accepted,
			Status:    edgeStatus(dispatch),
			Priority:  result.Priority,
			Interrupt: result.Interrupt,
			Codec:     result.Codec,
			Lane:      result.Lane,
			CreatedAt: time.Now().UTC(),
		})
		if dispatch.Parsed != nil {
			reply := parsedToRoundMessage(round.ID, dispatch.Role, fromRole, dispatch.Parsed, time.Now().UTC())
			round.Messages = append(round.Messages, reply)
			if args.NeedsReply && result.OpenQuestionID != "" && len(args.ToRoles) == 1 {
				registerQuestionReply(round, result.OpenQuestionID, accepted)
				if accepted && !dispatch.Parsed.NeedsReply {
					resolveRoundQuestion(round, result.OpenQuestionID, dispatch.Parsed.Summary, target, "reply")
				}
			}
			if dispatch.Parsed.NeedsReply {
				question := RoundQuestion{
					ID:              messageID("question", time.Now().UTC()),
					RoundID:         round.ID,
					FromRole:        target,
					ToRoles:         []string{fromRole},
					Intent:          dispatch.Parsed.Intent,
					MessageID:       reply.MessageID,
					Status:          "open",
					HopCount:        followUpHopCount(round, result.OpenQuestionID),
					ReplyCount:      0,
					UnansweredCount: 0,
					Priority:        dispatch.Parsed.Priority,
					Interrupt:       dispatch.Parsed.Interrupt,
					Codec:           dispatch.Parsed.Codec,
					TokenBudget:     dispatch.Parsed.TokenBudget,
					Lane:            dispatch.Parsed.Lane,
					CreatedAt:       time.Now().UTC(),
				}
				applyQuestionPolicy(round, &question, "follow_up")
				round.OpenQuestions = append(round.OpenQuestions, question)
			} else if args.NeedsReply && result.OpenQuestionID != "" && !accepted {
				incrementQuestionUnanswered(round, result.OpenQuestionID)
			}
		}
	}

	if round != nil {
		round.UpdatedAt = time.Now().UTC()
		if err := s.store.SaveRound(*round); err != nil {
			return RouteTurnResult{}, err
		}
	}
	return result, nil
}

func (s *Service) SteerRound(ctx context.Context, args SteerRoundArgs) (SteerRoundResult, error) {
	_ = ctx
	round, err := s.requireRound(args.RoundID)
	if err != nil {
		return SteerRoundResult{}, err
	}
	now := time.Now().UTC()
	event := SteeringEvent{
		ID:            messageID("steer", now),
		RoundID:       round.ID,
		Actor:         firstNonEmptyString(strings.TrimSpace(args.Actor), "orchestrator"),
		Goal:          strings.TrimSpace(args.Goal),
		Priorities:    cloneStrings(args.Priorities),
		AllowedRoles:  chooseRoles(args.AllowedRoles, supportedRoles),
		RequiredRoles: chooseRoles(args.RequiredRoles, supportedRequiredRoles),
		OptionalRoles: chooseRoles(args.OptionalRoles, supportedOptionalRoles),
		Budget:        args.Budget,
		Reason:        strings.TrimSpace(args.Reason),
		Applied:       true,
		CreatedAt:     now,
	}
	if event.Budget.MaxHopsPerQuestion == 0 {
		event.Budget.MaxHopsPerQuestion = 8
	}
	if event.Budget.MaxUnanswered == 0 {
		event.Budget.MaxUnanswered = 2
	}
	if event.Budget.MaxTokensPerPacket == 0 {
		event.Budget.MaxTokensPerPacket = 96
	}
	if event.Budget.InterruptWindowSecs == 0 {
		event.Budget.InterruptWindowSecs = 15
	}
	round.Policy = RoundPolicy{
		Mode:            "steered_mesh",
		Goal:            event.Goal,
		Priorities:      cloneStrings(event.Priorities),
		AllowedRoles:    cloneStrings(event.AllowedRoles),
		RequiredRoles:   cloneStrings(event.RequiredRoles),
		OptionalRoles:   cloneStrings(event.OptionalRoles),
		DefaultCodec:    firstNonEmptyString(round.Policy.DefaultCodec, "compact"),
		DefaultPriority: firstNonEmptyString(round.Policy.DefaultPriority, "normal"),
		Budget:          event.Budget,
	}
	round.RequiredRoles = cloneStrings(event.RequiredRoles)
	round.OptionalRoles = cloneStrings(event.OptionalRoles)
	round.SteeringEvents = append(round.SteeringEvents, event)
	round.Status = chooseRoundStatus(round.Status)
	round.UpdatedAt = now
	if err := s.store.SaveRound(*round); err != nil {
		return SteerRoundResult{}, err
	}
	return SteerRoundResult{Round: round, SteeringEvent: &event}, nil
}

func (s *Service) ReadRoundGraph(ctx context.Context, args ReadRoundGraphArgs) (ReadRoundGraphResult, error) {
	_ = ctx
	round, err := s.requireRound(args.RoundID)
	if err != nil {
		return ReadRoundGraphResult{}, err
	}
	return ReadRoundGraphResult{
		Round:             round,
		Messages:          round.Messages,
		Edges:             round.Edges,
		OpenQuestions:     round.OpenQuestions,
		ResolvedQuestions: round.ResolvedQuestions,
		SteeringEvents:    round.SteeringEvents,
	}, nil
}

func (s *Service) ResolveQuestion(ctx context.Context, args ResolveQuestionArgs) (ResolveQuestionResult, error) {
	_ = ctx
	round, err := s.requireRound(args.RoundID)
	if err != nil {
		return ResolveQuestionResult{}, err
	}
	question := resolveRoundQuestion(round, args.QuestionID, args.Resolution, args.DecidedBy, firstNonEmptyString(args.ResolvedVia, "manual"))
	if question == nil {
		return ResolveQuestionResult{}, fmt.Errorf("question을 찾을 수 없습니다: %s", args.QuestionID)
	}
	round.UpdatedAt = time.Now().UTC()
	if err := s.store.SaveRound(*round); err != nil {
		return ResolveQuestionResult{}, err
	}
	return ResolveQuestionResult{Round: round, Question: question}, nil
}

func (s *Service) CloseRound(ctx context.Context, args CloseRoundArgs) (CloseRoundResult, error) {
	_ = ctx
	round, err := s.requireRound(args.RoundID)
	if err != nil {
		return CloseRoundResult{}, err
	}
	round.Status = "resolved"
	round.CurrentStage = "closed"
	round.Summary = strings.TrimSpace(args.Summary)
	round.Retrospective = strings.TrimSpace(args.Retrospective)
	round.CompletedAt = time.Now().UTC()
	round.UpdatedAt = round.CompletedAt
	if err := s.store.SaveRound(*round); err != nil {
		return CloseRoundResult{}, err
	}
	return CloseRoundResult{Round: round}, nil
}

func (s *Service) requireRound(roundID string) (*RoundArtifact, error) {
	if strings.TrimSpace(roundID) == "" {
		return nil, fmt.Errorf("round_id가 비어 있습니다")
	}
	round, err := s.store.LoadRound(strings.TrimSpace(roundID))
	if err != nil {
		return nil, err
	}
	if round == nil {
		return nil, fmt.Errorf("round를 찾을 수 없습니다: %s", roundID)
	}
	return round, nil
}

func buildPeerPrompt(fromRole, toRole, roundID, intent, message string, needsReply bool, replyTo string, codec string, priority string, interrupt bool, tokenBudget int, compressionHint string, lane string) string {
	lines := []string{
		fmt.Sprintf("너는 %s 역할이다.", toRole),
		"이 메시지는 harness steered_mesh peer conversation packet이다.",
		fmt.Sprintf("- round_id: %s", firstNonEmptyString(strings.TrimSpace(roundID), "없음")),
		fmt.Sprintf("- from_role: %s", fromRole),
		fmt.Sprintf("- intent: %s", firstNonEmptyString(strings.TrimSpace(intent), "inform")),
		fmt.Sprintf("- reply_to: %s", firstNonEmptyString(strings.TrimSpace(replyTo), "없음")),
		fmt.Sprintf("- needs_reply: %t", needsReply),
		fmt.Sprintf("- codec: %s", normalizeCodec(codec)),
		fmt.Sprintf("- priority: %s", normalizePriority(priority)),
		fmt.Sprintf("- interrupt: %t", interrupt),
		fmt.Sprintf("- token_budget: %d", tokenBudget),
		fmt.Sprintf("- compression_hint: %s", firstNonEmptyString(strings.TrimSpace(compressionHint), "-")),
		fmt.Sprintf("- lane: %s", normalizeLane(lane)),
		"",
		"메시지:",
		strings.TrimSpace(message),
		"",
		"응답 규칙:",
		"- 자유 형식으로 답해도 된다.",
		"- codec이 compact, kv, symbolic면 짧은 key-value packet이나 원시형 단문을 우선한다.",
		"- 예시: st:ok | sc:align | rs:hud cut keep flight | rk:none | ask:pm lock | cf:0.74 | nr:1 | pr:interrupt",
		"- 고정 섹션 제목, 형식 채우기, 없음 문구 반복은 쓰지 마라.",
		"- 핵심 판단, 실제 리스크, 필요한 요청, 결정, 증거만 남겨라.",
		"- interrupt=true 면 진행 중인 일반 흐름보다 먼저 다뤄야 하는 핵심만 적어라.",
	}
	return strings.Join(lines, "\n")
}

func parsedToRoundMessage(roundID, fromRole, toRole string, parsed *ParsedSections, now time.Time) RoundMessage {
	return RoundMessage{
		MessageID:       messageID("msg", now),
		RoundID:         roundID,
		FromRole:        fromRole,
		ToRoles:         []string{toRole},
		Intent:          parsed.Intent,
		Summary:         parsed.Summary,
		Requests:        cloneStrings(parsed.Requests),
		Decisions:       cloneStrings(parsed.Decisions),
		Risks:           cloneStrings(parsed.Risks),
		EvidenceRefs:    cloneStrings(parsed.EvidenceRefs),
		Confidence:      parsed.Confidence,
		NeedsReply:      parsed.NeedsReply,
		SteerSuggestion: parsed.SteerSuggestion,
		ProtocolStatus:  parsed.ProtocolStatus,
		Priority:        parsed.Priority,
		Interrupt:       parsed.Interrupt,
		Codec:           parsed.Codec,
		TokenBudget:     parsed.TokenBudget,
		CompressionHint: parsed.CompressionHint,
		Lane:            parsed.Lane,
		EtaSeconds:      parsed.EtaSeconds,
		ProgressState:   parsed.ProgressState,
		MoreComing:      parsed.MoreComing,
		ParseMode:       parsed.ParseMode,
		CreatedAt:       now,
	}
}

func resolveRoundQuestion(round *RoundArtifact, questionID, resolution, decidedBy, resolvedVia string) *RoundQuestion {
	for index, question := range round.OpenQuestions {
		if question.ID != questionID {
			continue
		}
		question.Status = "resolved"
		question.Resolution = strings.TrimSpace(resolution)
		question.ResolvedVia = firstNonEmptyString(resolvedVia, decidedBy)
		question.ResolvedAt = time.Now().UTC()
		round.OpenQuestions = append(round.OpenQuestions[:index], round.OpenQuestions[index+1:]...)
		round.ResolvedQuestions = append(round.ResolvedQuestions, question)
		return &question
	}
	return nil
}

func edgeStatus(dispatch DispatchResult) string {
	if dispatch.Error != "" {
		return "warn"
	}
	if acceptedParseStatus(dispatch.ParseStatus) {
		return "ok"
	}
	return "review"
}

func acceptedParseStatus(parseStatus string) bool {
	switch strings.TrimSpace(parseStatus) {
	case "ok", "relaxed", "partial":
		return true
	default:
		return false
	}
}

func broadcastAllowed(intent string) bool {
	switch strings.TrimSpace(intent) {
	case "role_conflict", "wide_impact", "policy_change":
		return true
	default:
		return false
	}
}

func uniqueRoles(roles []string) []string {
	seen := map[string]struct{}{}
	unique := make([]string, 0, len(roles))
	for _, role := range roles {
		role = strings.TrimSpace(role)
		if role == "" {
			continue
		}
		if _, ok := seen[role]; ok {
			continue
		}
		seen[role] = struct{}{}
		unique = append(unique, role)
	}
	return unique
}

func cloneStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}
	out := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		out = append(out, value)
	}
	return out
}

func normalizePriority(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "interrupt", "urgent":
		return "interrupt"
	case "high":
		return "high"
	case "low":
		return "low"
	default:
		return "normal"
	}
}

func normalizeCodec(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "compact":
		return "compact"
	case "kv", "keyvalue", "key_value":
		return "kv"
	case "symbolic", "symbol":
		return "symbolic"
	default:
		return "plain"
	}
}

func normalizeLane(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "interrupt", "fast":
		return "interrupt"
	case "priority":
		return "priority"
	default:
		return "default"
	}
}

func interruptLane(interrupt bool, priority string) string {
	if interrupt || normalizePriority(priority) == "interrupt" {
		return "interrupt"
	}
	if normalizePriority(priority) == "high" {
		return "priority"
	}
	return "default"
}

func currentRoundBudget(round *RoundArtifact) RoundBudget {
	budget := round.Policy.Budget
	if budget.MaxHopsPerQuestion == 0 {
		budget.MaxHopsPerQuestion = 8
	}
	if budget.MaxUnanswered == 0 {
		budget.MaxUnanswered = 2
	}
	if budget.MaxTokensPerPacket == 0 {
		budget.MaxTokensPerPacket = 96
	}
	if budget.InterruptWindowSecs == 0 {
		budget.InterruptWindowSecs = 15
	}
	return budget
}

func applyQuestionPolicy(round *RoundArtifact, question *RoundQuestion, reason string) {
	if question == nil {
		return
	}
	budget := currentRoundBudget(round)
	question.Priority = normalizePriority(question.Priority)
	question.Codec = normalizeCodec(question.Codec)
	question.Lane = normalizeLane(firstNonEmptyString(question.Lane, interruptLane(question.Interrupt, question.Priority)))
	if question.Interrupt && question.Priority != "interrupt" {
		question.Priority = "interrupt"
	}
	if question.TokenBudget <= 0 {
		question.TokenBudget = budget.MaxTokensPerPacket
	}
	switch {
	case question.Interrupt:
		question.Status = "needs_steer"
	case question.HopCount > budget.MaxHopsPerQuestion:
		question.Status = "needs_steer"
	case question.UnansweredCount >= budget.MaxUnanswered:
		question.Status = "needs_steer"
	default:
		question.Status = "open"
	}
	if question.Status == "needs_steer" {
		round.SteeringEvents = append(round.SteeringEvents, SteeringEvent{
			ID:            messageID("steer", time.Now().UTC()),
			RoundID:       round.ID,
			Actor:         "orchestrator",
			Goal:          firstNonEmptyString(round.Policy.Goal, "interrupt steering"),
			Priorities:    cloneStrings(round.Policy.Priorities),
			AllowedRoles:  cloneStrings(round.Policy.AllowedRoles),
			RequiredRoles: cloneStrings(round.Policy.RequiredRoles),
			OptionalRoles: cloneStrings(round.Policy.OptionalRoles),
			Budget:        budget,
			Reason:        firstNonEmptyString(reason, "question escalation"),
			Applied:       false,
			CreatedAt:     time.Now().UTC(),
		})
	}
}

func registerQuestionReply(round *RoundArtifact, questionID string, accepted bool) {
	for index := range round.OpenQuestions {
		if round.OpenQuestions[index].ID != questionID {
			continue
		}
		round.OpenQuestions[index].ReplyCount++
		if accepted {
			round.OpenQuestions[index].UnansweredCount = 0
		} else {
			round.OpenQuestions[index].UnansweredCount++
		}
		applyQuestionPolicy(round, &round.OpenQuestions[index], "reply_update")
		return
	}
}

func incrementQuestionUnanswered(round *RoundArtifact, questionID string) {
	if strings.TrimSpace(questionID) == "" {
		return
	}
	for index := range round.OpenQuestions {
		if round.OpenQuestions[index].ID != questionID {
			continue
		}
		round.OpenQuestions[index].UnansweredCount++
		applyQuestionPolicy(round, &round.OpenQuestions[index], "unanswered")
		return
	}
}

func followUpHopCount(round *RoundArtifact, questionID string) int {
	for _, question := range round.OpenQuestions {
		if question.ID == questionID {
			return question.HopCount + 1
		}
	}
	return 1
}

func chooseRoles(preferred []string, fallback []string) []string {
	if len(preferred) > 0 {
		return cloneStrings(preferred)
	}
	return cloneStrings(fallback)
}

func roundIssue(round *RoundArtifact) string {
	if round == nil || strings.TrimSpace(round.IssueRef) == "" {
		return "미지정"
	}
	return round.IssueRef
}

func chooseRoundStatus(current string) string {
	current = strings.TrimSpace(current)
	if current == "" || current == "pending" {
		return "open"
	}
	return current
}

func firstNonEmptyString(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}
