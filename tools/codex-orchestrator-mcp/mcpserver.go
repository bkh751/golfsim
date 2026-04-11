package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"sync"
)

type MCPServer struct {
	in      io.Reader
	out     io.Writer
	writeMu sync.Mutex
	service *Service
}

func NewMCPServer(in io.Reader, out io.Writer, service *Service) *MCPServer {
	return &MCPServer{in: in, out: out, service: service}
}

func (s *MCPServer) Run(ctx context.Context) error {
	scanner := bufio.NewScanner(s.in)
	scanner.Buffer(make([]byte, 1024), 10*1024*1024)

	for scanner.Scan() {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		var request rpcRequest
		if err := json.Unmarshal([]byte(line), &request); err != nil {
			_ = s.writeError(nil, -32700, fmt.Sprintf("JSON 파싱 실패: %v", err))
			continue
		}
		if err := s.handleRequest(ctx, request); err != nil {
			if request.ID != nil {
				_ = s.writeError(request.ID, -32000, err.Error())
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return err
	}
	return nil
}

func (s *MCPServer) handleRequest(ctx context.Context, request rpcRequest) error {
	switch request.Method {
	case "initialize":
		return s.writeResult(request.ID, map[string]any{
			"protocolVersion": mcpProtocolVersion,
			"capabilities": map[string]any{
				"tools": map[string]any{},
			},
			"serverInfo": map[string]any{
				"name":    serverName,
				"version": serverVersion,
			},
		})
	case "initialized", "notifications/initialized":
		return nil
	case "ping":
		return s.writeResult(request.ID, map[string]any{})
	case "tools/list":
		return s.writeResult(request.ID, map[string]any{
			"tools": s.tools(),
		})
	case "tools/call":
		var params struct {
			Name      string         `json:"name"`
			Arguments map[string]any `json:"arguments"`
		}
		if err := decodeInto(request.Params, &params); err != nil {
			return err
		}
		text, isError, err := s.callTool(ctx, params.Name, params.Arguments)
		if err != nil {
			return err
		}
		return s.writeResult(request.ID, map[string]any{
			"content": []mcpTextContent{
				{Type: "text", Text: text},
			},
			"isError": isError,
		})
	default:
		return s.writeError(request.ID, -32601, fmt.Sprintf("지원하지 않는 메서드: %s", request.Method))
	}
}

func (s *MCPServer) tools() []mcpTool {
	return []mcpTool{
		{
			Name:        "discover_threads",
			Description: "현재 프로젝트 cwd의 Codex thread 후보를 찾는다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"cwd": map[string]any{
						"type":        "string",
						"description": "프로젝트 cwd. 비우면 현재 저장소 루트를 사용한다.",
					},
					"search_term": map[string]any{
						"type":        "string",
						"description": "선택적 검색어.",
					},
				},
				"required": []string{"cwd"},
			},
		},
		{
			Name:        "bind_targets",
			Description: "pm/planning/design/dev/gameplay_qa role을 고정 thread id에 바인딩한다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"bindings": map[string]any{
						"type":                 "object",
						"additionalProperties": map[string]any{"type": "string"},
					},
				},
				"required": []string{"bindings"},
			},
		},
		{
			Name:        "dispatch_turn",
			Description: "한 팀 세션에 relay prompt를 보내고 필요하면 완료까지 기다린다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"role":                map[string]any{"type": "string", "enum": supportedRoles},
					"parent_issue":        map[string]any{"type": "string"},
					"task_request":        map[string]any{"type": "string"},
					"confirmed_context":   map[string]any{"type": "string"},
					"blocker_context":     map[string]any{"type": "string"},
					"prompt_override":     map[string]any{"type": "string"},
					"wait_for_completion": map[string]any{"type": "boolean"},
				},
				"required": []string{"role", "parent_issue", "task_request"},
			},
		},
		{
			Name:        "broadcast_turn",
			Description: "여러 팀 세션에 같은 요청을 순차 전송한다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"roles":             map[string]any{"type": "array", "items": map[string]any{"type": "string", "enum": supportedRoles}},
					"parent_issue":      map[string]any{"type": "string"},
					"task_request":      map[string]any{"type": "string"},
					"confirmed_context": map[string]any{"type": "string"},
					"blocker_context":   map[string]any{"type": "string"},
				},
				"required": []string{"roles", "parent_issue", "task_request"},
			},
		},
		{
			Name:        "route_turn",
			Description: "역할 간 peer-to-peer 대화를 오케스트레이터 라우터를 경유해 기록 가능하게 전송한다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"from_role":        map[string]any{"type": "string"},
					"to_roles":         map[string]any{"type": "array", "items": map[string]any{"type": "string", "enum": supportedRoles}},
					"round_id":         map[string]any{"type": "string"},
					"intent":           map[string]any{"type": "string"},
					"message":          map[string]any{"type": "string"},
					"wait_mode":        map[string]any{"type": "string"},
					"needs_reply":      map[string]any{"type": "boolean"},
					"reply_to":         map[string]any{"type": "string"},
					"priority":         map[string]any{"type": "string"},
					"interrupt":        map[string]any{"type": "boolean"},
					"codec":            map[string]any{"type": "string"},
					"token_budget":     map[string]any{"type": "integer"},
					"compression_hint": map[string]any{"type": "string"},
					"lane":             map[string]any{"type": "string"},
				},
				"required": []string{"from_role", "to_roles", "intent", "message"},
			},
		},
		{
			Name:        "steer_round",
			Description: "라운드의 steering policy와 required/optional role을 갱신한다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"round_id":       map[string]any{"type": "string"},
					"goal":           map[string]any{"type": "string"},
					"priorities":     map[string]any{"type": "array", "items": map[string]any{"type": "string"}},
					"allowed_roles":  map[string]any{"type": "array", "items": map[string]any{"type": "string", "enum": supportedRoles}},
					"required_roles": map[string]any{"type": "array", "items": map[string]any{"type": "string", "enum": supportedRoles}},
					"optional_roles": map[string]any{"type": "array", "items": map[string]any{"type": "string", "enum": supportedRoles}},
					"budget":         map[string]any{"type": "object"},
					"reason":         map[string]any{"type": "string"},
					"actor":          map[string]any{"type": "string"},
				},
				"required": []string{"round_id", "goal"},
			},
		},
		{
			Name:        "read_round_graph",
			Description: "특정 라운드의 peer conversation graph를 읽는다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"round_id": map[string]any{"type": "string"},
				},
				"required": []string{"round_id"},
			},
		},
		{
			Name:        "resolve_question",
			Description: "open question을 resolved로 옮긴다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"round_id":     map[string]any{"type": "string"},
					"question_id":  map[string]any{"type": "string"},
					"resolution":   map[string]any{"type": "string"},
					"decided_by":   map[string]any{"type": "string"},
					"resolved_via": map[string]any{"type": "string"},
				},
				"required": []string{"round_id", "question_id", "resolution", "decided_by"},
			},
		},
		{
			Name:        "close_round",
			Description: "라운드를 resolved 상태로 닫고 summary/retrospective를 기록한다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"round_id":      map[string]any{"type": "string"},
					"summary":       map[string]any{"type": "string"},
					"retrospective": map[string]any{"type": "string"},
					"closed_by":     map[string]any{"type": "string"},
				},
				"required": []string{"round_id", "summary"},
			},
		},
		{
			Name:        "read_dashboard",
			Description: "5개 팀 전체 대시보드 상태를 읽는다.",
			InputSchema: map[string]any{
				"type":       "object",
				"properties": map[string]any{},
			},
		},
		{
			Name:        "roundtable_start",
			Description: "라운드테이블 실행 요청을 큐에 등록한다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"issue_ref":     map[string]any{"type": "string"},
					"trigger":       map[string]any{"type": "string"},
					"changed_files": map[string]any{"type": "array", "items": map[string]any{"type": "string"}},
					"topic":         map[string]any{"type": "string"},
					"session_id":    map[string]any{"type": "string"},
				},
				"required": []string{"trigger"},
			},
		},
		{
			Name:        "roundtable_read",
			Description: "특정 round_id의 라운드테이블 산출물을 읽는다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"round_id": map[string]any{"type": "string"},
				},
				"required": []string{"round_id"},
			},
		},
		{
			Name:        "roundtable_list",
			Description: "최근 라운드테이블 목록을 읽는다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"limit": map[string]any{"type": "integer"},
				},
			},
		},
		{
			Name:        "read_team",
			Description: "특정 팀의 최신 상태와 필요하면 raw thread를 읽는다.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"role":          map[string]any{"type": "string", "enum": supportedRoles},
					"include_turns": map[string]any{"type": "boolean"},
				},
				"required": []string{"role"},
			},
		},
	}
}

