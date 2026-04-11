package main

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

const (
	mcpProtocolVersion = "2024-11-05"
	serverName         = "golfsim-orchestrator"
	serverVersion      = "0.1.0"
)

var supportedRoles = []string{"pm", "planning", "design", "dev", "gameplay_qa"}
var supportedRequiredRoles = []string{"pm", "planning", "design", "dev", "gameplay_qa"}
var supportedOptionalRoles = []string{}

var supportedRoleSet = map[string]struct{}{
	"pm":          {},
	"planning":    {},
	"design":      {},
	"dev":         {},
	"gameplay_qa": {},
}

const (
	warmAfter     = 30 * time.Minute
	staleAfter    = 4 * time.Hour
	criticalAfter = 24 * time.Hour
)

type Targets map[string]string

type DiscoverThreadsArgs struct {
	CWD        string `json:"cwd"`
	SearchTerm string `json:"search_term,omitempty"`
}

type BindTargetsArgs struct {
	Bindings map[string]string `json:"bindings"`
}

type DispatchTurnArgs struct {
	Role              string `json:"role"`
	ParentIssue       string `json:"parent_issue"`
	TaskRequest       string `json:"task_request"`
	ConfirmedContext  string `json:"confirmed_context,omitempty"`
	BlockerContext    string `json:"blocker_context,omitempty"`
	PromptOverride    string `json:"prompt_override,omitempty"`
	WaitForCompletion *bool  `json:"wait_for_completion,omitempty"`
}

type BroadcastTurnArgs struct {
	Roles            []string `json:"roles"`
	ParentIssue      string   `json:"parent_issue"`
	TaskRequest      string   `json:"task_request"`
	ConfirmedContext string   `json:"confirmed_context,omitempty"`
	BlockerContext   string   `json:"blocker_context,omitempty"`
}

type RouteTurnArgs struct {
	FromRole        string   `json:"from_role"`
	ToRoles         []string `json:"to_roles"`
	RoundID         string   `json:"round_id,omitempty"`
	Intent          string   `json:"intent"`
	Message         string   `json:"message"`
	WaitMode        string   `json:"wait_mode,omitempty"`
	NeedsReply      bool     `json:"needs_reply,omitempty"`
	ReplyTo         string   `json:"reply_to,omitempty"`
	Priority        string   `json:"priority,omitempty"`
	Interrupt       bool     `json:"interrupt,omitempty"`
	Codec           string   `json:"codec,omitempty"`
	TokenBudget     int      `json:"token_budget,omitempty"`
	CompressionHint string   `json:"compression_hint,omitempty"`
	Lane            string   `json:"lane,omitempty"`
}

type SteerRoundArgs struct {
	RoundID       string      `json:"round_id"`
	Goal          string      `json:"goal"`
	Priorities    []string    `json:"priorities,omitempty"`
	AllowedRoles  []string    `json:"allowed_roles,omitempty"`
	RequiredRoles []string    `json:"required_roles,omitempty"`
	OptionalRoles []string    `json:"optional_roles,omitempty"`
	Budget        RoundBudget `json:"budget,omitempty"`
	Reason        string      `json:"reason,omitempty"`
	Actor         string      `json:"actor,omitempty"`
}

type ReadRoundGraphArgs struct {
	RoundID string `json:"round_id"`
}

type ResolveQuestionArgs struct {
	RoundID     string `json:"round_id"`
	QuestionID  string `json:"question_id"`
	Resolution  string `json:"resolution"`
	DecidedBy   string `json:"decided_by"`
	ResolvedVia string `json:"resolved_via,omitempty"`
}

type CloseRoundArgs struct {
	RoundID       string `json:"round_id"`
	Summary       string `json:"summary"`
	Retrospective string `json:"retrospective,omitempty"`
	ClosedBy      string `json:"closed_by,omitempty"`
}

type ReadTeamArgs struct {
	Role         string `json:"role"`
	IncludeTurns bool   `json:"include_turns,omitempty"`
}

