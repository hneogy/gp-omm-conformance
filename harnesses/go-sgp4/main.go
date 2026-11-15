// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
//
// gpconf harness for akhenakh/sgp4 v1.0.4 (0.9.0 item b4, Go), one program for --cmd, --vectors-cmd and --write-cmd:
//
//	gpconf-go-sgp4 parse {fmt}   TLE and 2LE through ParseTLELines, OMM JSON through ParseOMMs, OMM CSV through ParseOMMsCSV
//	gpconf-go-sgp4 vectors       propagate through (*TLE).FindPosition, alpha5_decode through ParseAlpha5, alpha5_encode through FormatAlpha5;
//	                             two_digit_year, parse_epoch and parse_catalog_id unsupported
//	gpconf-go-sgp4 write         one record of the writer case through (*OMM).ToTLE and (*TLE).TLEString (D-445's gap)
//
// Values are the library's, as it holds them. UNTESTED where it was written (no Go toolchain there); the corpus's
// scratch CI builds and runs it (README.md).
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"

	sgp4 "github.com/akhenakh/sgp4"
)

type rec = map[string]any

func fromTLE(t *sgp4.TLE) rec {
	var name any
	if strings.TrimSpace(t.Name) != "" {
		name = strings.TrimSpace(t.Name)
	}
	return rec{
		"norad_cat_id": t.SatelliteNumber, "object_name": name,
		"epoch":       t.EpochTime().UTC().Format("2006-01-02T15:04:05.000000"),
		"mean_motion": t.MeanMotion, "eccentricity": t.Eccentricity, "inclination": t.Inclination,
		"ra_of_asc_node": t.RightAscension, "arg_of_pericenter": t.ArgOfPerigee, "mean_anomaly": t.MeanAnomaly,
		"bstar": t.Bstar, "mean_motion_dot": t.MeanMotionDot, "mean_motion_ddot": t.MeanMotionDot2,
		"classification_type": string(t.Classification), "element_set_no": t.ElementNumber,
		"rev_at_epoch": t.RevolutionNumber,
	}
}

func fromOMM(o sgp4.OMM) rec {
	r := rec{
		"norad_cat_id": o.NoradCatID, "epoch": o.EpochStr, // the library keeps the epoch as the file's text
		"mean_motion": o.MeanMotion, "eccentricity": o.Eccentricity, "inclination": o.Inclination,
		"ra_of_asc_node": o.RAOfAscNode, "arg_of_pericenter": o.ArgOfPericenter, "mean_anomaly": o.MeanAnomaly,
		"bstar": o.BStar, "mean_motion_dot": o.MeanMotionDot, "mean_motion_ddot": o.MeanMotionDDot,
		"ephemeris_type": o.EphemerisType, "element_set_no": o.ElementSetNo, "rev_at_epoch": o.RevAtEpoch,
	}
	for k, v := range map[string]string{"object_name": o.ObjectName, "object_id": o.ObjectID,
		"classification_type": o.ClassificationType, "center_name": o.CenterName, "ref_frame": o.RefFrame,
		"time_system": o.TimeSystem, "mean_element_theory": o.MeanElementTheory} {
		if v != "" {
			r[k] = v
		}
	}
	return r
}

func sets(text string) [][]string {
	lines := strings.Split(text, "\n")
	for i := range lines {
		lines[i] = strings.TrimSuffix(lines[i], "\r")
	}
	var out [][]string
	for i := 0; i < len(lines); i++ {
		if strings.HasPrefix(lines[i], "1 ") {
			l2 := "" // a line 1 with no line 2 after it goes to the library as it is, for the library to answer (D-439)
			if i+1 < len(lines) && strings.HasPrefix(lines[i+1], "2 ") {
				l2 = lines[i+1]
			}
			set := []string{lines[i], l2}
			if i > 0 && strings.TrimSpace(lines[i-1]) != "" && !strings.HasPrefix(lines[i-1], "2 ") {
				set = []string{lines[i-1], lines[i], l2}
			}
			out = append(out, set)
			if l2 != "" {
				i++
			}
		}
	}
	return out
}