func (s *MCPServer) callTool(ctx context.Context, name string, args map[string]any) (string, bool, error) {
	switch name {
	case "discover_threads":
		var input DiscoverThreadsArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		if strings.TrimSpace(input.CWD) == "" {
			input.CWD = s.service.repoRoot
		}
		result, err := s.service.DiscoverThreads(ctx, input)
		return prettyJSON(result, err)
	case "bind_targets":
		var input BindTargetsArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.BindTargets(ctx, input)
		return prettyJSON(result, err)
	case "dispatch_turn":
		var input DispatchTurnArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.DispatchTurn(ctx, input)
		return prettyJSON(result, err)
	case "broadcast_turn":
		var input BroadcastTurnArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.BroadcastTurn(ctx, input)
		return prettyJSON(result, err)
	case "route_turn":
		var input RouteTurnArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.RouteTurn(ctx, input)
		return prettyJSON(result, err)
	case "steer_round":
		var input SteerRoundArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.SteerRound(ctx, input)
		return prettyJSON(result, err)
	case "read_round_graph":
		var input ReadRoundGraphArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.ReadRoundGraph(ctx, input)
		return prettyJSON(result, err)
	case "resolve_question":
		var input ResolveQuestionArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.ResolveQuestion(ctx, input)
		return prettyJSON(result, err)
	case "close_round":
		var input CloseRoundArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.CloseRound(ctx, input)
		return prettyJSON(result, err)
	case "read_dashboard":
		result, err := s.service.ReadDashboard(ctx)
		return prettyJSON(result, err)
	case "read_team":
		var input ReadTeamArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.ReadTeam(ctx, input)
		return prettyJSON(result, err)
	case "roundtable_start":
		var input RoundtableStartArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.RoundtableStart(ctx, input)
		return prettyJSON(result, err)
	case "roundtable_read":
		var input RoundtableReadArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.RoundtableRead(ctx, input)
		return prettyJSON(result, err)
	case "roundtable_list":
		var input RoundtableListArgs
		if err := decodeInto(args, &input); err != nil {
			return "", true, err
		}
		result, err := s.service.RoundtableList(ctx, input)
		return prettyJSON(result, err)
	default:
		return "", true, fmt.Errorf("지원하지 않는 도구: %s", name)
	}
}

func (s *MCPServer) writeResult(id interface{}, result interface{}) error {
	return s.writeEnvelope(map[string]any{
		"jsonrpc": "2.0",
		"id":      id,
		"result":  result,
	})
}

func (s *MCPServer) writeError(id interface{}, code int, message string) error {
	return s.writeEnvelope(map[string]any{
		"jsonrpc": "2.0",
		"id":      id,
		"error": map[string]any{
			"code":    code,
			"message": message,
		},
	})
}

func (s *MCPServer) writeEnvelope(payload interface{}) error {
	bytes, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	bytes = append(bytes, '\n')

	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	_, err = s.out.Write(bytes)
	return err
}

func decodeInto(src interface{}, dest interface{}) error {
	payload, err := json.Marshal(src)
	if err != nil {
		return err
	}
	if len(payload) == 0 || string(payload) == "null" {
		payload = []byte("{}")
	}
	return json.Unmarshal(payload, dest)
}

func prettyJSON(result interface{}, err error) (string, bool, error) {
	if err != nil {
		return "", true, err
	}
	payload, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return "", true, err
	}
	return string(payload), false, nil
}