type RoundtableStartArgs struct {
	IssueRef     string   `json:"issue_ref,omitempty"`
	Trigger      string   `json:"trigger"`
	ChangedFiles []string `json:"changed_files,omitempty"`
	Topic        string   `json:"topic,omitempty"`
	SessionID    string   `json:"session_id,omitempty"`
}

type RoundtableReadArgs struct {
	RoundID string `json:"round_id"`
}

type RoundtableListArgs struct {
	Limit int `json:"limit,omitempty"`
}

type ParsedSections struct {
	Status          string   `json:"status"`
	Scope           string   `json:"understanding"`
	Result          string   `json:"result"`
	Summary         string   `json:"summary,omitempty"`
	Intent          string   `json:"intent,omitempty"`
	Blocker         string   `json:"blocker"`
	NextRequest     string   `json:"next_request"`
	Requests        []string `json:"requests,omitempty"`
	Decisions       []string `json:"decisions,omitempty"`
	Risks           []string `json:"risks,omitempty"`
	EvidenceRefs    []string `json:"evidence_refs,omitempty"`
	Confidence      float64  `json:"confidence,omitempty"`
	NeedsReply      bool     `json:"needs_reply,omitempty"`
	SteerSuggestion string   `json:"steer_suggestion,omitempty"`
	ProtocolStatus  string   `json:"protocol_status,omitempty"`
	Priority        string   `json:"priority,omitempty"`
	Interrupt       bool     `json:"interrupt,omitempty"`
	Codec           string   `json:"codec,omitempty"`
	TokenBudget     int      `json:"token_budget,omitempty"`
	CompressionHint string   `json:"compression_hint,omitempty"`
	Lane            string   `json:"lane,omitempty"`
	EtaSeconds      int      `json:"eta_seconds,omitempty"`
	ProgressState   string   `json:"progress_state,omitempty"`
	MoreComing      bool     `json:"more_coming,omitempty"`
	ParseStatus     string   `json:"parse_status"`
	ParseMode       string   `json:"parse_mode,omitempty"`
	ParseConfidence float64  `json:"parse_confidence,omitempty"`
	Missing         []string `json:"missing,omitempty"`
	Raw             string   `json:"raw"`
}

type TeamState struct {
	Role               string          `json:"role"`
	LastDispatchID     string          `json:"last_dispatch_id,omitempty"`
	ThreadID           string          `json:"thread_id,omitempty"`
	ThreadTitle        string          `json:"thread_title,omitempty"`
	LastTurnID         string          `json:"last_turn_id,omitempty"`
	LastStatus         string          `json:"last_status,omitempty"`
	Blocker            string          `json:"blocker,omitempty"`
	NextRequest        string          `json:"next_request,omitempty"`
	UpdatedAt          time.Time       `json:"updated_at,omitempty"`
	ParseStatus        string          `json:"parse_status,omitempty"`
	ParseMode          string          `json:"parse_mode,omitempty"`
	ParseConfidence    float64         `json:"parse_confidence,omitempty"`
	Freshness          string          `json:"freshness,omitempty"`
	RiskState          string          `json:"risk_state,omitempty"`
	Source             string          `json:"source,omitempty"`
	RequiredRole       bool            `json:"required_role"`
	LastPeerMessageAt  time.Time       `json:"last_peer_message_at,omitempty"`
	LastPeerTarget     string          `json:"last_peer_target,omitempty"`
	LastStreamAt       time.Time       `json:"last_stream_at,omitempty"`
	DeclaredEtaSeconds int             `json:"declared_eta_seconds,omitempty"`
	ProgressState      string          `json:"progress_state,omitempty"`
	StreamText         string          `json:"stream_text,omitempty"`
	ResponseAcceptRate float64         `json:"response_accept_rate,omitempty"`
	RawFinalText       string          `json:"raw_final_text,omitempty"`
	Parsed             *ParsedSections `json:"parsed,omitempty"`
	LastError          string          `json:"last_error,omitempty"`
}

