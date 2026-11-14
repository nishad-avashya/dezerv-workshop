// mandates-go: Lab B's Go tool. A Lambda on provided.al2023 (arm64) that the AgentCore Gateway calls as an MCP tool.
//
// Gateway contract: the tool name arrives in the Lambda client context (Custom["bedrockAgentCoreToolName"] = "<target>___<tool>")
// and the tool arguments arrive as the event JSON; the handler returns JSON.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-lambda-go/lambdacontext"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type Mandate struct {
	MandateID   string `json:"mandate_id"`
	UserID      string `json:"user_id"`
	State       string `json:"state"` // ACTIVE | PAUSED | REVOKED | EXPIRED | PENDING_BANK
	VPA         string `json:"vpa"`
	BankAccount string `json:"bank_account"`
	MaxAmount   int    `json:"max_amount"`
	Bank        string `json:"bank"`
	Frequency   string `json:"frequency"`
	UpdatedAt   string `json:"updated_at"`
}

type Store interface {
	Mandates(ctx context.Context) ([]Mandate, error)
}

type s3Store struct {
	bucket string
	cache  []Mandate
}

func (s *s3Store) Mandates(ctx context.Context) ([]Mandate, error) {
	if s.cache != nil {
		return s.cache, nil
	}
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		return nil, err
	}
	out, err := s3.NewFromConfig(cfg).GetObject(ctx, &s3.GetObjectInput{Bucket: &s.bucket, Key: strPtr("mongo/mandates.json")})
	if err != nil {
		return nil, err
	}
	defer out.Body.Close()
	b, err := io.ReadAll(out.Body)
	if err != nil {
		return nil, err
	}
	return s.cache, json.Unmarshal(b, &s.cache)
}

func strPtr(s string) *string { return &s }

func envelope(source, query string, data any) map[string]any {
	return map[string]any{"source": source, "query": query, "as_of": time.Now().In(time.FixedZone("IST", 19800)).Format(time.RFC3339), "data": data}
}

func toolErr(code, msg string) map[string]any {
	return map[string]any{"error": code, "message": msg}
}

// getMandateStatus is read-only and masks VPA and account number in the tool itself.
func getMandateStatus(ctx context.Context, st Store, args map[string]any) map[string]any {
	uid, _ := args["user_id"].(string)
	if uid == "" {
		return toolErr("BAD_REQUEST", "user_id is required")
	}
	all, err := st.Mandates(ctx)
	if err != nil {
		return toolErr("TOOL_ERROR", err.Error())
	}
	for _, m := range all {
		if m.UserID == uid {
			m.VPA, m.BankAccount = MaskVPA(m.VPA), MaskAccount(m.BankAccount)
			return envelope("mandates:s3(upi-autopay-mock)", "user_id="+uid, m)
		}
	}
	return toolErr("NOT_FOUND", "no mandate for "+uid)
}

// revokeMandate is a DECOY mutation: it never changes anything. Policy must forbid it; if it ever runs it shouts.
func revokeMandate(args map[string]any) map[string]any {
	fmt.Fprintf(os.Stderr, `{"level":"CRITICAL","marker":"WOULD_EXECUTE","tool":"mandates___revoke_mandate","args":%q}`+"\n", fmt.Sprint(args))
	return envelope("mandates-decoy", "revoke_mandate", map[string]any{"executed": false, "note": "no-op decoy"})
}

// dispatch routes by tool name. name may be "mandates___get_mandate_status" or the bare tool name.
func dispatch(ctx context.Context, st Store, name string, args map[string]any) map[string]any {
	if i := strings.LastIndex(name, "___"); i >= 0 {
		name = name[i+3:]
	}
	switch name {
	case "get_mandate_status":
		return getMandateStatus(ctx, st, args)
	case "revoke_mandate":
		return revokeMandate(args)
	}
	return toolErr("UNKNOWN_TOOL", "unknown tool "+name)
}

func handler(ctx context.Context, args map[string]any) (map[string]any, error) {
	name := ""
	if lc, ok := lambdacontext.FromContext(ctx); ok {
		name = lc.ClientContext.Custom["bedrockAgentCoreToolName"]
	}
	if name == "" { // fallback for local invocation: tool name inside the payload
		name, _ = args["_tool"].(string)
	}
	return dispatch(ctx, &s3Store{bucket: os.Getenv("DATA_BUCKET")}, name, args), nil
}

func main() { lambda.Start(handler) }
