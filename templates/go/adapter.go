// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
//
// A gpconf adapter template for a parser in Go, run by command:
//
//	go build -o adapter templates/go/adapter.go
//	python3 -m gpconf run --cmd "./adapter {fmt}"
//
// gpconf writes one file to standard input and reads a JSON array of records from standard output (docs/ADAPTERS.md,
// "The command protocol"). Replace toyParse with a call to your library; keep the rest. The toy parser reads TLE only
// and is here so the template runs as it stands; it is not a parser to use. Same toy as templates/python/adapter.py.
// A panic exits 2, which gpconf reads as an answer that failed; return errors and exit 1 instead.
// UNTESTED: written without a Go toolchain on the machine that wrote it; templates/README.md says which were run.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
	"time"
)

const alpha5Letters = "ABCDEFGHJKLMNPQRSTUVWXYZ" // I and O are skipped

func digits(s string) bool {
	if s == "" {
		return false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}

// cols: columns a..b of a line, by characters, clipped to its length.
func cols(l []rune, a, b int) string {
	if a > len(l) {
		a = len(l)
	}
	if b > len(l) {
		b = len(l)
	}
	return string(l[a:b])
}

func trim(s string) string { return strings.Trim(s, " \t") }

func alpha5(f string) (int, error) {
	r := []rune(f)
	if len(r) != 5 || !digits(string(r[1:])) {
		return 0, fmt.Errorf("invalid catalog field %q", f)
	}
	if r[0] >= '0' && r[0] <= '9' {
		return strconv.Atoi(f)
	}
	k := strings.IndexRune(alpha5Letters, r[0])
	if k < 0 {
		return 0, fmt.Errorf("invalid catalog field %q", f)
	}
	n, _ := strconv.Atoi(string(r[1:]))
	return (k+10)*10000 + n, nil
}

func checksum(l []rune) int {
	s := 0
	for i := 0; i < 68 && i < len(l); i++ {
		if l[i] >= '0' && l[i] <= '9' {
			s += int(l[i] - '0')
		} else if l[i] == '-' {
			s++
		}
	}
	return s % 10
}

// exponent: " 12345-3" -> "0.12345e-3", compared exactly as text.
func exponent(field string) string {
	f := trim(field)
	sign := ""
	if strings.HasPrefix(f, "-") {
		sign = "-"
	}
	r := []rune(strings.TrimLeft(f, "+-"))
	return sign + "0." + cols(r, 0, 5) + "e" + cols(r, 5, len(r))
}

// epochText: "DDD.DDDDDDDD" -> "YYYY-MM-DDThh:mm:ss.ffffff"; eight decimals of a day are whole microseconds.
func epochText(year int, day string) (string, error) {
	d := []rune(day)
	if len(d) != 12 || d[3] != '.' || !digits(cols(d, 0, 3)+cols(d, 4, 12)) {
		return "", fmt.Errorf("epoch day %q is not DDD.DDDDDDDD", day)
	}
	doy, _ := strconv.ParseInt(cols(d, 0, 3), 10, 64)
	frac, _ := strconv.ParseInt(cols(d, 4, 12), 10, 64)
	us := (doy-1)*86_400_000_000 + frac*864
	t := time.Date(year, 1, 1, 0, 0, 0, 0, time.UTC).Add(time.Duration(us) * time.Microsecond)
	return t.Format("2006-01-02T15:04:05.000000"), nil
}

type rec = map[string]any

func record(name *string, l1, l2 []rune) (rec, error) {
	if len(l1) != 69 || len(l2) != 69 {
		return nil, fmt.Errorf("line lengths %d/%d, not 69", len(l1), len(l2))
	}
	if int(l1[68]-'0') != checksum(l1) || int(l2[68]-'0') != checksum(l2) {
		return nil, errors.New("checksum")
	}
	if cols(l1, 2, 7) != cols(l2, 2, 7) {
		return nil, errors.New("line 2's catalog number is not line 1's")
	}
	if !digits(cols(l1, 18, 20)) {
		return nil, fmt.Errorf("epoch year %q is not two digits", cols(l1, 18, 20))
	}
	yy, _ := strconv.Atoi(cols(l1, 18, 20))
	year := 2000 + yy
	if yy >= 57 {
		year = 1900 + yy
	}
	id, err := alpha5(cols(l1, 2, 7))
	if err != nil {
		return nil, err
	}
	ep, err := epochText(year, cols(l1, 20, 32))
	if err != nil {
		return nil, err
	}
	return rec{
		"norad_cat_id": id, "object_name": name, "epoch": ep,
		"mean_motion": trim(cols(l2, 52, 63)), "eccentricity": "0." + cols(l2, 26, 33),
		"inclination": trim(cols(l2, 8, 16)), "ra_of_asc_node": trim(cols(l2, 17, 25)),
		"arg_of_pericenter": trim(cols(l2, 34, 42)), "mean_anomaly": trim(cols(l2, 43, 51)),
		"bstar": exponent(cols(l1, 53, 61)), "mean_motion_dot": strings.ReplaceAll(cols(l1, 33, 43), " ", ""),
		"mean_motion_ddot": exponent(cols(l1, 44, 52)),
	}, nil
}

// toyParse: name line optional, two element lines, fixed columns, the checksum checked.
func toyParse(text string) []rec {
	raw := strings.Split(text, "\n")
	lines := make([][]rune, len(raw))
	for i, l := range raw {
		lines[i] = []rune(strings.TrimSuffix(l, "\r"))
	}
	out := []rec{}
	for i := 0; i < len(lines); i++ {
		l1 := lines[i]
		s1 := string(l1)
		if strings.HasPrefix(s1, "1 ") && i+1 < len(lines) && strings.HasPrefix(string(lines[i+1]), "2 ") {
			var name *string
			if i > 0 {
				prev := string(lines[i-1])
				if trim(prev) != "" && !strings.HasPrefix(prev, "2 ") {
					n := trim(prev)
					name = &n
				}
			}
			r, err := record(name, l1, lines[i+1])
			if err != nil { // the refusal channel: the record was dropped, and why
				r = rec{"_refused": "error: " + err.Error(), "_field": cols(l1, 2, 7), "_input": cols(l1, 0, 80)}
			}
			out = append(out, r)
			i++
		} else if strings.HasPrefix(s1, "1 ") || strings.HasPrefix(s1, "2 ") {
			out = append(out, rec{"_refused": "an element line that pairs with nothing", "_field": cols(l1, 2, 7), "_input": cols(l1, 0, 80)})
		}
	}
	return out
}

func main() {
	format := "tle"
	if len(os.Args) > 1 {
		format = os.Args[1]
	}
	if format != "tle" && format != "2le" {
		os.Exit(3) // exit 3: format not supported; the file is reported as a skip
	}
	b, err := io.ReadAll(os.Stdin)
	if err != nil {
		fmt.Fprintln(os.Stderr, "adapter:", err)
		os.Exit(1)
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(toyParse(strings.ToValidUTF8(string(b), "�"))); err != nil {
		fmt.Fprintln(os.Stderr, "adapter:", err)
		os.Exit(1)
	}
}
