package main

import (
	"context"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"
)

type PromptBuilder struct {
	repoRoot string
}

func NewPromptBuilder(repoRoot string) *PromptBuilder {
	return &PromptBuilder{repoRoot: repoRoot}
}

func (p *PromptBuilder) Build(ctx context.Context, role, parentIssue, taskRequest, confirmedContext, blockerContext, promptOverride string) (string, error) {
	if strings.TrimSpace(promptOverride) != "" {
		return strings.TrimSpace(promptOverride) + "\n", nil
	}

	script := filepath.Join(p.repoRoot, "skills", "relay-prompts", "scripts", "build_prompt.py")
	args := []string{
		script,
		"--role", role,
		"--parent-issue", parentIssue,
		"--task-request", taskRequest,
	}
	if strings.TrimSpace(confirmedContext) != "" {
		args = append(args, "--confirmed-context", confirmedContext)
	}
	if strings.TrimSpace(blockerContext) != "" {
		args = append(args, "--blocker-context", blockerContext)
	}

	cmd := exec.CommandContext(ctx, "python3", args...)
	cmd.Dir = p.repoRoot
	out, err := cmd.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("relay prompt 생성 실패: %w: %s", err, strings.TrimSpace(string(out)))
	}
	prompt := strings.TrimSpace(string(out))
	if prompt == "" {
		return "", fmt.Errorf("relay prompt가 비어 있습니다")
	}
	return prompt + "\n", nil
}
