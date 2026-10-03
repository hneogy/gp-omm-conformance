// Vector hooks for the corpus, each through the reference reader itself (nothing decoded by this program):
//   alpha5_decode(field): a valid line pair with the field in columns 3-7 of both lines -> the reader's satnum
//   two_digit_year(yy):   the same pair with the epoch year set -> the year of the epoch the reader stored
//   alpha5_encode:        the code has no encoder and no TLE writer: answered unsupported, so the item skips (D-205)
//   parse_epoch, parse_catalog_id: the code reads TLE lines only, no OMM of any form: answered unsupported
// Input: JSON {"op":..,"input":..} on stdin; output {"result":..}, {"error":..} or {"unsupported":..}.
#include <iostream>
#include <regex>
#include <sstream>
#include <stdexcept>
#include "common.h"
static const std::string L1 = "1 25544U 98067A   26263.52959654  .00008422  00000+0  15975-3 0  9999";
static const std::string L2 = "2 25544  51.6308 188.2246 0004825 162.2847 197.8311 15.49196792 58653";
static std::string field(const std::string &json, const std::string &key) {   // minimal: the runner sends {"op": "...", "input": "..."} with string inputs
    std::smatch m; std::regex re("\"" + key + "\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
    if (std::regex_search(json, m, re)) { std::string v = m[1]; std::string out; for (size_t i = 0; i < v.size(); i++) { if (v[i] == '\\' && i + 1 < v.size()) { out += v[++i]; } else out += v[i]; } return out; }
    return "";
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
        if (op == "alpha5_encode") { printf("{\"unsupported\":\"the code has no alpha5_encode: no TLE writer or Alpha-5 encoder\"}"); return 0; }
        if (op == "parse_epoch" || op == "parse_catalog_id") { printf("{\"unsupported\":\"the code reads TLE lines only: no OMM reader, so no CCSDS epoch or NORAD_CAT_ID parser\"}"); return 0; }
        printf("{\"error\":\"the code has no %s\"}", op.c_str()); return 1;
    } catch (std::invalid_argument &e) { printf("{\"error\":\"std::invalid_argument: %s\"}", e.what()); return 1; }
      catch (std::out_of_range &e) { printf("{\"error\":\"std::out_of_range: %s\"}", e.what()); return 1; }
      catch (std::exception &e) { printf("{\"error\":\"%s\"}", e.what()); return 1; }
}
