// alert-forwarder: a small Go HTTP service, shaped like a Dezerv Go service, that receives an alert webhook and asks the
// payments on-call agent (AgentCore Runtime) to investigate, streaming the diagnosis to stdout.
//
//	RUNTIME_ARN=arn:aws:bedrock-agentcore:... go run . -addr :8080
//	curl -s localhost:8080/alert -d @data/alerts/inc-sip-timeout.json
//
// Production mapping (see README): alert -> event intake (RUN-01) -> agent, with a fail-safe (NFR-03): if the agent has not
// acknowledged within the deadline, page a human anyway.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/bedrockagentcore"
)

type Invoker interface {
	Invoke(ctx context.Context, sessionID string, payload []byte) (io.ReadCloser, error)
}

type runtimeInvoker struct {
	client *bedrockagentcore.Client
	arn    string
}

func (r runtimeInvoker) Invoke(ctx context.Context, sessionID string, payload []byte) (io.ReadCloser, error) {
	out, err := r.client.InvokeAgentRuntime(ctx, &bedrockagentcore.InvokeAgentRuntimeInput{
		AgentRuntimeArn: aws.String(r.arn), RuntimeSessionId: aws.String(sessionID), Payload: payload,
		ContentType: aws.String("application/json"), Accept: aws.String("application/json"),
	})
	if err != nil {
		return nil, err
	}
	return out.Response, nil
}

// fingerprint makes a stable session id per alert: repeat alerts for the same incident reuse the session.
// Runtime session ids must be at least 33 characters.
func fingerprint(alert map[string]any) string {
	key := fmt.Sprint(alert["alert"], "|", alert["service"], "|", alert["window_start"])
	h := sha256.Sum256([]byte(key))
	return "alert-" + hex.EncodeToString(h[:])[:32]
}

func buildPrompt(alert map[string]any) string {
	b, _ := json.MarshalIndent(alert, "", " ")
	return "Investigate this alert and follow your workflow:\n" + string(b)
}

type Server struct {
	inv     Invoker
	timeout time.Duration
	log     *slog.Logger
	out     io.Writer
}

func (s *Server) handleAlert(w http.ResponseWriter, r *http.Request) {
	var alert map[string]any
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&alert); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	sid := fingerprint(alert)
	// Same field names as Lab A's service logs (CTX-05): commit and caller make log lines citable.
	lg := s.log.With("session_id", sid, "service", alert["service"], "caller", "alert-forwarder/main.go:handleAlert", "commit", commit())
	ctx, cancel := context.WithTimeout(r.Context(), s.timeout)
	defer cancel()
	payload, _ := json.Marshal(map[string]any{"prompt": buildPrompt(alert), "persona": "oncall", "task_id": sid, "session_id": sid})
	lg.Info("invoking agent", "alert", alert["alert"])
	body, err := s.inv.Invoke(ctx, sid, payload)
	if err != nil {
		lg.Error("agent invoke failed: paging a human (fail-safe)", "err", err)
		http.Error(w, "agent unavailable; escalated to human on-call", http.StatusBadGateway)
		return
	}
	defer body.Close()
	n, err := stream(s.out, body)
	if err != nil {
		lg.Error("stream interrupted", "err", err, "bytes", n)
		http.Error(w, "stream interrupted", http.StatusBadGateway)
		return
	}
	lg.Info("diagnosis complete", "bytes", n)
	w.WriteHeader(http.StatusAccepted)
	fmt.Fprintf(w, "diagnosis streamed to stdout (%d bytes), session %s\n", n, sid)
}

// stream copies the response to out chunk by chunk, so long diagnoses appear as they arrive. If the runtime returns the
// agent's JSON envelope ({"answer": ...}) it is unwrapped at the end for readability.
func stream(out io.Writer, body io.Reader) (int64, error) {
	var total int64
	buf := make([]byte, 4096)
	var all strings.Builder
	for {
		n, err := body.Read(buf)
		if n > 0 {
			total += int64(n)
			all.Write(buf[:n])
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			return total, err
		}
	}
	text := all.String()
	var env struct {
		Answer string `json:"answer"`
	}
	if json.Unmarshal([]byte(text), &env) == nil && env.Answer != "" {
		text = env.Answer
	}
	fmt.Fprintln(out, text)
	return total, nil
}

func commit() string {
	if c := os.Getenv("GIT_COMMIT"); c != "" {
		return c
	}
	return "dev"
}

func main() {
	addr := flag.String("addr", ":8080", "listen address")
	timeout := flag.Duration("timeout", 10*time.Minute, "per-alert deadline; after it, page a human (NFR-03)")
	flag.Parse()
	arn := os.Getenv("RUNTIME_ARN")
	if arn == "" {
		slog.Error("RUNTIME_ARN is required")
		os.Exit(2)
	}
	// The runtime ARN carries its region (arn:aws:bedrock-agentcore:<region>:...). Use it, not AWS_REGION: a stray AWS_REGION in the
	// environment points the client at the wrong region and the runtime "does not exist" (a 404 that looks like an agent problem).
	region, err := regionFromARN(arn)
	if err != nil {
		slog.Error("bad RUNTIME_ARN", "err", err)
		os.Exit(2)
	}
	cfg, err := config.LoadDefaultConfig(context.Background(), config.WithRegion(region))
	if err != nil {
		slog.Error("aws config", "err", err)
		os.Exit(1)
	}
	srv := &Server{inv: runtimeInvoker{bedrockagentcore.NewFromConfig(cfg), arn}, timeout: *timeout, log: slog.New(slog.NewJSONHandler(os.Stderr, nil)), out: os.Stdout}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /alert", srv.handleAlert)
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) { fmt.Fprintln(w, "ok") })
	slog.Info("listening", "addr", *addr)
	if err := http.ListenAndServe(*addr, mux); err != nil {
		slog.Error("server", "err", err)
		os.Exit(1)
	}
}

// regionFromARN extracts <region> from arn:<partition>:bedrock-agentcore:<region>:<account>:runtime/<id>.
func regionFromARN(arn string) (string, error) {
	parts := strings.Split(arn, ":")
	if len(parts) < 6 || parts[0] != "arn" || parts[3] == "" {
		return "", fmt.Errorf("not an AgentCore runtime ARN: %q", arn)
	}
	return parts[3], nil
}
