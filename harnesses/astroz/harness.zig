// Harness for gp-omm-conformance over astroz (ATTron/astroz, GPL-3.0, called unmodified through its Tle module):
// TLE and 2LE through Tle.MultiIterator + Tle.parseLines (the library's own file walk), OMM JSON through
// Tle.parseOmmArray. Runner --cmd protocol: raw bytes on stdin, JSON records on stdout, exit 3 for formats the
// library has no reader for (CSV, XML, KVN). argv: fmt, mode ('fields' = epoch rebuilt from epochYear/epochDay
// with the pivot at 57; 'jd' = epoch from the parser's epochJd, the value the propagators use).
const std = @import("std");
const Tle = @import("astroz");
const c = @import("common.zig");

fn emit(w: *std.Io.Writer, t: Tle, mode: []const u8) !void {
    try w.print("{{\"norad_cat_id\":{d},\"object_name\":null,\"_designator\":", .{t.satelliteNumber});
    try c.jsonString(w, t.intlDesignator);
    try w.print(",\"classification\":\"{c}\",\"epoch\":\"", .{t.classification});
    if (c.eql(mode, "jd")) try c.isoFromJd(w, t.epochJd) else try c.isoFromFields(w, t.epochYear, t.epochDay);
    try w.print("\",\"_epoch_year_field\":{d},\"_epoch_day_field\":{d},\"_epoch_jd\":{d},\"_epoch_j2000_field\":{d}", .{ t.epochYear, t.epochDay, t.epochJd, t.epoch });
    try w.print(",\"mean_motion\":{d},\"eccentricity\":{d},\"inclination\":{d},\"ra_of_asc_node\":{d},\"arg_of_pericenter\":{d},\"mean_anomaly\":{d}", .{ t.mMotion, t.eccentricity, t.inclination, t.rightAscension, t.perigee, t.mAnomaly });
    try w.print(",\"bstar\":{d},\"mean_motion_dot\":{d},\"rev_at_epoch\":{d},\"element_set_no\":{d},\"ephemeris_type\":{d}}}", .{ t.bstarDrag, t.firstDerMeanMotion, t.revNum, t.elemNumber, t.ephemType });
}

pub fn main(init: std.process.Init) !void {
    const gpa = init.gpa;
    const io = init.io;
    var it = std.process.Args.Iterator.init(init.minimal.args);
    _ = it.next();
    const fmt = it.next() orelse "tle";
    const mode = it.next() orelse "fields";
    const is_json = c.eql(fmt, "json");
    if (!(c.eql(fmt, "tle") or c.eql(fmt, "2le") or is_json)) std.process.exit(3);

    var rbuf: [65536]u8 = undefined;
    var fr = std.Io.File.stdin().readerStreaming(io, &rbuf);
    const text = try fr.interface.allocRemaining(gpa, .unlimited);
    defer gpa.free(text);

    var wbuf: [65536]u8 = undefined;
    var fw = std.Io.File.stdout().writerStreaming(io, &wbuf);
    const w = &fw.interface;
    var ebuf: [4096]u8 = undefined;
    var fe = std.Io.File.stderr().writerStreaming(io, &ebuf);
    const e = &fe.interface;

    try w.writeByte('[');
    var first = true;
    if (is_json) {
        const tles = Tle.parseOmmArray(text, gpa) catch |err| {
            try e.print("parseOmmArray: error.{s}\n", .{@errorName(err)});
            try e.flush();
            try w.writeByte(']');
            try w.flush();
            return;
        };
        defer {
            for (tles) |*t| {
                var tle = t.*;
                tle.deinit();
            }
            gpa.free(tles);
        }
        for (tles) |t| {
            if (!first) try w.writeByte(',');
            first = false;
            try emit(w, t, mode);
        }
    } else {
        var iter = Tle.MultiIterator.init(text);
        var n: usize = 0;
        var bad: usize = 0;
        while (iter.next()) |pair| {
            n += 1;
            if (Tle.parseLines(pair.line1, pair.line2, gpa)) |t| {
                var tle = t;
                defer tle.deinit();
                if (!first) try w.writeByte(',');
                first = false;
                try emit(w, tle, mode);
            } else |err| {
                bad += 1;
                if (bad <= 5) try e.print("set {d} ({s}): error.{s}\n", .{ n, pair.line1[0..7], @errorName(err) });
            }
        }
        try e.print("sets seen {d}, refused {d}\n", .{ n, bad });
        try e.flush();
    }
    try w.writeByte(']');
    try w.flush();
}