type DashboardEntry struct {
	Role               string    `json:"role"`
	LastDispatchID     string    `json:"last_dispatch_id,omitempty"`
	ThreadID           string    `json:"thread_id,omitempty"`
	ThreadTitle        string    `json:"thread_title,omitempty"`
	LastTurnID         string    `json:"last_turn_id,omitempty"`
	LastStatus         string    `json:"last_status,omitempty"`
	Blocker            string    `json:"blocker,omitempty"`
	NextRequest        string    `json:"next_request,omitempty"`
	UpdatedAt          time.Time `json:"updated_at,omitempty"`
	LastPeerMessageAt  time.Time `json:"last_peer_message_at,omitempty"`
	LastPeerTarget     string    `json:"last_peer_target,omitempty"`
	LastStreamAt       time.Time `json:"last_stream_at,omitempty"`
	Stale              bool      `json:"stale"`
	Freshness          string    `json:"freshness,omitempty"`
	RiskState          string    `json:"risk_state,omitempty"`
	RequiredRole       bool      `json:"required_role"`
	ParseStatus        string    `json:"parse_status,omitempty"`
	ParseMode          string    `json:"parse_mode,omitempty"`
	ParseConfidence    float64   `json:"parse_confidence,omitempty"`
	DeclaredEtaSeconds int       `json:"declared_eta_seconds,omitempty"`
	ProgressState      string    `json:"progress_state,omitempty"`
	ResponseAcceptRate float64   `json:"response_accept_rate,omitempty"`
}

type ThreadSummary struct {
	ID            string    `json:"id"`
	Title         string    `json:"title"`
	CWD           string    `json:"cwd"`
	Status        string    `json:"status"`
	Preview       string    `json:"preview"`
	UpdatedAt     time.Time `json:"updated_at"`
	CreatedAt     time.Time `json:"created_at"`
	AgentNickname string    `json:"agent_nickname,omitempty"`
	AgentRole     string    `json:"agent_role,omitempty"`
}

type DispatchResult struct {
	Role         string          `json:"role"`
	DispatchID   string          `json:"dispatch_id"`
	ThreadID     string          `json:"thread_id"`
	ThreadTitle  string          `json:"thread_title"`
	TurnID       string          `json:"turn_id,omitempty"`
	Waited       bool            `json:"waited"`
	PromptPath   string          `json:"prompt_path,omitempty"`
	LastStatus   string          `json:"last_status,omitempty"`
	ParseStatus  string          `json:"parse_status,omitempty"`
	Parsed       *ParsedSections `json:"parsed,omitempty"`
	Error        string          `json:"error,omitempty"`
	CompletedNow bool            `json:"completed_now"`
}

type ReadTeamResult struct {
	Role   string          `json:"role"`
	State  *DashboardEntry `json:"state,omitempty"`
	Raw    *TeamState      `json:"raw,omitempty"`
	Thread *AppThread      `json:"thread,omitempty"`
}

type DashboardResult struct {
	Entries map[string]DashboardEntry `json:"entries"`
}

type RouteTurnResult struct {
	RoundID         string           `json:"round_id,omitempty"`
	MessageID       string           `json:"message_id,omitempty"`
	OpenQuestionID  string           `json:"open_question_id,omitempty"`
	Priority        string           `json:"priority,omitempty"`
	Interrupt       bool             `json:"interrupt,omitempty"`
	Codec           string           `json:"codec,omitempty"`
	TokenBudget     int              `json:"token_budget,omitempty"`
	CompressionHint string           `json:"compression_hint,omitempty"`
	Lane            string           `json:"lane,omitempty"`
	Results         []DispatchResult `json:"results"`
}

type SteerRoundResult struct {
	Round         *RoundArtifact `json:"round,omitempty"`
	SteeringEvent *SteeringEvent `json:"steering_event,omitempty"`
}

type ReadRoundGraphResult struct {
	Round             *RoundArtifact  `json:"round,omitempty"`
	Messages          []RoundMessage  `json:"messages,omitempty"`
	Edges             []RoundEdge     `json:"edges,omitempty"`
	OpenQuestions     []RoundQuestion `json:"open_questions,omitempty"`
	ResolvedQuestions []RoundQuestion `json:"resolved_questions,omitempty"`
	SteeringEvents    []SteeringEvent `json:"steering_events,omitempty"`
}

