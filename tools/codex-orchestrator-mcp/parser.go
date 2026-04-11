package main

import (
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

var strictSectionPattern = regexp.MustCompile(`(?m)^(상태|이해한 범위|결과|blocker|다음 요청)\s*:\s*(.*)$`)
var relaxedSectionPattern = regexp.MustCompile(`(?im)^(?:#{1,3}\s*)?(상태|status|state|이해한 범위|understanding|scope|owner|결과|result|summary|결과 요약|blocker|risk|다음 요청|next|next request|requests?|ask)\s*[:\-]?\s*(.*)$`)

type sectionMatch struct {
	Name       string
	Start      int
	ContentPos int
	FirstLine  string
}

func ParseTeamResponse(text string) (*ParsedSections, error) {
	trimmed := strings.TrimSpace(text)
	parsed := &ParsedSections{
		Raw:             trimmed,
		ParseStatus:     "unparsed",
		ParseMode:       "unparsed",
		ParseConfidence: 0.0,
		ProtocolStatus:  "review",
	}
	if trimmed == "" {
		parsed.Missing = []string{"상태", "이해한 범위", "결과", "blocker", "다음 요청"}
		return parsed, fmt.Errorf("응답 본문이 비어 있습니다")
	}

	var ackMeta *ParsedSections
	if packet, rest := extractLeadingAckPacket(trimmed); len(packet) > 0 {
		ackMeta = &ParsedSections{}
		fillParsedFromCompact(ackMeta, packet)
		finalizeProgressMeta(ackMeta)
		if strings.TrimSpace(rest) != "" {
			trimmed = strings.TrimSpace(rest)
		}
	}

	if sections, missing := extractSections(trimmed, strictSectionPattern, normalizeStrictSection); len(sections) > 0 && len(missing) == 0 {
		fillParsedSections(parsed, sections)
		parsed.ParseStatus = "ok"
		parsed.ParseMode = "strict"
		parsed.ParseConfidence = 1.0
		finalizeParsed(parsed)
		mergeProgressMeta(parsed, ackMeta)
		return parsed, nil
	}

	if sections, missing := extractSections(trimmed, relaxedSectionPattern, normalizeRelaxedSection); len(sections) > 0 {
		fillParsedSections(parsed, sections)
		parsed.Missing = missing
		if len(missing) == 0 {
			parsed.ParseStatus = "relaxed"
			parsed.ParseMode = "relaxed"
			parsed.ParseConfidence = 0.8
		} else {
			parsed.ParseStatus = "partial"
			parsed.ParseMode = "relaxed"
			parsed.ParseConfidence = 0.6
		}
		finalizeParsed(parsed)
		mergeProgressMeta(parsed, ackMeta)
		return parsed, nil
	}

	if packet := extractCompactPacket(trimmed); len(packet) > 0 {
		fillParsedFromCompact(parsed, packet)
		parsed.Missing = requiredMissing(compactSections(packet))
		if len(parsed.Missing) == 0 {
			parsed.ParseStatus = "relaxed"
			parsed.ParseMode = "compact"
			parsed.ParseConfidence = 0.85
		} else {
			parsed.ParseStatus = "partial"
			parsed.ParseMode = "compact"
			parsed.ParseConfidence = 0.68
		}
		finalizeParsed(parsed)
		mergeProgressMeta(parsed, ackMeta)
		return parsed, nil
	}

	parsed.ParseStatus = "partial"
	parsed.ParseMode = "heuristic"
	parsed.ParseConfidence = 0.35
	parsed.Missing = []string{"상태", "이해한 범위", "결과", "blocker", "다음 요청"}
	parsed.Result = heuristicSummary(trimmed)
	hydrateHeuristicFields(parsed)
	finalizeParsed(parsed)
	mergeProgressMeta(parsed, ackMeta)
	return parsed, nil
}

func extractSections(text string, pattern *regexp.Regexp, normalize func(string) string) (map[string]string, []string) {
	matches := pattern.FindAllStringSubmatchIndex(text, -1)
	if len(matches) == 0 {
		return nil, requiredMissing(nil)
	}

	found := make([]sectionMatch, 0, len(matches))
	for _, idx := range matches {
		name := normalize(strings.TrimSpace(text[idx[2]:idx[3]]))
		if name == "" {
			continue
		}
		found = append(found, sectionMatch{
			Name:       name,
			Start:      idx[0],
			ContentPos: idx[1],
			FirstLine:  strings.TrimSpace(text[idx[4]:idx[5]]),
		})
	}
	sort.Slice(found, func(i, j int) bool {
		return found[i].Start < found[j].Start
	})

	sections := map[string]string{}
	for i, match := range found {
		end := len(text)
		if i+1 < len(found) {
			end = found[i+1].Start
		}
		body := strings.TrimSpace(text[match.ContentPos:end])
		if match.FirstLine != "" && !strings.HasPrefix(body, match.FirstLine) {
			body = strings.TrimSpace(match.FirstLine + "\n" + body)
		}
		sections[match.Name] = body
	}
	return sections, requiredMissing(sections)
}

func normalizeStrictSection(value string) string {
	switch strings.TrimSpace(value) {
	case "상태", "이해한 범위", "결과", "blocker", "다음 요청":
		return strings.TrimSpace(value)
	default:
		return ""
	}
}

func normalizeRelaxedSection(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "상태", "status", "state":
		return "상태"
	case "이해한 범위", "understanding", "scope", "owner":
		return "이해한 범위"
	case "결과", "result", "summary", "결과 요약":
		return "결과"
	case "blocker", "risk":
		return "blocker"
	case "다음 요청", "next", "next request", "requests", "ask":
		return "다음 요청"
	default:
		return ""
	}
}

