package main

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
)

type fake []Mandate

func (f fake) Mandates(context.Context) ([]Mandate, error) { return f, nil }

var sample = fake{{MandateID: "MND-1", UserID: "U-1042", State: "ACTIVE", VPA: "aarav42@okhdfc", BankAccount: "acct 246989508976", MaxAmount: 10000}}

func TestMaskVPA(t *testing.T) {
	if got := MaskVPA("aarav42@okhdfc"); got != "***@okhdfc" {
		t.Fatalf("got %q", got)
	}
	if got := MaskVPA("not a vpa"); got != "***" {
		t.Fatalf("got %q", got)
	}
}

func TestMaskAccount(t *testing.T) {
	cases := map[string]string{"acct 246989508976": "acct XXXXXXXX8976", "246989508976": "XXXXXXXX8976", "junk": "XXXX"}
	for in, want := range cases {
		if got := MaskAccount(in); got != want {
			t.Errorf("MaskAccount(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestGetMandateStatusMasksAndReturnsState(t *testing.T) {
	out := getMandateStatus(context.Background(), sample, map[string]any{"user_id": "U-1042"})
	b, _ := json.Marshal(out)
	s := string(b)
	if !strings.Contains(s, `"state":"ACTIVE"`) {
		t.Fatalf("state missing: %s", s)
	}
	if strings.Contains(s, "aarav42") || strings.Contains(s, "246989508976") {
		t.Fatalf("PII leaked: %s", s)
	}
}

func TestNotFoundAndBadRequest(t *testing.T) {
	if out := getMandateStatus(context.Background(), sample, map[string]any{"user_id": "U-9"}); out["error"] != "NOT_FOUND" {
		t.Fatalf("%v", out)
	}
	if out := getMandateStatus(context.Background(), sample, map[string]any{}); out["error"] != "BAD_REQUEST" {
		t.Fatalf("%v", out)
	}
}

func TestDispatchStripsTargetPrefixAndRejectsUnknown(t *testing.T) {
	ctx := context.Background()
	if out := dispatch(ctx, sample, "mandates___get_mandate_status", map[string]any{"user_id": "U-1042"}); out["error"] != nil {
		t.Fatalf("%v", out)
	}
	if out := dispatch(ctx, sample, "get_mandate_status", map[string]any{"user_id": "U-1042"}); out["error"] != nil {
		t.Fatalf("%v", out)
	}
	if out := dispatch(ctx, sample, "mandates___nope", nil); out["error"] != "UNKNOWN_TOOL" {
		t.Fatalf("%v", out)
	}
}

func TestDecoyNeverExecutes(t *testing.T) {
	out := dispatch(context.Background(), sample, "mandates___revoke_mandate", map[string]any{"user_id": "U-1042"})
	b, _ := json.Marshal(out)
	if !strings.Contains(string(b), `"executed":false`) {
		t.Fatalf("%s", b)
	}
}