type ResolveQuestionResult struct {
	Round    *RoundArtifact `json:"round,omitempty"`
	Question *RoundQuestion `json:"question,omitempty"`
}

type CloseRoundResult struct {
	Round *RoundArtifact `json:"round,omitempty"`
}

type RoundtableStartResult struct {
	Round     RoundArtifact `json:"round"`
	DedupeHit bool          `json:"dedupe_hit"`
	Enqueued  bool          `json:"enqueued"`
}

type RoundtableReadResult struct {
	Round *RoundArtifact `json:"round,omitempty"`
}

type RoundtableListResult struct {
	Rounds []RoundArtifact `json:"rounds"`
}

type RoundArtifact struct {
	ID                string             `json:"id"`
	IssueRef          string             `json:"issue_ref,omitempty"`
	Trigger           string             `json:"trigger"`
	Topic             string             `json:"topic,omitempty"`
	ChangedFiles      []string           `json:"changed_files,omitempty"`
	ChangeFingerprint string             `json:"change_fingerprint,omitempty"`
	SessionID         string             `json:"session_id,omitempty"`
	Source            string             `json:"source,omitempty"`
	Status            string             `json:"status"`
	CurrentStage      string             `json:"current_stage,omitempty"`
	PendingReason     string             `json:"pending_reason,omitempty"`
	Error             string             `json:"error,omitempty"`
	CreatedAt         time.Time          `json:"created_at"`
	UpdatedAt         time.Time          `json:"updated_at"`
	StartedAt         time.Time          `json:"started_at,omitempty"`
	CompletedAt       time.Time          `json:"completed_at,omitempty"`
	Participants      []string           `json:"participants,omitempty"`
	RequiredRoles     []string           `json:"required_roles,omitempty"`
	OptionalRoles     []string           `json:"optional_roles,omitempty"`
	Policy            RoundPolicy        `json:"policy,omitempty"`
	Steps             []RoundStepResult  `json:"steps,omitempty"`
	Messages          []RoundMessage     `json:"messages,omitempty"`
	Edges             []RoundEdge        `json:"edges,omitempty"`
	OpenQuestions     []RoundQuestion    `json:"open_questions,omitempty"`
	ResolvedQuestions []RoundQuestion    `json:"resolved_questions,omitempty"`
	SteeringEvents    []SteeringEvent    `json:"steering_events,omitempty"`
	Summary           string             `json:"summary,omitempty"`
	Retrospective     string             `json:"retrospective,omitempty"`
	GameplayFindings  []string           `json:"gameplay_findings,omitempty"`
	BacklogCandidates []BacklogCandidate `json:"backlog_candidates,omitempty"`
	IssueDraftResults []IssueDraftResult `json:"issue_draft_results,omitempty"`
	ReviewPath        string             `json:"review_path,omitempty"`
	BacklogDraftPath  string             `json:"backlog_draft_path,omitempty"`
}