func parse(format string, raw []byte) ([]rec, error) {
	out := []rec{{"_adapter": map[string]any{"refusals": true}}} // the harness reports the library's refusals (D-439)
	switch format {
	case "tle", "2le":
		for _, set := range sets(string(raw)) {
			l1 := set[len(set)-2]
			t, err := sgp4.ParseTLELines(append([]string(nil), set...))
			if err != nil { // the refusal channel, with the library's reason
				field := ""
				if len(l1) >= 7 {
					field = l1[2:7]
				}
				out = append(out, rec{"_refused": err.Error(), "_field": field, "_input": l1})
				continue
			}
			out = append(out, fromTLE(t))
		}
		return out, nil
	case "json":
		omms, err := sgp4.ParseOMMs(raw)
		if err != nil {
			return nil, err
		}
		for _, o := range omms {
			out = append(out, fromOMM(o))
		}
		return out, nil
	case "csv":
		omms, err := sgp4.ParseOMMsCSV(bytes.NewReader(raw))
		if err != nil {
			return nil, err
		}
		for _, o := range omms {
			out = append(out, fromOMM(o))
		}
		return out, nil
	}
	os.Exit(3) // XML and KVN: the library has no reader for them
	return nil, nil
}

// code: the library's errors as Vallado's SGP4 codes where one is meant, 99 for any other [inferred, untested]
func code(err error) int {
	var decayed *sgp4.SatelliteDecayedError
	if errors.As(err, &decayed) {
		return 6
	}
	var lim *sgp4.SGP4ModelLimitsError
	if errors.As(err, &lim) {
		switch lim.Reason {
		case sgp4.ReasonEccentricityTooLow, sgp4.ReasonEccentricityTooHigh:
			return 1
		case sgp4.ReasonPerturbedEccSqTooHigh:
			return 3
		case sgp4.ReasonSemiLatusRectumNegative, sgp4.ReasonBeta2Negative:
			return 4
		}
	}
	return 99
}

func propagate(input map[string]any) any {
	times, _ := input["tsince"].([]any)
	if len(times) == 0 {
		return map[string]any{"result": []any{}} // the probe: the op exists
	}
	if f, _ := input["fmt"].(string); f != "tle" && f != "2le" {
		return map[string]any{"unsupported": "the harness propagates TLE only"}
	}
	raw, _ := input["raw"].(string)
	s := sets(raw)
	if len(s) != 1 {
		return map[string]any{"error": "one element set expected"}
	}
	t, err := sgp4.ParseTLELines(s[0])
	if err != nil {
		return map[string]any{"error": err.Error()}
	}
	steps := []any{}
	for _, v := range times {
		ts, _ := v.(float64)
		eci, err := t.FindPosition(ts)
		if err != nil {
			steps = append(steps, map[string]any{"r": nil, "v": nil, "error": code(err)})
			continue
		}
		steps = append(steps, map[string]any{"r": []float64{eci.Position.X, eci.Position.Y, eci.Position.Z},
			"v": []float64{eci.Velocity.X, eci.Velocity.Y, eci.Velocity.Z}, "error": 0})
	}
	return map[string]any{"result": steps}
}

// num reads a record's value: the writer case sends the elements as decimal strings and the counters as integers.
func num(v any) (float64, error) {
	switch x := v.(type) {
	case nil:
		return 0, nil
	case float64:
		return x, nil
	case string:
		if strings.TrimSpace(x) == "" {
			return 0, nil
		}
		return strconv.ParseFloat(strings.TrimSpace(x), 64)
	}
	return 0, fmt.Errorf("not a number: %v", v)
}

