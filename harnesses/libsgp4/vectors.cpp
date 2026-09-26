// Vector hooks for the corpus, each through the library's own entry points (nothing decoded by this program):
//   alpha5_decode(field): a valid line pair with the field in columns 3-7 of both lines -> Tle::NoradNumber()
//   two_digit_year(yy):   the same pair with the epoch year set -> Tle::Epoch().Year()
//   parse_epoch(text):    a valid CSV data line with EPOCH replaced -> Tle::FromCsv().Epoch()      (master only)
//   parse_catalog_id(t):  a valid CSV data line with NORAD_CAT_ID replaced -> Tle::FromCsv().NoradNumber() (master only)
//   alpha5_encode:        the library has no encoder or writer
// Input: JSON {"op":..,"input":..} on stdin; output {"result":..} or {"error":..}.
#include <iostream>
#include <regex>
#include <sstream>
#include "common.h"
#include "TleException.h"
using namespace libsgp4;
static const std::string L1 = "1 25544U 98067A   26263.52959654  .00008422  00000+0  15975-3 0  9999";
static const std::string L2 = "2 25544  51.6308 188.2246 0004825 162.2847 197.8311 15.49196792 58653";
static const std::string CSV = "ISS (ZARYA),1998-067A,2026-09-20T12:42:37.141056,15.49196792,0.0004825,51.6308,188.2246,162.2847,197.8311,0,U,25544,999,58653,0.00015975,0.00008422,0";
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
            Tle t("X", a, b); printf("{\"result\":%u}", t.NoradNumber()); return 0;
        }
        if (op == "two_digit_year") {
            if (input.size() != 2) { printf("{\"error\":\"two digits expected\"}"); return 1; }
            std::string a = with_checksum(L1.substr(0, 18) + input + L1.substr(20));
            Tle t("X", a, L2); printf("{\"result\":%d}", t.Epoch().Year()); return 0;
        }
#ifdef HAVE_CSV
        if (op == "parse_epoch") {
            std::string row = CSV; size_t p = row.find("2026-09-20T12:42:37.141056"); row.replace(p, 26, input);
            Tle t = Tle::FromCsv(row); printf("{\"result\":\"%s\"}", iso(t.Epoch()).c_str()); return 0;
        }
        if (op == "parse_catalog_id") {
            std::string row = CSV; size_t p = row.find(",25544,"); row.replace(p, 7, "," + input + ",");
            Tle t = Tle::FromCsv(row); printf("{\"result\":%u}", t.NoradNumber()); return 0;
        }
#endif
        printf("{\"error\":\"the library has no %s\"}", op.c_str()); return 1;
    } catch (TleException &e) { printf("{\"error\":\"TleException: %s\"}", e.what()); return 1; }
      catch (std::exception &e) { printf("{\"error\":\"%s\"}", e.what()); return 1; }
}