type RoundStepResult struct {
	Stage            string    `json:"stage"`
	Role             string    `json:"role"`
	FromRole         string    `json:"from_role,omitempty"`
	ToRoles          []string  `json:"to_roles,omitempty"`
	TurnIndex        int       `json:"turn_index"`
	MessageID        string    `json:"message_id,omitempty"`
	Intent           string    `json:"intent,omitempty"`
	ThreadID         string    `json:"thread_id,omitempty"`
	TurnID           string    `json:"turn_id,omitempty"`
	ParseStatus      string    `json:"parse_status,omitempty"`
	ParseMode        string    `json:"parse_mode,omitempty"`
	FallbackKind     string    `json:"fallback_kind,omitempty"`
	LastStatus       string    `json:"last_status,omitempty"`
	Blocker          string    `json:"blocker,omitempty"`
	NextRequest      string    `json:"next_request,omitempty"`
	NeedsReply       bool      `json:"needs_reply,omitempty"`
	Priority         string    `json:"priority,omitempty"`
	Interrupt        bool      `json:"interrupt,omitempty"`
	Codec            string    `json:"codec,omitempty"`
	TokenBudget      int       `json:"token_budget,omitempty"`
	CompressionHint  string    `json:"compression_hint,omitempty"`
	Lane             string    `json:"lane,omitempty"`
	EtaSeconds       int       `json:"eta_seconds,omitempty"`
	ProgressState    string    `json:"progress_state,omitempty"`
	MoreComing       bool      `json:"more_coming,omitempty"`
	LastStreamAt     string    `json:"last_stream_at,omitempty"`
	AdaptiveDeadline string    `json:"adaptive_deadline,omitempty"`
	ExtendedSlices   int       `json:"extended_slices,omitempty"`
	TimeoutReason    string    `json:"timeout_reason,omitempty"`
	Scope            string    `json:"understanding,omitempty"`
	Result           string    `json:"result,omitempty"`
	Raw              string    `json:"raw,omitempty"`
	Confidence       float64   `json:"confidence,omitempty"`
	EvidenceRefs     []string  `json:"evidence_refs,omitempty"`
	UpdatedAt        time.Time `json:"updated_at,omitempty"`
}

type RoundBudget struct {
	MaxHopsPerQuestion  int `json:"max_hops_per_question,omitempty"`
	MaxUnanswered       int `json:"max_unanswered,omitempty"`
	MaxTokensPerPacket  int `json:"max_tokens_per_packet,omitempty"`
	InterruptWindowSecs int `json:"interrupt_window_secs,omitempty"`
}

type RoundPolicy struct {
	Mode            string      `json:"mode,omitempty"`
	Goal            string      `json:"goal,omitempty"`
	Priorities      []string    `json:"priorities,omitempty"`
	AllowedRoles    []string    `json:"allowed_roles,omitempty"`
	RequiredRoles   []string    `json:"required_roles,omitempty"`
	OptionalRoles   []string    `json:"optional_roles,omitempty"`
	DefaultCodec    string      `json:"default_codec,omitempty"`
	DefaultPriority string      `json:"default_priority,omitempty"`
	Budget          RoundBudget `json:"budget,omitempty"`
}

type RoundMessage struct {
	MessageID        string    `json:"message_id"`
	RoundID          string    `json:"round_id"`
	FromRole         string    `json:"from_role"`
	ToRoles          []string  `json:"to_roles,omitempty"`
	ReplyTo          string    `json:"reply_to,omitempty"`
	Intent           string    `json:"intent,omitempty"`
	Summary          string    `json:"summary,omitempty"`
	Requests         []string  `json:"requests,omitempty"`
	Decisions        []string  `json:"decisions,omitempty"`
	Risks            []string  `json:"risks,omitempty"`
	EvidenceRefs     []string  `json:"evidence_refs,omitempty"`
	Confidence       float64   `json:"confidence,omitempty"`
	NeedsReply       bool      `json:"needs_reply,omitempty"`
	SteerSuggestion  string    `json:"steer_suggestion,omitempty"`
	ProtocolStatus   string    `json:"protocol_status,omitempty"`
	Priority         string    `json:"priority,omitempty"`
	Interrupt        bool      `json:"interrupt,omitempty"`
	Codec            string    `json:"codec,omitempty"`
	TokenBudget      int       `json:"token_budget,omitempty"`
	CompressionHint  string    `json:"compression_hint,omitempty"`
	Lane             string    `json:"lane,omitempty"`
	EtaSeconds       int       `json:"eta_seconds,omitempty"`
	ProgressState    string    `json:"progress_state,omitempty"`
	MoreComing       bool      `json:"more_coming,omitempty"`
	LastStreamAt     string    `json:"last_stream_at,omitempty"`
	AdaptiveDeadline string    `json:"adaptive_deadline,omitempty"`
	ExtendedSlices   int       `json:"extended_slices,omitempty"`
	TimeoutReason    string    `json:"timeout_reason,omitempty"`
	ParseMode        string    `json:"parse_mode,omitempty"`
	FallbackKind     string    `json:"fallback_kind,omitempty"`
	CreatedAt        time.Time `json:"created_at"`
}

