// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// A C interface over SGPKit's bridge function, createTLE() (SGP4LibWrapper, Wrapper.hpp), for a Swift target built
// without C++ interoperability. It calls that function and copies out what the libsgp4 Tle it returns holds; it
// reads no line itself.
#ifndef SGPKIT_BRIDGE_H
#define SGPKIT_BRIDGE_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    unsigned int norad_number;
    char int_designator[32];
    int year, month, day, hour, minute, second, microsecond;
    double mean_motion, eccentricity, inclination, ra_of_asc_node, arg_of_pericenter, mean_anomaly;
    double bstar, mean_motion_dt2, mean_motion_ddt6;
    unsigned int orbit_number;
} sgpkit_tle_fields;

/// createTLE(title, line1, line2) with the three strings as given, each as a pointer and a length so that a NUL
/// inside a line reaches the library as std.string(String) would carry it. Returns 1 and fills `out` when the
/// function returned a Tle, 0 when it returned nothing (libsgp4 threw, and the bridge caught it).
int sgpkit_create_tle(const char *title, size_t title_length,
                      const char *line1, size_t line1_length,
                      const char *line2, size_t line2_length,
                      sgpkit_tle_fields *out);

#ifdef __cplusplus
}
#endif

#endif
