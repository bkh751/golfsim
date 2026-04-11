package main

import (
	"context"
	"errors"
	"io"
	"log"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	log.SetFlags(0)

	repoRoot := os.Getenv("GOLFSIM_REPO_ROOT")
	if repoRoot == "" {
		var err error
		repoRoot, err = os.Getwd()
		if err != nil {
			log.Fatal(err)
		}
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	app := NewAppServerClient(AppServerConfig{
		Command:  "codex",
		Args:     []string{"app-server", "--listen", "stdio://"},
		RepoRoot: repoRoot,
	})
	defer app.Close()

	service, err := NewService(repoRoot, app)
	if err != nil {
		log.Fatal(err)
	}

	server := NewMCPServer(os.Stdin, os.Stdout, service)
	if err := server.Run(ctx); err != nil && !errors.Is(err, io.EOF) {
		log.Fatal(err)
	}
}