func requiredMissing(sections map[string]string) []string {
	required := []string{"상태", "이해한 범위", "결과", "blocker", "다음 요청"}
	missing := make([]string, 0)
	for _, key := range required {
		if sections == nil {
			missing = append(missing, key)
			continue
		}
		if _, ok := sections[key]; !ok {
			missing = append(missing, key)
		}
	}
	return missing
}

func fillParsedSections(parsed *ParsedSections, sections map[string]string) {
	parsed.Status = strings.TrimSpace(sections["상태"])
	parsed.Scope = strings.TrimSpace(sections["이해한 범위"])
	parsed.Result = strings.TrimSpace(sections["결과"])
	parsed.Blocker = strings.TrimSpace(sections["blocker"])
	parsed.NextRequest = strings.TrimSpace(sections["다음 요청"])
}

func fillParsedFromCompact(parsed *ParsedSections, packet map[string]string) {
	parsed.Status = compactValue(packet, "상태")
	parsed.Scope = compactValue(packet, "이해한 범위")
	parsed.Result = compactValue(packet, "결과")
	parsed.Blocker = compactValue(packet, "blocker")
	parsed.NextRequest = compactValue(packet, "다음 요청")
	parsed.Intent = compactValue(packet, "intent")
	parsed.SteerSuggestion = compactValue(packet, "steer_suggestion")
	parsed.ProtocolStatus = compactValue(packet, "protocol_status")
	parsed.Priority = normalizePriority(compactValue(packet, "priority"))
	parsed.Interrupt = parseCompactBool(compactValue(packet, "interrupt"))
	parsed.Codec = normalizeCodec(compactValue(packet, "codec"))
	parsed.TokenBudget = parseCompactInt(compactValue(packet, "token_budget"))
	parsed.CompressionHint = strings.TrimSpace(compactValue(packet, "compression_hint"))
	parsed.Lane = normalizeLane(compactValue(packet, "lane"))
	parsed.EtaSeconds = parseCompactInt(compactValue(packet, "eta_seconds"))
	parsed.ProgressState = normalizeProgressState(compactValue(packet, "progress_state"))
	if value := strings.TrimSpace(compactValue(packet, "more_coming")); value != "" {
		parsed.MoreComing = parseCompactBool(value)
	}
	if value := strings.TrimSpace(compactValue(packet, "confidence")); value != "" {
		if parsedValue, err := strconv.ParseFloat(value, 64); err == nil {
			parsed.Confidence = clampConfidence(parsedValue)
		}
	}
	if value := strings.TrimSpace(compactValue(packet, "needs_reply")); value != "" {
		parsed.NeedsReply = parseCompactBool(value)
	}
	parsed.Requests = compactList(packet["requests"])
	parsed.Decisions = compactList(packet["decisions"])
	parsed.Risks = compactList(packet["risks"])
	parsed.EvidenceRefs = compactList(packet["evidence_refs"])
}

