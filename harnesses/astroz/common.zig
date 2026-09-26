// Shared helpers for the gp-omm-conformance harness over astroz (the corpus's own code; astroz is GPL-3.0 and is only called).
const std = @import("std");

pub fn eql(a: []const u8, b: []const u8) bool {
    return std.mem.eql(u8, a, b);
}

/// ISO day-of-year epoch from the parser's two-digit year and fractional day, with the TLE pivot at 57.
pub fn isoFromFields(w: *std.Io.Writer, epochYear: u16, epochDay: f64) !void {
    const year: u32 = if (epochYear < 57) 2000 + @as(u32, epochYear) else 1900 + @as(u32, epochYear);
    var doy: u32 = @intFromFloat(@floor(epochDay));
    var us: u64 = @intFromFloat(@round((epochDay - @floor(epochDay)) * 86400e6));
    if (us >= 86400_000_000) {
        us -= 86400_000_000;
        doy += 1;
    }
    try w.print("{d:0>4}-{d:0>3}T{d:0>2}:{d:0>2}:{d:0>2}.{d:0>6}", .{ year, doy, us / 3600_000_000, (us % 3600_000_000) / 60_000_000, (us % 60_000_000) / 1_000_000, us % 1_000_000 });
}

/// ISO calendar epoch from a Julian date (the parser's epochJd), microsecond-rounded.
pub fn isoFromJd(w: *std.Io.Writer, jd: f64) !void {
    const unix_us: i64 = @intFromFloat(@round((jd - 2440587.5) * 86400e6));
    try isoFromUnixUs(w, unix_us);
}

/// ISO calendar epoch from microseconds since 1970-01-01 (Howard Hinnant's civil-from-days).
pub fn isoFromUnixUs(w: *std.Io.Writer, unix_us: i64) !void {
    const day_us: i64 = 86400_000_000;
    const days: i64 = @divFloor(unix_us, day_us);
    const rem: u64 = @intCast(unix_us - days * day_us);
    const z: i64 = days + 719468;
    const era: i64 = @divFloor(z, 146097);
    const doe: u64 = @intCast(z - era * 146097);
    const yoe: u64 = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    const y: i64 = @as(i64, @intCast(yoe)) + era * 400;
    const doy: u64 = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const mp: u64 = (5 * doy + 2) / 153;
    const d: u64 = doy - (153 * mp + 2) / 5 + 1;
    const m: u64 = if (mp < 10) mp + 3 else mp - 9;
    const year: u64 = @intCast(if (m <= 2) y + 1 else y);
    try w.print("{d:0>4}-{d:0>2}-{d:0>2}T{d:0>2}:{d:0>2}:{d:0>2}.{d:0>6}", .{ year, m, d, rem / 3600_000_000, (rem % 3600_000_000) / 60_000_000, (rem % 60_000_000) / 1_000_000, rem % 1_000_000 });
}

/// Days since 1970-01-01 for a civil date (Howard Hinnant's algorithm).
pub fn daysFromCivil(y0: i64, m: u64, d: u64) i64 {
    const y: i64 = if (m <= 2) y0 - 1 else y0;
    const era: i64 = @divFloor(y, 400);
    const yoe: u64 = @intCast(y - era * 400);
    const mp: u64 = if (m > 2) m - 3 else m + 9;
    const doy: u64 = (153 * mp + 2) / 5 + d - 1;
    const doe: u64 = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + @as(i64, @intCast(doe)) - 719468;
}

/// ISO calendar epoch from the parser's two-digit year and fractional day (pivot at 57), microsecond-rounded,
/// with no Julian-date round trip.
pub fn isoCalendarFromFields(w: *std.Io.Writer, epochYear: u16, epochDay: f64) !void {
    const year: i64 = if (epochYear < 57) 2000 + @as(i64, epochYear) else 1900 + @as(i64, epochYear);
    const doy: i64 = @intFromFloat(@floor(epochDay));
    const us: i64 = @intFromFloat(@round((epochDay - @floor(epochDay)) * 86400e6));
    const days: i64 = daysFromCivil(year, 1, 1) + doy - 1;
    try isoFromUnixUs(w, days * 86400_000_000 + us);
}

pub fn yearFromJd(jd: f64) i64 {
    const days: i64 = @intFromFloat(@floor(jd - 2440587.5));
    const z: i64 = days + 719468;
    const era: i64 = @divFloor(z, 146097);
    const doe: u64 = @intCast(z - era * 146097);
    const yoe: u64 = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    const y: i64 = @as(i64, @intCast(yoe)) + era * 400;
    const doy: u64 = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const mp: u64 = (5 * doy + 2) / 153;
    const m: u64 = if (mp < 10) mp + 3 else mp - 9;
    return if (m <= 2) y + 1 else y;
}

pub fn jsonString(w: *std.Io.Writer, s: []const u8) !void {
    try w.writeByte('"');
    for (s) |c| {
        switch (c) {
            '"' => try w.writeAll("\\\""),
            '\\' => try w.writeAll("\\\\"),
            else => if (c < 0x20) try w.print("\\u{x:0>4}", .{c}) else try w.writeByte(c),
        }
    }
    try w.writeByte('"');
}
