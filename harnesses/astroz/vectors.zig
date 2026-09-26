// Vector hooks for gp-omm-conformance over astroz: {op, input} JSON on stdin -> {result} | {error} on stdout.
// alpha5_decode and two_digit_year go through Tle.parseLines on the ISS baseline pair with the field substituted
// (astroz validates no checksum); parse_epoch and parse_catalog_id through Tle.parseOmm on a JSON record with the
// one value substituted (astroz reads OMM as JSON only). No encoder or writer exists.
const std = @import("std");
const Tle = @import("astroz");
const c = @import("common.zig");
const L1 = "1 25544U 98067A   26263.52959654  .00008422  00000+0  15975-3 0  9997";
const L2 = "2 25544  51.6355 213.4302 0003462 300.5590  59.5075 15.49866287 66880";
const OMM_HEAD = "{\"OBJECT_NAME\":\"ISS (ZARYA)\",\"OBJECT_ID\":\"1998-067A\",\"EPOCH\":\"";
const OMM_MID = "\",\"MEAN_MOTION\":15.49866287,\"ECCENTRICITY\":0.0003462,\"INCLINATION\":51.6355,\"RA_OF_ASC_NODE\":213.4302,\"ARG_OF_PERICENTER\":300.559,\"MEAN_ANOMALY\":59.5075,\"EPHEMERIS_TYPE\":0,\"CLASSIFICATION_TYPE\":\"U\",\"NORAD_CAT_ID\":";
const OMM_TAIL = ",\"ELEMENT_SET_NO\":999,\"REV_AT_EPOCH\":66880,\"BSTAR\":0.00015975,\"MEAN_MOTION_DOT\":0.00008422,\"MEAN_MOTION_DDOT\":0}";

pub fn main(init: std.process.Init) !void {
    const gpa = init.gpa;
    const io = init.io;
    var rbuf: [4096]u8 = undefined;
    var fr = std.Io.File.stdin().readerStreaming(io, &rbuf);
    const text = try fr.interface.allocRemaining(gpa, .unlimited);
    defer gpa.free(text);
    var wbuf: [4096]u8 = undefined;
    var fw = std.Io.File.stdout().writerStreaming(io, &wbuf);
    const w = &fw.interface;
    defer w.flush() catch {};

    const parsed = try std.json.parseFromSlice(std.json.Value, gpa, text, .{});
    defer parsed.deinit();
    const op = parsed.value.object.get("op").?.string;
    const inputv = parsed.value.object.get("input").?;
    var ibuf: [64]u8 = undefined;
    const input: []const u8 = switch (inputv) {
        .string => |s| s,
        .integer => |i| try std.fmt.bufPrint(&ibuf, "{d}", .{i}),
        else => "",
    };

    if (c.eql(op, "alpha5_decode") or c.eql(op, "two_digit_year")) {
        var l1: [69]u8 = undefined;
        var l2: [69]u8 = undefined;
        @memcpy(&l1, L1);
        @memcpy(&l2, L2);
        if (c.eql(op, "alpha5_decode")) {
            var f: [5]u8 = .{ ' ', ' ', ' ', ' ', ' ' };
            const n = @min(input.len, 5);
            @memcpy(f[0..n], input[0..n]);
            @memcpy(l1[2..7], &f);
            @memcpy(l2[2..7], &f);
        } else {
            var y: [2]u8 = .{ '0', '0' };
            if (input.len >= 2) @memcpy(&y, input[input.len - 2 ..]) else if (input.len == 1) y[1] = input[0];
            @memcpy(l1[18..20], &y);
        }
        if (Tle.parseLines(&l1, &l2, gpa)) |t| {
            var tle = t;
            defer tle.deinit();
            if (c.eql(op, "alpha5_decode")) try w.print("{{\"result\":{d}}}", .{tle.satelliteNumber}) else try w.print("{{\"result\":{d}}}", .{c.yearFromJd(tle.epochJd)});
        } else |err| try w.print("{{\"error\":\"error.{s}\"}}", .{@errorName(err)});
    } else if (c.eql(op, "parse_epoch") or c.eql(op, "parse_catalog_id")) {
        const json = if (c.eql(op, "parse_epoch"))
            try std.fmt.allocPrint(gpa, "{s}{s}{s}25544{s}", .{ OMM_HEAD, input, OMM_MID, OMM_TAIL })
        else
            try std.fmt.allocPrint(gpa, "{s}2026-09-20T12:42:37.141056{s}{s}{s}", .{ OMM_HEAD, OMM_MID, input, OMM_TAIL });
        defer gpa.free(json);
        if (Tle.parseOmm(json, gpa)) |t| {
            var tle = t;
            defer tle.deinit();
            if (c.eql(op, "parse_epoch")) {
                try w.writeAll("{\"result\":\"");
                try c.isoCalendarFromFields(w, tle.epochYear, tle.epochDay);
                try w.writeAll("\"}");
            } else try w.print("{{\"result\":{d}}}", .{tle.satelliteNumber});
        } else |err| try w.print("{{\"error\":\"error.{s}\"}}", .{@errorName(err)});
    } else if (c.eql(op, "alpha5_encode")) {
        try w.writeAll("{\"error\":\"astroz has no TLE writer\"}");
    } else try w.print("{{\"error\":\"unknown op {s}\"}}", .{op});
}