type RoundEdge struct {
	ID           string    `json:"id"`
	RoundID      string    `json:"round_id"`
	FromRole     string    `json:"from_role"`
	ToRole       string    `json:"to_role"`
	MessageID    string    `json:"message_id,omitempty"`
	ReplyTo      string    `json:"reply_to,omitempty"`
	Intent       string    `json:"intent,omitempty"`
	Accepted     bool      `json:"accepted"`
	Status       string    `json:"status,omitempty"`
	Priority     string    `json:"priority,omitempty"`
	Interrupt    bool      `json:"interrupt,omitempty"`
	Codec        string    `json:"codec,omitempty"`
	Lane         string    `json:"lane,omitempty"`
	FallbackKind string    `json:"fallback_kind,omitempty"`
	CreatedAt    time.Time `json:"created_at"`
}

type RoundQuestion struct {
	ID              string    `json:"id"`
	RoundID         string    `json:"round_id"`
	FromRole        string    `json:"from_role"`
	ToRoles         []string  `json:"to_roles,omitempty"`
	Intent          string    `json:"intent,omitempty"`
	MessageID       string    `json:"message_id,omitempty"`
	Status          string    `json:"status,omitempty"`
	ReplyCount      int       `json:"reply_count,omitempty"`
	HopCount        int       `json:"hop_count,omitempty"`
	UnansweredCount int       `json:"unanswered_count,omitempty"`
	Priority        string    `json:"priority,omitempty"`
	Interrupt       bool      `json:"interrupt,omitempty"`
	Codec           string    `json:"codec,omitempty"`
	TokenBudget     int       `json:"token_budget,omitempty"`
	Lane            string    `json:"lane,omitempty"`
	Resolution      string    `json:"resolution,omitempty"`
	ResolvedVia     string    `json:"resolved_via,omitempty"`
	CreatedAt       time.Time `json:"created_at"`
	ResolvedAt      time.Time `json:"resolved_at,omitempty"`
}

type SteeringEvent struct {
	ID            string      `json:"id"`
	RoundID       string      `json:"round_id"`
	Actor         string      `json:"actor"`
	Goal          string      `json:"goal,omitempty"`
	Priorities    []string    `json:"priorities,omitempty"`
	AllowedRoles  []string    `json:"allowed_roles,omitempty"`
	RequiredRoles []string    `json:"required_roles,omitempty"`
	OptionalRoles []string    `json:"optional_roles,omitempty"`
	Budget        RoundBudget `json:"budget,omitempty"`
	Reason        string      `json:"reason,omitempty"`
	Applied       bool        `json:"applied"`
	CreatedAt     time.Time   `json:"created_at"`
}

type BacklogCandidate struct {
	Title              string   `json:"title"`
	Summary            string   `json:"summary"`
	TeamLabel          string   `json:"team_label"`
	AcceptanceCriteria []string `json:"acceptance_criteria,omitempty"`
}

type IssueDraftResult struct {
	Title     string `json:"title"`
	URL       string `json:"url,omitempty"`
	Status    string `json:"status"`
	Error     string `json:"error,omitempty"`
	TeamLabel string `json:"team_label,omitempty"`
}

type DiscoverThreadsResult struct {
	Threads []ThreadSummary `json:"threads"`
}

type BindTargetsResult struct {
	Bindings  map[string]string        `json:"bindings"`
	Validated map[string]ThreadSummary `json:"validated"`
}

type BroadcastTurnResult struct {
	Results []DispatchResult `json:"results"`
}