func finalizeParsed(parsed *ParsedSections) {
	if parsed.Result == "" {
		parsed.Result = heuristicSummary(parsed.Raw)
	}
	if parsed.Blocker == "" {
		parsed.Blocker = "없음"
	}
	if parsed.NextRequest == "" {
		parsed.NextRequest = "없음"
	}
	parsed.Summary = firstNonEmpty(firstSentence(parsed.Result), firstSentence(parsed.Raw), "-")
	parsed.Requests = tokenizeField(parsed.NextRequest)
	if !parsed.NeedsReply {
		parsed.NeedsReply = len(parsed.Requests) > 0
	}
	parsed.Risks = tokenizeRisk(parsed.Blocker)
	parsed.Decisions = extractBulletLines(parsed.Result, "결정")
	if len(parsed.EvidenceRefs) == 0 {
		parsed.EvidenceRefs = extractEvidenceRefs(parsed.Raw)
	}
	if parsed.Confidence == 0 {
		parsed.Confidence = clampConfidence(parsed.ParseConfidence)
	} else {
		parsed.Confidence = clampConfidence(parsed.Confidence)
	}
	parsed.Priority = normalizePriority(parsed.Priority)
	parsed.Codec = normalizeCodec(parsed.Codec)
	if parsed.Interrupt && parsed.Priority != "interrupt" {
		parsed.Priority = "interrupt"
	}
	parsed.Lane = normalizeLane(firstNonEmpty(parsed.Lane, interruptLane(parsed.Interrupt, parsed.Priority)))
	if parsed.CompressionHint == "" && parsed.Codec != "plain" {
		parsed.CompressionHint = "primitive"
	}
	if parsed.TokenBudget < 0 {
		parsed.TokenBudget = 0
	}
	finalizeProgressMeta(parsed)
	if parsed.Intent == "" {
		switch {
		case parsed.NeedsReply:
			parsed.Intent = "question"
		case len(parsed.Decisions) > 0:
			parsed.Intent = "decision"
		default:
			parsed.Intent = "inform"
		}
	}
	if parsed.ProtocolStatus == "" || parsed.ProtocolStatus == "review" {
		switch {
		case parsed.Blocker != "" && parsed.Blocker != "없음":
			parsed.ProtocolStatus = "blocked"
		case parsed.ParseStatus == "partial":
			parsed.ProtocolStatus = "review"
		default:
			parsed.ProtocolStatus = "accepted"
		}
	}
}

func finalizeProgressMeta(parsed *ParsedSections) {
	if parsed == nil {
		return
	}
	if parsed.ProgressState == "" {
		switch normalizeProgressState(parsed.Status) {
		case "ack", "work", "blocked", "final":
			parsed.ProgressState = normalizeProgressState(parsed.Status)
		}
	}
	if parsed.ProgressState == "" && parsed.MoreComing {
		parsed.ProgressState = "work"
	}
	if parsed.ProgressState == "final" {
		parsed.MoreComing = false
	}
	if parsed.ProgressState == "ack" && !parsed.MoreComing {
		parsed.MoreComing = true
	}
	if parsed.EtaSeconds < 0 {
		parsed.EtaSeconds = 0
	}
}

func mergeProgressMeta(parsed *ParsedSections, ackMeta *ParsedSections) {
	if parsed == nil || ackMeta == nil {
		return
	}
	if parsed.EtaSeconds == 0 && ackMeta.EtaSeconds > 0 {
		parsed.EtaSeconds = ackMeta.EtaSeconds
	}
	if parsed.ProgressState == "" && ackMeta.ProgressState != "ack" {
		parsed.ProgressState = ackMeta.ProgressState
	}
	if ackMeta.MoreComing && parsed.ProgressState == "" {
		parsed.MoreComing = true
	}
}

func heuristicSummary(text string) string {
	lines := splitLines(text)
	if len(lines) == 0 {
		return "-"
	}
	summary := strings.Join(lines, " ")
	if len(summary) > 220 {
		return strings.TrimSpace(summary[:217]) + "..."
	}
	return summary
}

