// Harness for gp-omm-conformance over SatDump's own code (master f3d82ad; the release's registry parser is identical):
//   tle: satdump::parseTLEStream() (src-core/common/tracking/tle.cpp) builds the registry exactly as the application does,
//        then each registry entry's lines go through the bundled predict fork's predict_parse_tle(), as every tracking
//        consumer in the application does; both numbers are reported.
//   csv: satdump::ccsdsOmmToKepler() (src-core/db/kepler/kepler_utils.cpp, master only) per line, the reader behind the
//        default orbicentral "FORMAT=omm" feed, which is CelesTrak's CSV layout.
// Nothing in SatDump is modified; SatDump is GPL-3.0 and none of its code enters the corpus. Output: JSON records on
// stdout in the runner's --cmd protocol; exit 3 = format unsupported.
#include <cmath>
#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include "common/tracking/tle.h"
#include "db/kepler/kepler_handler.h"
extern "C" {
#include "libs/predict/predict.h"
}

static void jstr(const std::string &s) {
    putchar('"');
    for (unsigned char c : s) { if (c == '"' || c == '\\') { putchar('\\'); putchar(c); } else if (c < 0x20) printf("\\u%04x", c); else putchar(c); }
    putchar('"');
}
static std::string iso_from_unix(double t) {   // seconds since 1970 as a double -> ISO with microseconds
    long long us = llround(t * 1e6); time_t s = (time_t)(us / 1000000); long long f = us % 1000000; if (f < 0) { f += 1000000; s -= 1; }
    struct tm g; gmtime_r(&s, &g); char b[40];
    snprintf(b, sizeof b, "%04d-%02d-%02dT%02d:%02d:%02d.%06lld", g.tm_year + 1900, g.tm_mon + 1, g.tm_mday, g.tm_hour, g.tm_min, g.tm_sec, f);
    return b;
}
static std::string iso_from_tle_epoch(int yy, double day) {   // the year by the pivot the bundled predict fork applies (unsorted.c:104-107), computed here; the day fraction from the parsed double
    int year = yy < 57 ? 2000 + yy : 1900 + yy;
    int doy = (int)floor(day); long long us = llround((day - doy) * 86400e6); if (us >= 86400000000LL) { us -= 86400000000LL; doy++; }
    char b[40]; snprintf(b, sizeof b, "%04d-%03dT%02d:%02d:%02d.%06lld", year, doy, (int)(us / 3600000000LL), (int)((us % 3600000000LL) / 60000000LL), (int)((us % 60000000LL) / 1000000LL), us % 1000000LL);
    return b;
}

int main(int argc, char **argv) {
    std::string fmt = argc > 1 ? argv[1] : "";
    std::stringstream in; in << std::cin.rdbuf();
    bool first = true;
    printf("[");
    if (fmt == "tle" || fmt == "2le") {
        std::vector<satdump::TLE> registry;
        int n = satdump::parseTLEStream(in, registry);
        fprintf(stderr, "parseTLEStream: %d set(s) accepted, registry size %zu\n", n, registry.size());
        for (auto &t : registry) {
            predict_orbital_elements_t *m = predict_parse_tle(t.line1.c_str(), t.line2.c_str());
            if (!m) { fprintf(stderr, "predict_parse_tle returned NULL for %d\n", t.norad); continue; }
            if (!first) printf(","); first = false;
            printf("{\"norad_cat_id\":%d,\"_predict_satellite_number\":%d,\"object_name\":", t.norad, m->satellite_number); jstr(t.name);
            printf(",\"_designator\":"); jstr(std::string(m->designator, strnlen(m->designator, 9)));
            printf(",\"epoch\":\"%s\",\"mean_motion\":%.17g,\"eccentricity\":%.17g,\"inclination\":%.17g,\"ra_of_asc_node\":%.17g,\"arg_of_pericenter\":%.17g,\"mean_anomaly\":%.17g",
                   iso_from_tle_epoch(m->epoch_year, m->epoch_day).c_str(), m->mean_motion, m->eccentricity, m->inclination, m->right_ascension, m->argument_of_perigee, m->mean_anomaly);
            printf(",\"bstar\":%.17g,\"mean_motion_dot\":%.17g,\"mean_motion_ddot\":%.17g,\"element_set_no\":%ld,\"rev_at_epoch\":%d}",
                   m->bstar_drag_term, m->derivative_mean_motion, m->second_derivative_mean_motion, m->element_number, m->revolutions_at_epoch);
            predict_destroy_orbital_elements(m);
        }
    } else if (fmt == "csv") {
        std::string line; int accepted = 0, rejected = 0;
        while (std::getline(in, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            satdump::KeplerData kep;
            if (!satdump::ccsdsOmmToKepler(line, kep)) { rejected++; continue; }
            accepted++;
            if (!first) printf(","); first = false;
            printf("{\"norad_cat_id\":%d,\"object_name\":", kep.satellite_number); jstr(kep.name);
            printf(",\"_designator\":"); jstr(kep.designator);
            printf(",\"epoch\":\"%s\",\"mean_motion\":%.17g,\"eccentricity\":%.17g,\"inclination\":%.17g,\"ra_of_asc_node\":%.17g,\"arg_of_pericenter\":%.17g,\"mean_anomaly\":%.17g",
                   iso_from_unix(kep.epoch).c_str(), kep.mean_motion, kep.eccentricity, kep.inclination, kep.right_ascension, kep.argument_of_perigee, kep.mean_anomaly);
            printf(",\"bstar\":%.17g,\"mean_motion_dot\":%.17g,\"mean_motion_ddot\":%.17g,\"element_set_no\":%ld,\"rev_at_epoch\":%d}",
                   kep.bstar_drag_term, kep.derivative_mean_motion, kep.second_derivative_mean_motion, kep.element_number, kep.revolutions_at_epoch);
        }
        fprintf(stderr, "ccsdsOmmToKepler: %d line(s) accepted, %d rejected (header or malformed)\n", accepted, rejected);
    } else {
        return 3;
    }
    printf("]\n");
    return 0;
}
