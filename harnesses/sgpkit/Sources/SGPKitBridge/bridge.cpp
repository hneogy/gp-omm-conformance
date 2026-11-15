// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
#include "SGPKitBridge.h"

#include <Wrapper.hpp>
#include <cstring>
#include <string>

int sgpkit_create_tle(const char *title, size_t title_length,
                      const char *line1, size_t line1_length,
                      const char *line2, size_t line2_length,
                      sgpkit_tle_fields *out) {
    // the call TLEInterpreter.satelliteData(from:date:) makes, TLEInterpreter.swift lines 95 to 99
    std::optional<libsgp4::Tle> made = createTLE(std::string(title, title_length),
                                                 std::string(line1, line1_length),
                                                 std::string(line2, line2_length));
    if (!made.has_value()) return 0;
    const libsgp4::Tle &t = *made;
    std::memset(out, 0, sizeof *out);
    out->norad_number = t.NoradNumber();
    std::strncpy(out->int_designator, t.IntDesignator().c_str(), sizeof out->int_designator - 1);
    const libsgp4::DateTime epoch = t.Epoch();
    out->year = epoch.Year();
    out->month = epoch.Month();
    out->day = epoch.Day();
    out->hour = epoch.Hour();
    out->minute = epoch.Minute();
    out->second = epoch.Second();
    out->microsecond = epoch.Microsecond();
    out->mean_motion = t.MeanMotion();
    out->eccentricity = t.Eccentricity();
    out->inclination = t.Inclination(true);
    out->ra_of_asc_node = t.RightAscendingNode(true);
    out->arg_of_pericenter = t.ArgumentPerigee(true);
    out->mean_anomaly = t.MeanAnomaly(true);
    out->bstar = t.BStar();
    out->mean_motion_dt2 = t.MeanMotionDt2();
    out->mean_motion_ddt6 = t.MeanMotionDdt6();
    out->orbit_number = t.OrbitNumber();
    return 1;
}