func hydrateHeuristicFields(parsed *ParsedSections) {
	lines := splitLines(parsed.Raw)
	resultLines := make([]string, 0, len(lines))
	for _, line := range lines {
		trimmed := strings.TrimSpace(strings.TrimLeft(line, "-*• "))
		if trimmed == "" {
			continue
		}
		lower := strings.ToLower(trimmed)
		switch {
		case hasAnyPrefix(lower, "st:", "status:", "state:"):
			parsed.Status = firstNonEmpty(parsed.Status, fieldValue(trimmed))
		case hasAnyPrefix(lower, "owner:", "scope:", "understanding:"):
			parsed.Scope = firstNonEmpty(parsed.Scope, fieldValue(trimmed))
		case hasAnyPrefix(lower, "rs:", "result:", "summary:"):
			parsed.Result = firstNonEmpty(fieldValue(trimmed), parsed.Result)
		case hasAnyPrefix(lower, "rk:", "risk:", "blocker:"):
			parsed.Blocker = firstNonEmpty(parsed.Blocker, fieldValue(trimmed))
		case hasAnyPrefix(lower, "ask:", "rq:", "next:", "next_request:", "request:"):
			parsed.NextRequest = firstNonEmpty(parsed.NextRequest, fieldValue(trimmed))
		default:
			resultLines = append(resultLines, trimmed)
		}
	}
	if len(resultLines) > 0 && (parsed.Result == "" || parsed.Result == heuristicSummary(parsed.Raw)) {
		parsed.Result = heuristicSummary(strings.Join(resultLines, " "))
	}
}

func hasAnyPrefix(value string, prefixes ...string) bool {
	for _, prefix := range prefixes {
		if strings.HasPrefix(value, prefix) {
			return true
		}
	}
	return false
}

func fieldValue(value string) string {
	parts := strings.SplitN(value, ":", 2)
	if len(parts) != 2 {
		return strings.TrimSpace(value)
	}
	return strings.TrimSpace(parts[1])
}

func extractCompactPacket(text string) map[string]string {
	candidate := strings.NewReplacer("\r\n", "\n", "\n", " | ", ";", " | ").Replace(text)
	chunks := strings.Split(candidate, "|")
	packet := map[string]string{}
	matched := 0
	for _, chunk := range chunks {
		chunk = strings.TrimSpace(chunk)
		if chunk == "" {
			continue
		}
		sep := ":"
		if !strings.Contains(chunk, ":") && strings.Contains(chunk, "=") {
			sep = "="
		}
		if !strings.Contains(chunk, sep) {
			continue
		}
		parts := strings.SplitN(chunk, sep, 2)
		key := normalizeCompactKey(parts[0])
		if key == "" {
			continue
		}
		packet[key] = strings.TrimSpace(parts[1])
		matched++
	}
	if matched < 3 {
		return nil
	}
	if packet["결과"] == "" && packet["summary"] == "" && packet["상태"] == "" {
		return nil
	}
	return packet
}

func extractLeadingAckPacket(text string) (map[string]string, string) {
	lines := strings.Split(strings.ReplaceAll(text, "\r\n", "\n"), "\n")
	if len(lines) == 0 {
		return nil, ""
	}
	first := strings.TrimSpace(lines[0])
	packet := extractCompactPacket(first)
	if len(packet) == 0 {
		return nil, ""
	}
	progress := normalizeProgressState(compactValue(packet, "progress_state"))
	if progress == "" {
		progress = normalizeProgressState(compactValue(packet, "상태"))
	}
	if progress == "" && compactValue(packet, "eta_seconds") == "" && compactValue(packet, "more_coming") == "" {
		return nil, ""
	}
	rest := ""
	if len(lines) > 1 {
		rest = strings.TrimSpace(strings.Join(lines[1:], "\n"))
	}
	return packet, rest
}

func normalizeCompactKey(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "st", "status", "state":
		return "상태"
	case "pg", "progress", "progress_state", "work":
		return "progress_state"
	case "sc", "scope", "understanding", "owner", "ow":
		return "이해한 범위"
	case "rs", "res", "result", "summary", "sum":
		return "결과"
	case "bk", "blocker", "risk", "rk":
		return "blocker"
	case "rq", "next", "next_request", "req", "request", "ask":
		return "다음 요청"
	case "in", "intent":
		return "intent"
	case "cf", "conf", "confidence":
		return "confidence"
	case "nr", "needs_reply", "reply":
		return "needs_reply"
	case "dec", "decision", "decisions":
		return "decisions"
	case "ev", "evidence", "evidence_refs":
		return "evidence_refs"
	case "sg", "steer", "steer_suggestion":
		return "steer_suggestion"
	case "ps", "protocol", "protocol_status":
		return "protocol_status"
	case "cd", "codec":
		return "codec"
	case "pr", "priority":
		return "priority"
	case "ix", "interrupt", "int":
		return "interrupt"
	case "tb", "token_budget", "budget":
		return "token_budget"
	case "ch", "compression", "compression_hint":
		return "compression_hint"
	case "ln", "lane":
		return "lane"
	case "eta", "eta_seconds":
		return "eta_seconds"
	case "more", "more_coming", "m":
		return "more_coming"
	case "requests":
		return "requests"
	case "risks":
		return "risks"
	default:
		return ""
	}
}

