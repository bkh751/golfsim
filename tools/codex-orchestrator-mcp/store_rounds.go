package main

import (
	"crypto/sha1"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type roundQueueEvent struct {
	Event     string    `json:"event"`
	RoundID   string    `json:"round_id"`
	IssueRef  string    `json:"issue_ref,omitempty"`
	Trigger   string    `json:"trigger"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

func (s *Store) CreateRoundRequest(args RoundtableStartArgs, source string) (RoundArtifact, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if err := s.ensureHarnessDirsLocked(); err != nil {
		return RoundArtifact{}, false, err
	}

	fingerprint := roundFingerprint(args.IssueRef, args.Topic, args.ChangedFiles)
	rounds, err := s.loadRoundsLocked()
	if err != nil {
		return RoundArtifact{}, false, err
	}
	for _, round := range rounds {
		if round.ChangeFingerprint == fingerprint && (round.Status == "pending" || round.Status == "running") {
			return round, true, nil
		}
	}

	now := time.Now().UTC()
	round := RoundArtifact{
		ID:                roundID(now, fingerprint),
		IssueRef:          strings.TrimSpace(args.IssueRef),
		Trigger:           strings.TrimSpace(args.Trigger),
		Topic:             strings.TrimSpace(args.Topic),
		ChangedFiles:      normalizeChangedFiles(args.ChangedFiles),
		ChangeFingerprint: fingerprint,
		SessionID:         strings.TrimSpace(args.SessionID),
		Source:            source,
		Status:            "pending",
		CreatedAt:         now,
		UpdatedAt:         now,
		Participants:      append([]string(nil), supportedRoles...),
		RequiredRoles:     append([]string(nil), supportedRequiredRoles...),
		OptionalRoles:     append([]string(nil), supportedOptionalRoles...),
		Policy: RoundPolicy{
			Mode:            "steered_mesh",
			Goal:            strings.TrimSpace(args.Topic),
			AllowedRoles:    append([]string(nil), supportedRoles...),
			RequiredRoles:   append([]string(nil), supportedRequiredRoles...),
			OptionalRoles:   append([]string(nil), supportedOptionalRoles...),
			DefaultCodec:    "compact",
			DefaultPriority: "normal",
			Budget: RoundBudget{
				MaxHopsPerQuestion:  8,
				MaxUnanswered:       2,
				MaxTokensPerPacket:  96,
				InterruptWindowSecs: 15,
			},
		},
		Messages:          []RoundMessage{},
		Edges:             []RoundEdge{},
		OpenQuestions:     []RoundQuestion{},
		ResolvedQuestions: []RoundQuestion{},
		SteeringEvents:    []SteeringEvent{},
	}
	if err := s.writeJSONLocked(s.roundPath(round.ID), round); err != nil {
		return RoundArtifact{}, false, err
	}
	if err := s.appendRoundQueueLocked(roundQueueEvent{
		Event:     "queued",
		RoundID:   round.ID,
		IssueRef:  round.IssueRef,
		Trigger:   round.Trigger,
		Status:    round.Status,
		CreatedAt: now,
		UpdatedAt: now,
	}); err != nil {
		return RoundArtifact{}, false, err
	}
	return round, false, nil
}

func (s *Store) LoadRound(roundID string) (*RoundArtifact, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.loadRoundLocked(roundID)
}

func (s *Store) SaveRound(round RoundArtifact) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.ensureHarnessDirsLocked(); err != nil {
		return err
	}
	round.ChangedFiles = normalizeChangedFiles(round.ChangedFiles)
	return s.writeJSONLocked(s.roundPath(round.ID), round)
}

func (s *Store) ListRounds(limit int) ([]RoundArtifact, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	rounds, err := s.loadRoundsLocked()
	if err != nil {
		return nil, err
	}
	sort.Slice(rounds, func(i, j int) bool {
		return rounds[i].CreatedAt.After(rounds[j].CreatedAt)
	})
	if limit > 0 && len(rounds) > limit {
		rounds = rounds[:limit]
	}
	return rounds, nil
}

func (s *Store) loadRoundLocked(roundID string) (*RoundArtifact, error) {
	path := s.roundPath(roundID)
	var round RoundArtifact
	if err := s.readJSONLocked(path, &round); err != nil {
		return nil, err
	}
	if round.ID == "" {
		return nil, nil
	}
	round.ChangedFiles = normalizeChangedFiles(round.ChangedFiles)
	return &round, nil
}

func (s *Store) loadRoundsLocked() ([]RoundArtifact, error) {
	dir := s.roundsDir()
	if _, err := os.Stat(dir); err != nil {
		if os.IsNotExist(err) {
			return []RoundArtifact{}, nil
		}
		return nil, err
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	rounds := make([]RoundArtifact, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		var round RoundArtifact
		if err := s.readJSONLocked(filepath.Join(dir, entry.Name()), &round); err != nil {
			return nil, err
		}
		if round.ID == "" {
			continue
		}
		round.ChangedFiles = normalizeChangedFiles(round.ChangedFiles)
		rounds = append(rounds, round)
	}
	return rounds, nil
}

func (s *Store) appendRoundQueueLocked(event roundQueueEvent) error {
	file, err := os.OpenFile(s.roundQueuePath(), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return err
	}
	defer file.Close()

	payload, err := json.Marshal(event)
	if err != nil {
		return err
	}
	_, err = file.Write(append(payload, '\n'))
	return err
}

func (s *Store) ensureHarnessDirsLocked() error {
	for _, dir := range []string{s.harnessDir(), s.roundsDir(), s.reviewsDir(), s.backlogDraftsDir()} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return err
		}
	}
	return nil
}

func (s *Store) harnessDir() string {
	return filepath.Join(s.repoRoot, ".codex", "harness")
}

func (s *Store) roundsDir() string {
	return filepath.Join(s.harnessDir(), "rounds")
}

func (s *Store) reviewsDir() string {
	return filepath.Join(s.harnessDir(), "reviews")
}

func (s *Store) backlogDraftsDir() string {
	return filepath.Join(s.harnessDir(), "backlog-drafts")
}

func (s *Store) roundPath(roundID string) string {
	return filepath.Join(s.roundsDir(), fmt.Sprintf("%s.json", roundID))
}

func (s *Store) roundQueuePath() string {
	return filepath.Join(s.harnessDir(), "round-requests.jsonl")
}

func roundFingerprint(issueRef, topic string, changedFiles []string) string {
	normalized := normalizeChangedFiles(changedFiles)
	parts := append([]string{strings.TrimSpace(issueRef), strings.TrimSpace(topic)}, normalized...)
	sum := sha1.Sum([]byte(strings.Join(parts, "\n")))
	return hex.EncodeToString(sum[:8])
}

func roundID(now time.Time, fingerprint string) string {
	short := fingerprint
	if len(short) > 8 {
		short = short[:8]
	}
	return fmt.Sprintf("round-%s-%s", now.UTC().Format("20060102T150405"), short)
}

func normalizeChangedFiles(changedFiles []string) []string {
	seen := map[string]struct{}{}
	normalized := make([]string, 0, len(changedFiles))
	for _, path := range changedFiles {
		path = strings.TrimSpace(path)
		if path == "" {
			continue
		}
		if _, ok := seen[path]; ok {
			continue
		}
		seen[path] = struct{}{}
		normalized = append(normalized, path)
	}
	sort.Strings(normalized)
	return normalized
}
