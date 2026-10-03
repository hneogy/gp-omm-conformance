// Harness for gp-omm-conformance over Vallado's SGP4 C++ as CelesTrak publishes it (fundamentals-of-astrodynamics,
// software/cpp/SGP4/SGP4/SGP4.cpp and SGP4.h), unmodified: tle/2le through SGP4Funcs::twoline2rv(), the only reader the
// code has. Output: JSON records on stdout in the runner's --cmd protocol; exit 3 = format unsupported. The record is
// what the reader left in the elsetrec, with its units turned back into the TLE's (the mean motion to rev/day, the
// angles to degrees, the derivatives to rev/day^2 and rev/day^3); the catalog number is the reader's integer satnum.
// A set the reader throws on comes back through the runner's refusal channel with the exception's type and message as
// its reason (corpus D-144). The elsetrec's error flag is not a refusal (D-218): it is the propagation model's return
// code on the elements, left by the call to sgp4init() inside twoline2rv(), not the reader's verdict on the line, and
// for a malformed set it depends on what the structure held before the call. It is carried in the record as _error,
// with a note on standard error when it is non-zero. Each line 1 goes to the reader with whatever line follows it, so
// the reader, not the harness, answers for a line 1 with no line 2 after it (D-183).
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>
#include "common.h"
static bool first = true;
static const double XPDOTP = 1440.0 / (2.0 * 3.14159265358979323846), RAD2DEG = 180.0 / 3.14159265358979323846;
static void refusal(const std::string &reason, const std::string &field, const std::string &input) {   // the refusal channel (D-144)
    if (!first) printf(","); first = false;
    printf("{\"_refused\":"); jstr(reason); printf(",\"_field\":"); jstr(field); printf(",\"_input\":"); jstr(input); printf("}");
}
static std::string flag_reason(int code) {   // the codes as SGP4.cpp's comments on sgp4() give them
    static const char *words[] = { "", "mean elements, ecc >= 1.0 or ecc < -0.001 or a < 0.95 er", "mean motion less than 0.0", "pert elements, ecc < 0.0 or ecc > 1.0",
                                   "semi-latus rectum < 0.0", "epoch elements are sub-orbital", "satellite has decayed" };
    std::string r = "error flag " + std::to_string(code) + " after twoline2rv";
    if (code >= 1 && code <= 6) r += std::string(": ") + words[code];
    return r;
}
static int emit(const elsetrec &s, bool has_name, const std::string &name, size_t line_no) {
    int notes = 0;
    if (!first) printf(","); first = false;
    printf("{\"norad_cat_id\":%d,\"_catalog_field\":", s.satnum); jstr(std::string(s.satnumStr, strnlen(s.satnumStr, 5)));
    printf(",\"object_name\":"); if (has_name) jstr(name); else printf("null");
    printf(",\"_designator\":"); jstr(std::string(s.intldesg, strnlen(s.intldesg, 10)));
    char e[40]; printf(",\"epoch\":"); if (iso_epoch(s.jdsatepoch, s.jdsatepochF, e)) printf("\"%s\"", e); else { printf("null"); notes++; }
    const double v[9] = { s.no_kozai * XPDOTP, s.ecco, s.inclo * RAD2DEG, s.nodeo * RAD2DEG, s.argpo * RAD2DEG, s.mo * RAD2DEG,
                          s.bstar, s.ndot * XPDOTP * 1440.0, s.nddot * XPDOTP * 1440.0 * 1440.0 };
    const char *k[9] = { "mean_motion", "eccentricity", "inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot" };
    for (int i = 0; i < 9; i++) { printf(",\"%s\":", k[i]); jnum(v[i]); if (!std::isfinite(v[i])) notes++; }
    if (s.classification >= 0x20 && s.classification < 0x7f) { printf(",\"classification_type\":"); jstr(std::string(1, s.classification)); }
    printf(",\"ephemeris_type\":%d,\"element_set_no\":%ld,\"rev_at_epoch\":%ld,\"_error\":%d}", s.ephtype, s.elnum, s.revnum, s.error);
    if (notes) fprintf(stderr, "vallado: line %zu: %d value(s) the reader left non-finite, written as null\n", line_no, notes);
    return notes;
}
int main(int argc, char **argv) {
    std::string fmt = argc > 1 ? argv[1] : "";
    if (fmt != "tle" && fmt != "2le") return 3;   // the code reads TLE lines only: no OMM reader of any kind
    std::stringstream in; in << std::cin.rdbuf(); std::string text = in.str();
    std::vector<std::string> lines; { std::string l; std::istringstream ls(text); while (std::getline(ls, l)) { if (!l.empty() && l.back() == '\r') l.pop_back(); lines.push_back(l); } }
    int refused = 0; printf("[{\"_adapter\":{\"refusals\":true}}"); first = false;   // every set the reader throws on is reported
    for (size_t i = 0; i < lines.size(); i++) {
        if (lines[i].rfind("1 ", 0) != 0) continue;   // with whatever line follows, a line 2 or not: the reader answers (D-183)
        const std::string l2 = i + 1 < lines.size() ? lines[i + 1] : "";
        bool has_name = i > 0 && lines[i - 1].rfind("1 ", 0) != 0 && lines[i - 1].rfind("2 ", 0) != 0;
        std::string name = has_name ? lines[i - 1] : "";
        while (!name.empty() && name.back() == ' ') name.pop_back();   // the file pads names to 24 columns
        const std::string field = lines[i].size() >= 7 ? lines[i].substr(2, 5) : "";
        elsetrec s;
        try {
            read_set(lines[i], l2, s);
            if (s.error) fprintf(stderr, "vallado: line %zu: %s (carried as _error, not a refusal) | %s\n", i + 1, flag_reason(s.error).c_str(), lines[i].c_str());
            emit(s, has_name, name, i + 1);
        }
        catch (std::invalid_argument &e) { refused++; fprintf(stderr, "vallado: line %zu: std::invalid_argument: %s | %s\n", i + 1, e.what(), lines[i].c_str());
                                           refusal(std::string("std::invalid_argument: ") + e.what(), field, lines[i]); }
        catch (std::out_of_range &e) { refused++; fprintf(stderr, "vallado: line %zu: std::out_of_range: %s | %s\n", i + 1, e.what(), lines[i].c_str());
                                       refusal(std::string("std::out_of_range: ") + e.what(), field, lines[i]); }
        catch (std::exception &e) { refused++; fprintf(stderr, "vallado: line %zu: %s\n", i + 1, e.what());
                                    refusal(e.what(), field, lines[i]); }
    }
    printf("]\n");
    if (refused) fprintf(stderr, "%d set(s) refused\n", refused);
    return 0;
}
