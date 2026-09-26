// Harness for gp-omm-conformance over libsgp4 (dnwrnr/sgp4), unmodified: tle/2le through the Tle(name, line1, line2)
// constructor; csv through Tle::FromCsv() per data line after the header, as LoadCsvTleFile() does (master only).
// Output: JSON records on stdout in the runner's --cmd protocol; exit 3 = format unsupported.
#include <iostream>
#include <sstream>
#include <vector>
#include "common.h"
#include "TleException.h"
using namespace libsgp4;
static bool first = true;
static void emit(const Tle &t, bool has_name) {
    if (!first) printf(","); first = false;
    printf("{\"norad_cat_id\":%u,\"object_name\":", t.NoradNumber()); if (has_name) jstr(t.Name()); else printf("null");
    printf(",\"_designator\":"); jstr(t.IntDesignator());
    printf(",\"epoch\":\"%s\",\"mean_motion\":%.17g,\"eccentricity\":%.17g,\"inclination\":%.17g,\"ra_of_asc_node\":%.17g,\"arg_of_pericenter\":%.17g,\"mean_anomaly\":%.17g",
           iso(t.Epoch()).c_str(), t.MeanMotion(), t.Eccentricity(), t.Inclination(true), t.RightAscendingNode(true), t.ArgumentPerigee(true), t.MeanAnomaly(true));
    printf(",\"bstar\":%.17g,\"mean_motion_dot\":%.17g,\"mean_motion_ddot\":%.17g,\"rev_at_epoch\":%u}", t.BStar(), t.MeanMotionDt2(), t.MeanMotionDdt6(), t.OrbitNumber());
}
int main(int argc, char **argv) {
    std::string fmt = argc > 1 ? argv[1] : "";
    std::stringstream in; in << std::cin.rdbuf(); std::string text = in.str();
    std::vector<std::string> lines; { std::string l; std::istringstream ls(text); while (std::getline(ls, l)) { if (!l.empty() && l.back() == '\r') l.pop_back(); lines.push_back(l); } }
    int refused = 0; printf("[");
    if (fmt == "tle" || fmt == "2le") {
        for (size_t i = 0; i + 1 < lines.size(); i++) {
            if (lines[i].rfind("1 ", 0) != 0 || lines[i + 1].rfind("2 ", 0) != 0) continue;
            bool has_name = i > 0 && lines[i - 1].rfind("1 ", 0) != 0 && lines[i - 1].rfind("2 ", 0) != 0;
            std::string name = has_name ? lines[i - 1] : "";
            while (!name.empty() && name.back() == ' ') name.pop_back();   // the file pads names to 24 columns; the library stores the name as given
            try { Tle t(name, lines[i], lines[i + 1]); emit(t, has_name); }
            catch (TleException &e) { refused++; fprintf(stderr, "libsgp4 refused line %zu: TleException: %s | %s\n", i + 1, e.what(), lines[i].c_str()); }
            catch (std::exception &e) { refused++; fprintf(stderr, "libsgp4 refused line %zu: %s\n", i + 1, e.what()); }
        }
    } else if (fmt == "csv") {
#ifdef HAVE_CSV
        for (size_t i = 1; i < lines.size(); i++) {   // the library's loader skips the header line
            if (lines[i].empty()) continue;
            try { Tle t = Tle::FromCsv(lines[i]); emit(t, true); }
            catch (TleException &e) { refused++; fprintf(stderr, "libsgp4 refused csv line %zu: TleException: %s\n", i + 1, e.what()); }
            catch (std::exception &e) { refused++; fprintf(stderr, "libsgp4 refused csv line %zu: %s\n", i + 1, e.what()); }
        }
#else
        return 3;
#endif
    } else return 3;
    printf("]\n");
    if (refused) fprintf(stderr, "%d record(s) refused\n", refused);
    return 0;
}
