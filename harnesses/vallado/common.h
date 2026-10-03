// Shared by the harness and the vectors helper: JSON output helpers, the call into the reference reader, the calendar
// form of the epoch the reader stored, and a checksum routine of my own for the synthetic lines the vectors helper builds.
#pragma once
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include "SGP4.h"
static inline void jstr(const std::string &s) { putchar('"'); for (unsigned char c : s) { if (c == '"' || c == '\\') { putchar('\\'); putchar(c); } else if (c < 0x20) printf("\\u%04x", c); else putchar(c); } putchar('"'); }
static inline void jnum(double v) { if (std::isfinite(v)) printf("%.17g", v); else printf("null"); }   // JSON has no NaN or infinity: null, and the harness says so on stderr
// The reader as its callers reach it: both lines in 130-character buffers, which it writes into; an elsetrec that
// starts zeroed, so a field the reader does not assign comes back as 0; and the arguments python-sgp4's wrapper
// passes (' ', ' ', 'i', wgs72), with which the function asks nothing of the terminal. The lines go in as the file
// carries them, checksum digit included, as a caller reading the file with fgets() would hand them over.
static inline void read_set(const std::string &l1, const std::string &l2, elsetrec &s) {
    char a[130], b[130]; memset(a, 0, sizeof a); memset(b, 0, sizeof b);
    strncpy(a, l1.c_str(), 129); strncpy(b, l2.c_str(), 129);
    memset(&s, 0, sizeof s);
    double startmfe = 0, stopmfe = 0, deltamin = 0;
    SGP4Funcs::twoline2rv(a, b, ' ', ' ', 'i', wgs72, startmfe, stopmfe, deltamin, s);
}
// The epoch the reader stored, jdsatepoch + jdsatepochF, as a calendar instant to the microsecond. The conversion is
// this file's own integer arithmetic, so that what is compared is the reader's stored epoch and nothing else.
static inline bool iso_epoch(double jd, double jdfrac, char out[40], int *year_out = nullptr) {
    if (!std::isfinite(jd) || !std::isfinite(jdfrac) || std::fabs(jd) > 1e8 || std::fabs(jdfrac) > 1e6) return false;
    double days = jd - 2440587.5;                      // days from 1970-01-01T00:00
    double whole = std::floor(days);
    long long z = (long long)whole;
    long long us = std::llround(((days - whole) + jdfrac) * 86400e6);
    const long long DAY = 86400000000LL;
    z += us / DAY; us %= DAY; if (us < 0) { us += DAY; z -= 1; }
    z += 719468;                                       // civil date from a day count
    long long era = (z >= 0 ? z : z - 146096) / 146097;
    long long doe = z - era * 146097, yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    long long y = yoe + era * 400, doy = doe - (365 * yoe + yoe / 4 - yoe / 100), mp = (5 * doy + 2) / 153;
    long long d = doy - (153 * mp + 2) / 5 + 1, m = mp < 10 ? mp + 3 : mp - 9; if (m <= 2) y += 1;
    snprintf(out, 40, "%04lld-%02lld-%02lldT%02lld:%02lld:%02lld.%06lld", y, m, d, us / 3600000000LL, (us / 60000000LL) % 60, (us / 1000000LL) % 60, us % 1000000LL);
    if (year_out) *year_out = (int)y;
    return true;
}
static inline std::string with_checksum(std::string line) { int s = 0; for (size_t i = 0; i < 68 && i < line.size(); i++) { char c = line[i]; if (c >= '0' && c <= '9') s += c - '0'; else if (c == '-') s += 1; } line.resize(68, ' '); line += char('0' + s % 10); return line; }
