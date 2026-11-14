package main

import (
	"regexp"
	"strings"
)

// Defence in depth: the Gateway's response interceptor masks PII too, but the tool masks its own output so it is safe
// even if it is ever called outside the Gateway. Same detectors as the Python interceptor for the fields this tool returns.
var (
	vpaRe  = regexp.MustCompile(`^([\w.\-]{2,})@([a-zA-Z]{2,})$`)
	acctRe = regexp.MustCompile(`(?i)^(acct|account)?\s*(\d{9,18})$`)
)

// MaskVPA turns "aarav42@okhdfc" into "***@okhdfc".
func MaskVPA(v string) string {
	if m := vpaRe.FindStringSubmatch(v); m != nil {
		return "***@" + m[2]
	}
	return "***"
}

// MaskAccount keeps the last four digits: "acct 246989508976" -> "acct XXXXXXXX8976".
func MaskAccount(a string) string {
	m := acctRe.FindStringSubmatch(strings.TrimSpace(a))
	if m == nil {
		return "XXXX"
	}
	digits := m[2]
	prefix := ""
	if m[1] != "" {
		prefix = m[1] + " "
	}
	return prefix + strings.Repeat("X", len(digits)-4) + digits[len(digits)-4:]
}
