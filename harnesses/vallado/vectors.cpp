// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// Vector hooks for the corpus, each through the reference reader itself (nothing decoded by this program):
//   alpha5_decode(field): a valid line pair with the field in columns 3-7 of both lines -> the reader's satnum
//   two_digit_year(yy):   the same pair with the epoch year set -> the year of the epoch the reader stored
//   alpha5_encode:        the code has no encoder and no TLE writer: answered unsupported, so the item skips (D-205)
//   parse_epoch, parse_catalog_id: the code reads TLE lines only, no OMM of any form: answered unsupported
//   propagate({raw, fmt, tsince}): the set's two lines read as the harness reads them (WGS-72, opsmode 'i', a zeroed
//                         elsetrec), then SGP4Funcs::sgp4 from the initialised set at each time: TEME r (km), v (km/s)
//                         and the code per step; the probe with no times answers []; OMM answered unsupported (D-416)
// Input: JSON {"op":..,"input":..} on stdin; output {"result":..}, {"error":..} or {"unsupported":..}.
#include <iostream>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <vector>
#include "common.h"
static const std::string L1 = "1 25544U 98067A   26263.52959654  .00008422  00000+0  15975-3 0  9999";
static const std::string L2 = "2 25544  51.6308 188.2246 0004825 162.2847 197.8311 15.49196792 58653";
static std::string field(const std::string &json, const std::string &key) {   // minimal: the runner sends {"op": "...", "input": "..."} with string inputs
    std::smatch m; std::regex re("\"" + key + "\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
    if (std::regex_search(json, m, re)) { std::string v = m[1]; std::string out; for (size_t i = 0; i < v.size(); i++) { if (v[i] == '\\' && i + 1 < v.size()) { out += v[++i]; } else out += v[i]; } return out; }
    return "";
}
static std::string unescape(const std::string &v) {   // a JSON string's escapes: \n, \r, \t, \", \\, \/ and \uXXXX (ASCII)
    std::string out;
    for (size_t i = 0; i < v.size(); i++) {
        if (v[i] != '\\' || i + 1 >= v.size()) { out += v[i]; continue; }
        char c = v[++i];
        if (c == 'n') out += '\n'; else if (c == 'r') out += '\r'; else if (c == 't') out += '\t';
        else if (c == 'u' && i + 4 < v.size()) { out += char(std::stoi(v.substr(i + 1, 4), nullptr, 16) & 0x7f); i += 4; }
        else out += c;
    }
    return out;
}
static bool propagate(const std::string &json) {   // the propagate op; false when the input is not one it reads
    std::smatch m;
    std::regex raw_re("\"raw\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\""), fmt_re("\"fmt\"\\s*:\\s*\"([a-z0-9.]*)\""), ts_re("\"tsince\"\\s*:\\s*\\[([^\\]]*)\\]");
    std::vector<double> ts;
    if (std::regex_search(json, m, ts_re)) {
        std::stringstream list(m[1].str()); std::string x;
        while (std::getline(list, x, ',')) if (x.find_first_not_of(" \t\r\n") != std::string::npos) ts.push_back(std::stod(x));
    }
    if (ts.empty()) { printf("{\"result\":[]}"); return true; }   // the probe: an op that is there answers []
    std::string fmt = std::regex_search(json, m, fmt_re) ? m[1].str() : "";
    if (fmt != "tle" && fmt != "2le") { printf("{\"unsupported\":\"the code reads TLE lines only: no OMM reader\"}"); return true; }
    std::string raw = std::regex_search(json, m, raw_re) ? unescape(m[1].str()) : "", l, l1, l2;
    std::stringstream lines(raw);
    while (std::getline(lines, l)) {
        if (!l.empty() && l.back() == '\r') l.pop_back();
        if (l.rfind("1 ", 0) == 0 && l1.empty()) l1 = l; else if (l.rfind("2 ", 0) == 0 && l2.empty()) l2 = l;
    }
    if (l1.empty() || l2.empty()) { printf("{\"error\":\"one element set expected: a line 1 and a line 2\"}"); return false; }
    elsetrec s; read_set(l1, l2, s);
    printf("{\"result\":[");
    for (size_t k = 0; k < ts.size(); k++) {
        double r[3], v[3]; elsetrec c = s;   // each step from the initialised set, as the verification driver does
        bool ok = SGP4Funcs::sgp4(c, ts[k], r, v);
        int code = ok ? c.error : (c.error ? c.error : -1);
        if (k) putchar(',');
        if (code == 0) {
            printf("{\"r\":["); jnum(r[0]); putchar(','); jnum(r[1]); putchar(','); jnum(r[2]);
            printf("],\"v\":["); jnum(v[0]); putchar(','); jnum(v[1]); putchar(','); jnum(v[2]); printf("],\"error\":0}");
        } else printf("{\"r\":null,\"v\":null,\"error\":%d}", code);
    }
    printf("]}");
    return true;
}
int main() {
    std::stringstream in; in << std::cin.rdbuf(); std::string json = in.str();
    std::string op = field(json, "op"), input = field(json, "input");
    try {
        if (op == "alpha5_decode") {
            if (input.size() != 5) { printf("{\"error\":\"field must be five characters\"}"); return 1; }
            std::string a = with_checksum(L1.substr(0, 2) + input + L1.substr(7)), b = with_checksum(L2.substr(0, 2) + input + L2.substr(7));
            elsetrec s; read_set(a, b, s); printf("{\"result\":%d}", s.satnum); return 0;
        }
        if (op == "two_digit_year") {
            if (input.size() != 2) { printf("{\"error\":\"two digits expected\"}"); return 1; }
            std::string a = with_checksum(L1.substr(0, 18) + input + L1.substr(20));
            elsetrec s; read_set(a, L2, s); char e[40]; int year = 0;
            if (!iso_epoch(s.jdsatepoch, s.jdsatepochF, e, &year)) { printf("{\"error\":\"the reader stored no finite epoch\"}"); return 1; }
            printf("{\"result\":%d}", year); return 0;
        }
        if (op == "propagate") return propagate(json) ? 0 : 1;
        if (op == "alpha5_encode") { printf("{\"unsupported\":\"the code has no alpha5_encode: no TLE writer or Alpha-5 encoder\"}"); return 0; }
        if (op == "parse_epoch" || op == "parse_catalog_id") { printf("{\"unsupported\":\"the code reads TLE lines only: no OMM reader, so no CCSDS epoch or NORAD_CAT_ID parser\"}"); return 0; }
        printf("{\"error\":\"the code has no %s\"}", op.c_str()); return 1;
    } catch (std::invalid_argument &e) { printf("{\"error\":\"std::invalid_argument: %s\"}", e.what()); return 1; }
      catch (std::out_of_range &e) { printf("{\"error\":\"std::out_of_range: %s\"}", e.what()); return 1; }
      catch (std::exception &e) { printf("{\"error\":\"%s\"}", e.what()); return 1; }
}