func normalizeProgressState(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "ack":
		return "ack"
	case "work", "working", "streaming":
		return "work"
	case "blocked", "block":
		return "blocked"
	case "final", "done", "complete", "completed":
		return "final"
	default:
		return ""
	}
}

func compactSections(packet map[string]string) map[string]string {
	if len(packet) == 0 {
		return nil
	}
	sections := map[string]string{}
	for _, key := range []string{"상태", "이해한 범위", "결과", "blocker", "다음 요청"} {
		if value := compactValue(packet, key); value != "" {
			sections[key] = value
		}
	}
	return sections
}

func compactValue(packet map[string]string, key string) string {
	return strings.TrimSpace(packet[key])
}

func compactList(value string) []string {
	value = strings.TrimSpace(value)
	if value == "" || strings.EqualFold(value, "none") || value == "없음" {
		return nil
	}
	raw := strings.FieldsFunc(value, func(r rune) bool {
		return r == ',' || r == '/' || r == ';'
	})
	items := make([]string, 0, len(raw))
	for _, item := range raw {
		item = strings.TrimSpace(item)
		if item == "" {
			continue
		}
		items = append(items, item)
	}
	return items
}

func parseCompactBool(value string) bool {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "t", "y", "yes", "urgent", "interrupt":
		return true
	default:
		return false
	}
}

func parseCompactInt(value string) int {
	parsed, err := strconv.Atoi(strings.TrimSpace(value))
	if err != nil {
		return 0
	}
	return parsed
}

func tokenizeField(value string) []string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" || trimmed == "없음" || trimmed == "none" {
		return nil
	}
	lines := extractBulletLines(trimmed, "")
	if len(lines) > 0 {
		return lines
	}
	return []string{trimmed}
}

func tokenizeRisk(value string) []string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" || trimmed == "없음" || trimmed == "none" || trimmed == "- 없음" {
		return nil
	}
	lines := extractBulletLines(trimmed, "")
	if len(lines) > 0 {
		return lines
	}
	return []string{trimmed}
}

func extractBulletLines(text string, contains string) []string {
	lines := splitLines(text)
	items := make([]string, 0)
	for _, line := range lines {
		cleaned := strings.TrimSpace(strings.TrimLeft(line, "-*0123456789. "))
		if cleaned == "" {
			continue
		}
		if contains != "" && !strings.Contains(cleaned, contains) {
			continue
		}
		items = append(items, cleaned)
	}
	return items
}

func extractEvidenceRefs(text string) []string {
	lines := splitLines(text)
	refs := make([]string, 0)
	for _, line := range lines {
		if strings.Contains(line, "evidence") || strings.Contains(line, "증거") || strings.Contains(line, "render_payload") {
			refs = append(refs, line)
		}
	}
	if len(refs) > 4 {
		return refs[:4]
	}
	return refs
}

func firstSentence(text string) string {
	for _, sep := range []string{"\n", ". ", "。", "! ", "? "} {
		if idx := strings.Index(text, sep); idx > 0 {
			return strings.TrimSpace(text[:idx])
		}
	}
	return strings.TrimSpace(text)
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func clampConfidence(value float64) float64 {
	switch {
	case value < 0:
		return 0
	case value > 1:
		return 1
	default:
		return value
	}
}

func splitLines(text string) []string {
	raw := strings.Split(strings.ReplaceAll(text, "\r\n", "\n"), "\n")
	lines := make([]string, 0, len(raw))
	for _, line := range raw {
		line = strings.TrimSpace(line)
		if line != "" {
			lines = append(lines, line)
		}
	}
	return lines
}