func str(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

// write: one record (the runner's key names) -> the library's own OMM-to-TLE path, printed as two or three lines.
// Exit 1 with the library's reason when it refuses the record (a catalog number above 339999 among them).
func write(raw []byte) int {
	var r map[string]any
	if err := json.Unmarshal(raw, &r); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	o := sgp4.OMM{ObjectName: str(r["object_name"]), ObjectID: str(r["object_id"]), EpochStr: str(r["epoch"]),
		ClassificationType: str(r["classification_type"])}
	floats := []struct {
		key string
		dst *float64
	}{{"mean_motion", &o.MeanMotion}, {"eccentricity", &o.Eccentricity}, {"inclination", &o.Inclination},
		{"ra_of_asc_node", &o.RAOfAscNode}, {"arg_of_pericenter", &o.ArgOfPericenter}, {"mean_anomaly", &o.MeanAnomaly},
		{"bstar", &o.BStar}, {"mean_motion_dot", &o.MeanMotionDot}, {"mean_motion_ddot", &o.MeanMotionDDot}}
	for _, f := range floats {
		v, err := num(r[f.key])
		if err != nil {
			fmt.Fprintln(os.Stderr, f.key+": "+err.Error())
			return 1
		}
		*f.dst = v
	}
	ints := []struct {
		key string
		dst *int
	}{{"norad_cat_id", &o.NoradCatID}, {"element_set_no", &o.ElementSetNo}, {"rev_at_epoch", &o.RevAtEpoch},
		{"ephemeris_type", &o.EphemerisType}}
	for _, f := range ints {
		v, err := num(r[f.key])
		if err != nil {
			fmt.Fprintln(os.Stderr, f.key+": "+err.Error())
			return 1
		}
		*f.dst = int(v)
	}
	t, err := o.ToTLE()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	text, err := t.TLEString()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	fmt.Println(strings.TrimRight(text, "\n"))
	return 0
}

func main() {
	raw, err := io.ReadAll(os.Stdin)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	switch {
	case len(os.Args) > 1 && os.Args[1] == "parse":
		format := "tle"
		if len(os.Args) > 2 {
			format = os.Args[2]
		}
		recs, err := parse(format, raw)
		if err != nil { // the file refused as a whole, with the library's reason
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		_ = enc.Encode(recs)
	case len(os.Args) > 1 && os.Args[1] == "write":
		os.Exit(write(raw))
	case len(os.Args) > 1 && os.Args[1] == "vectors":
		var req struct {
			Op    string          `json:"op"`
			Input json.RawMessage `json:"input"` // a string, a number or an object, by op (D-439)
		}
		if err := json.Unmarshal(raw, &req); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		if req.Op == "propagate" {
			var in map[string]any
			if err := json.Unmarshal(req.Input, &in); err != nil {
				_ = enc.Encode(map[string]any{"error": err.Error()})
				return
			}
			_ = enc.Encode(propagate(in))
		} else if req.Op == "alpha5_decode" {
			var field string
			if err := json.Unmarshal(req.Input, &field); err != nil {
				_ = enc.Encode(map[string]any{"error": err.Error()})
				return
			}
			n, err := sgp4.ParseAlpha5(field)
			if err != nil { // the library refuses the field
				_ = enc.Encode(map[string]any{"error": err.Error()})
				return
			}
			_ = enc.Encode(map[string]any{"result": n})
		} else if req.Op == "alpha5_encode" {
			var n json.Number
			d := json.NewDecoder(bytes.NewReader(req.Input))
			d.UseNumber()
			if err := d.Decode(&n); err != nil {
				_ = enc.Encode(map[string]any{"error": err.Error()})
				return
			}
			i, err := n.Int64()
			if err != nil {
				_ = enc.Encode(map[string]any{"error": err.Error()})
				return
			}
			field, err := sgp4.FormatAlpha5(int(i))
			if err != nil { // the library refuses a number the field cannot carry
				_ = enc.Encode(map[string]any{"error": err.Error()})
				return
			}
			_ = enc.Encode(map[string]any{"result": field})
		} else {
			_ = enc.Encode(map[string]any{"unsupported": "akhenakh/sgp4 has no " + req.Op + " hook"})
		}
	default:
		fmt.Fprintln(os.Stderr, "usage: gpconf-go-sgp4 parse FMT | vectors | write")
		os.Exit(1)
	}
}