type dispatchEvent struct {
	Event       string    `json:"event"`
	DispatchID  string    `json:"dispatch_id"`
	Role        string    `json:"role"`
	ThreadID    string    `json:"thread_id"`
	ThreadTitle string    `json:"thread_title,omitempty"`
	TurnID      string    `json:"turn_id,omitempty"`
	PromptPath  string    `json:"prompt_path,omitempty"`
	ParentIssue string    `json:"parent_issue,omitempty"`
	TaskRequest string    `json:"task_request,omitempty"`
	Waited      bool      `json:"waited"`
	ParseStatus string    `json:"parse_status,omitempty"`
	Error       string    `json:"error,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
	CompletedAt time.Time `json:"completed_at,omitempty"`
}

type rpcRequest struct {
	JSONRPC string      `json:"jsonrpc"`
	ID      interface{} `json:"id,omitempty"`
	Method  string      `json:"method"`
	Params  interface{} `json:"params,omitempty"`
}

type rpcEnvelope struct {
	JSONRPC string           `json:"jsonrpc"`
	ID      *json.RawMessage `json:"id,omitempty"`
	Method  string           `json:"method,omitempty"`
	Params  json.RawMessage  `json:"params,omitempty"`
	Result  json.RawMessage  `json:"result,omitempty"`
	Error   *rpcError        `json:"error,omitempty"`
}

type rpcError struct {
	Code    int             `json:"code"`
	Message string          `json:"message"`
	Data    json.RawMessage `json:"data,omitempty"`
}

type rpcCallResult struct {
	Result json.RawMessage
	Err    error
}

type mcpTool struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	InputSchema map[string]any `json:"inputSchema"`
}

type mcpTextContent struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

type AppThreadListResponse struct {
	Data       []AppThread `json:"data"`
	NextCursor *string     `json:"nextCursor"`
}

type AppThreadReadResponse struct {
	Thread AppThread `json:"thread"`
}

type AppTurnStartResponse struct {
	Turn AppTurn `json:"turn"`
}

type AppThread struct {
	ID            string      `json:"id"`
	Preview       string      `json:"preview"`
	Ephemeral     bool        `json:"ephemeral"`
	ModelProvider string      `json:"modelProvider"`
	CreatedAt     int64       `json:"createdAt"`
	UpdatedAt     int64       `json:"updatedAt"`
	Status        StatusValue `json:"status"`
	Path          *string     `json:"path"`
	CWD           string      `json:"cwd"`
	CLIVersion    string      `json:"cliVersion"`
	Source        string      `json:"source"`
	AgentNickname *string     `json:"agentNickname"`
	AgentRole     *string     `json:"agentRole"`
	Name          *string     `json:"name"`
	Turns         []AppTurn   `json:"turns"`
}

type AppTurn struct {
	ID     string          `json:"id"`
	Items  []AppThreadItem `json:"items"`
	Status StatusValue     `json:"status"`
	Error  json.RawMessage `json:"error"`
}

type AppThreadItem struct {
	Type    string          `json:"type"`
	ID      string          `json:"id"`
	Text    string          `json:"text"`
	Phase   *string         `json:"phase"`
	Content json.RawMessage `json:"content"`
}

type appTurnCompleted struct {
	ThreadID string  `json:"threadId"`
	Turn     AppTurn `json:"turn"`
}

type appThreadStatusChanged struct {
	ThreadID string `json:"threadId"`
	Status   string `json:"status"`
}

type appAgentMessageDelta struct {
	ThreadID string `json:"threadId"`
	TurnID   string `json:"turnId"`
	ItemID   string `json:"itemId"`
	Delta    string `json:"delta"`
}

type appServerNotification struct {
	Method   string
	ThreadID string
	TurnID   string
	Status   string
	Delta    string
}

type AppServerConfig struct {
	Command  string
	Args     []string
	RepoRoot string
	Env      []string
}

func roleSupported(role string) bool {
	_, ok := supportedRoleSet[role]
	return ok
}

func boolValue(v *bool, fallback bool) bool {
	if v == nil {
		return fallback
	}
	return *v
}

func timeFromUnixSeconds(sec int64) time.Time {
	if sec <= 0 {
		return time.Time{}
	}
	return time.Unix(sec, 0).UTC()
}

func threadTitle(thread AppThread) string {
	if thread.Name != nil && *thread.Name != "" {
		return *thread.Name
	}
	if thread.Preview != "" {
		for _, line := range splitLines(thread.Preview) {
			if line != "" {
				return line
			}
		}
	}
	return thread.ID
}

func threadSummary(thread AppThread) ThreadSummary {
	var nickname string
	if thread.AgentNickname != nil {
		nickname = *thread.AgentNickname
	}
	var role string
	if thread.AgentRole != nil {
		role = *thread.AgentRole
	}
	return ThreadSummary{
		ID:            thread.ID,
		Title:         threadTitle(thread),
		CWD:           thread.CWD,
		Status:        string(thread.Status),
		Preview:       thread.Preview,
		UpdatedAt:     timeFromUnixSeconds(thread.UpdatedAt),
		CreatedAt:     timeFromUnixSeconds(thread.CreatedAt),
		AgentNickname: nickname,
		AgentRole:     role,
	}
}

func dashboardEntryFromState(role string, state *TeamState) DashboardEntry {
	if state == nil {
		return DashboardEntry{Role: role, Stale: true, Freshness: "critical", RequiredRole: requiredRole(role)}
	}
	freshness := state.Freshness
	if freshness == "" {
		freshness = freshnessFromTime(state.UpdatedAt)
	}
	return DashboardEntry{
		Role:               role,
		LastDispatchID:     state.LastDispatchID,
		ThreadID:           state.ThreadID,
		ThreadTitle:        state.ThreadTitle,
		LastTurnID:         state.LastTurnID,
		LastStatus:         state.LastStatus,
		Blocker:            state.Blocker,
		NextRequest:        state.NextRequest,
		UpdatedAt:          state.UpdatedAt,
		LastPeerMessageAt:  state.LastPeerMessageAt,
		LastPeerTarget:     state.LastPeerTarget,
		LastStreamAt:       state.LastStreamAt,
		Stale:              freshness == "stale" || freshness == "critical",
		Freshness:          freshness,
		RiskState:          riskStateFromState(state),
		RequiredRole:       state.RequiredRole || requiredRole(role),
		ParseStatus:        state.ParseStatus,
		ParseMode:          state.ParseMode,
		ParseConfidence:    state.ParseConfidence,
		DeclaredEtaSeconds: state.DeclaredEtaSeconds,
		ProgressState:      state.ProgressState,
		ResponseAcceptRate: state.ResponseAcceptRate,
	}
}

func dispatchID(role string, now time.Time) string {
	return fmt.Sprintf("%s-%d", role, now.UTC().UnixNano())
}

func messageID(prefix string, now time.Time) string {
	return fmt.Sprintf("%s-%d", prefix, now.UTC().UnixNano())
}

func requiredRole(role string) bool {
	for _, item := range supportedRequiredRoles {
		if item == role {
			return true
		}
	}
	return false
}

func freshnessFromTime(updatedAt time.Time) string {
	if updatedAt.IsZero() {
		return "critical"
	}
	age := time.Since(updatedAt)
	switch {
	case age <= warmAfter:
		return "fresh"
	case age <= staleAfter:
		return "warm"
	case age <= criticalAfter:
		return "stale"
	default:
		return "critical"
	}
}

func riskStateFromState(state *TeamState) string {
	if state == nil {
		return "blocked"
	}
	if state.RiskState != "" {
		return state.RiskState
	}
	blocker := strings.TrimSpace(state.Blocker)
	if blocker == "" || blocker == "없음" || blocker == "- 없음" {
		return "clear"
	}
	return "blocked"
}

type StatusValue string

func (s *StatusValue) UnmarshalJSON(data []byte) error {
	if string(data) == "null" {
		*s = ""
		return nil
	}

	var asString string
	if err := json.Unmarshal(data, &asString); err == nil {
		*s = StatusValue(asString)
		return nil
	}

	var asObject struct {
		Type string `json:"type"`
	}
	if err := json.Unmarshal(data, &asObject); err == nil {
		*s = StatusValue(asObject.Type)
		return nil
	}

	return fmt.Errorf("status 파싱 실패: %s", string(data))
}
