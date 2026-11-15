// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// The corpus's own reference vectors for the propagation tier's TLE/OMM twins (lane C's question 3, ruled yes on
// 2026-11-01): each TLE set given on stdin, two lines at a time, propagated by Vallado's SGP4 (SGP4.cpp, as the recipe's
// pin carries it; WGS-72, opsmode 'i', the verification driver's settings) to the minutes since epoch given on the
// command line. Output: one JSON line per set, {"line1", "line2", "steps": [{"t", "error", "r", "v"}]}, TEME km, km/s.
// Build: c++ -std=c++17 -O2 -I<SGP4 dir> -Iharnesses/vallado tools/sgp4_reference_vectors.cpp <SGP4 dir>/SGP4.cpp -o reference_vectors
// (<SGP4 dir>: the Vallado recipe's checkout, harnesses/vallado/README.md; common.h is the recipe's)
// The numbers are SGP4's output for the corpus's own element sets; nothing of Vallado's files is read or copied.
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#include "common.h"
int main(int argc, char **argv) {
    std::vector<double> times;
    for (int i = 1; i < argc; i++) times.push_back(std::strtod(argv[i], nullptr));
    std::string l1, l2;
    while (std::getline(std::cin, l1) && std::getline(std::cin, l2)) {
        if (!l1.empty() && l1.back() == '\r') l1.pop_back();
        if (!l2.empty() && l2.back() == '\r') l2.pop_back();
        elsetrec s;
        read_set(l1, l2, s);
        printf("{\"line1\":"); jstr(l1); printf(",\"line2\":"); jstr(l2); printf(",\"steps\":[");
        for (size_t k = 0; k < times.size(); k++) {
            double r[3], v[3];
            elsetrec c = s;   // each step from the initialised set, as sgp4_tsince does
            bool ok = SGP4Funcs::sgp4(c, times[k], r, v);
            printf("%s{\"t\":", k ? "," : ""); jnum(times[k]);
            printf(",\"error\":%d", ok ? c.error : (c.error ? c.error : -1));
            if (ok && c.error == 0) {
                printf(",\"r\":["); jnum(r[0]); putchar(','); jnum(r[1]); putchar(','); jnum(r[2]);
                printf("],\"v\":["); jnum(v[0]); putchar(','); jnum(v[1]); putchar(','); jnum(v[2]); printf("]");
            }
            printf("}");
        }
        printf("]}\n");
    }
    return 0;
}
