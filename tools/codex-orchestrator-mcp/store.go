package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type Store struct {
	repoRoot string
	mu       sync.Mutex
}

func NewStore(repoRoot string) *Store {
	return &Store{repoRoot: repoRoot}
}

func (s *Store) EnsureDirs() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if err := os.MkdirAll(s.promptsDir(), 0o755); err != nil {
		return err
	}
	return s.ensureHarnessDirsLocked()
}

func (s *Store) LoadTargets() (Targets, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.loadTargetsLocked()
}

func (s *Store) SaveTargets(targets Targets) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.writeJSONLocked(s.targetsPath(), targets)
}

func (s *Store) LoadState() (map[string]TeamState, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.loadStateLocked()
}

func (s *Store) SaveState(state map[string]TeamState) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.writeJSONLocked(s.statePath(), state)
}

func (s *Store) UpdateState(role string, updater func(*TeamState)) (TeamState, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	state, err := s.loadStateLocked()
	if err != nil {
		return TeamState{}, err
	}
	current := state[role]
	if current.Role == "" {
		current.Role = role
	}
	updater(&current)
	state[role] = current
	if err := s.writeJSONLocked(s.statePath(), state); err != nil {
		return TeamState{}, err
	}
	return current, nil
}

func (s *Store) AppendDispatch(event dispatchEvent) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if err := os.MkdirAll(s.orchestratorDir(), 0o755); err != nil {
		return err
	}
	file, err := os.OpenFile(s.dispatchesPath(), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return err
	}
	defer file.Close()

	payload, err := json.Marshal(event)
	if err != nil {
		return err
	}
	if _, err := file.Write(append(payload, '\n')); err != nil {
		return err
	}
	return nil
}

func (s *Store) WritePromptSnapshot(role, prompt string, now time.Time) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if err := os.MkdirAll(s.promptsDir(), 0o755); err != nil {
		return "", err
	}
	filename := fmt.Sprintf("%s-%s.md", now.UTC().Format("20060102T150405.000000000Z"), role)
	path := filepath.Join(s.promptsDir(), filename)
	if err := os.WriteFile(path, []byte(prompt), 0o644); err != nil {
		return "", err
	}
	return path, nil
}

func (s *Store) loadTargetsLocked() (Targets, error) {
	targets := Targets{}
	if err := s.readJSONLocked(s.targetsPath(), &targets); err != nil {
		return nil, err
	}
	return targets, nil
}

func (s *Store) loadStateLocked() (map[string]TeamState, error) {
	state := map[string]TeamState{}
	if err := s.readJSONLocked(s.statePath(), &state); err != nil {
		return nil, err
	}
	return state, nil
}

func (s *Store) readJSONLocked(path string, dest interface{}) error {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	defer file.Close()

	decoder := json.NewDecoder(bufio.NewReader(file))
	if err := decoder.Decode(dest); err != nil {
		return fmt.Errorf("%s 읽기 실패: %w", path, err)
	}
	return nil
}

func (s *Store) writeJSONLocked(path string, value interface{}) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}

	payload, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	payload = append(payload, '\n')
	return os.WriteFile(path, payload, 0o644)
}

func (s *Store) orchestratorDir() string {
	return filepath.Join(s.repoRoot, ".codex", "orchestrator")
}

func (s *Store) promptsDir() string {
	return filepath.Join(s.orchestratorDir(), "prompts")
}

func (s *Store) targetsPath() string {
	return filepath.Join(s.orchestratorDir(), "targets.json")
}

func (s *Store) statePath() string {
	return filepath.Join(s.orchestratorDir(), "state.json")
}

func (s *Store) dispatchesPath() string {
	return filepath.Join(s.orchestratorDir(), "dispatches.jsonl")
}
