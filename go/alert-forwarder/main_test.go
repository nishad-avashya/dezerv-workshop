package main

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type fakeInv struct {
	body string
	err  error
	sid  string
}

func (f *fakeInv) Invoke(_ context.Context, sid string, _ []byte) (io.ReadCloser, error) {
	f.sid = sid
	if f.err != nil {
		return nil, f.err
	}
	return io.NopCloser(strings.NewReader(f.body)), nil
}

func newServer(inv Invoker, out *bytes.Buffer) *Server {
	return &Server{inv: inv, timeout: time.Second, log: slog.New(slog.NewJSONHandler(io.Discard, nil)), out: out}
}

func post(s *Server, body string) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	s.handleAlert(rec, httptest.NewRequest(http.MethodPost, "/alert", strings.NewReader(body)))
	return rec
}

func TestFingerprintStableAndLongEnough(t *testing.T) {
	a := map[string]any{"alert": "X", "service": "payments-gw", "window_start": "t0"}
	if fingerprint(a) != fingerprint(a) {
		t.Fatal("not stable")
	}
	if len(fingerprint(a)) < 33 {
		t.Fatalf("session id too short: %d", len(fingerprint(a)))
	}
	b := map[string]any{"alert": "X", "service": "payments-gw", "window_start": "t1"}
	if fingerprint(a) == fingerprint(b) {
		t.Fatal("different incidents share a session")
	}
}

func TestHappyPathUnwrapsAnswerAndPrints(t *testing.T) {
	var out bytes.Buffer
	inv := &fakeInv{body: `{"session_id":"s","answer":"root cause v2.14.3"}`}
	rec := post(newServer(inv, &out), `{"alert":"PaymentsFailureRateHigh","service":"payments-gw","window_start":"t0"}`)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("code %d", rec.Code)
	}
	if !strings.Contains(out.String(), "root cause v2.14.3") {
		t.Fatalf("out: %q", out.String())
	}
}

func TestRepeatAlertReusesSession(t *testing.T) {
	var out bytes.Buffer
	inv := &fakeInv{body: "{}"}
	s := newServer(inv, &out)
	post(s, `{"alert":"A","service":"s","window_start":"t0"}`)
	first := inv.sid
	post(s, `{"alert":"A","service":"s","window_start":"t0"}`)
	if inv.sid != first {
		t.Fatalf("sessions differ: %s vs %s", first, inv.sid)
	}
}

func TestAgentDownIsFailSafe(t *testing.T) {
	var out bytes.Buffer
	rec := post(newServer(&fakeInv{err: errors.New("boom")}, &out), `{"alert":"A","service":"s"}`)
	if rec.Code != http.StatusBadGateway || !strings.Contains(rec.Body.String(), "escalated to human") {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
}

func TestBadJSONRejected(t *testing.T) {
	var out bytes.Buffer
	if rec := post(newServer(&fakeInv{}, &out), `{not json`); rec.Code != http.StatusBadRequest {
		t.Fatalf("code %d", rec.Code)
	}
}

func TestRegionFromARN(t *testing.T) {
	got, err := regionFromARN("arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/fx_payments_gw-EXAMPLE123")
	if err != nil || got != "us-west-2" {
		t.Fatalf("%q %v", got, err)
	}
	for _, bad := range []string{"", "not-an-arn", "arn:aws:bedrock-agentcore::1:runtime/x"} {
		if _, err := regionFromARN(bad); err == nil {
			t.Errorf("%q should be rejected", bad)
		}
	}
}
