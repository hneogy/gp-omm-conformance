// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// gpconf harness for SGP.NET 1.6.0 (0.9.0 item b4, C#), behind --cmd: TLE and 2LE through `new Tle(name, l1, l2)`,
// OMM CSV, JSON, XML and KVN through the library's own parsers (OmmCsvParser, OmmJsonParser, OmmXmlParser,
// OmmKvnParser). Values are the library's, as it holds them. UNTESTED where it was written (no .NET SDK there);
// the corpus's scratch CI builds and runs it (README.md).
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using SGPdotNET.Exception;
using SGPdotNET.Parsers;
using SGPdotNET.TLE;

static class Harness
{
    static string Epoch(DateTime t) => t.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.ffffff", System.Globalization.CultureInfo.InvariantCulture);

    static Dictionary<string, object> FromTle(Tle t) => new Dictionary<string, object>
    {
        ["norad_cat_id"] = t.NoradNumber,
        ["object_name"] = string.IsNullOrEmpty(t.Name) ? null : t.Name,
        ["epoch"] = Epoch(t.Epoch),
        ["mean_motion"] = t.MeanMotionRevPerDay,
        ["eccentricity"] = t.Eccentricity,
        ["inclination"] = t.Inclination.Degrees,
        ["ra_of_asc_node"] = t.RightAscendingNode.Degrees,
        ["arg_of_pericenter"] = t.ArgumentPerigee.Degrees,
        ["mean_anomaly"] = t.MeanAnomaly.Degrees,
        ["bstar"] = t.BStarDragTerm,
        ["mean_motion_dot"] = t.MeanMotionDtOver2,
        ["mean_motion_ddot"] = t.MeanMotionDdtOver6,
        ["rev_at_epoch"] = t.OrbitNumber,
    };

    static Dictionary<string, object> FromOmm(OmmData o) => new Dictionary<string, object>
    {
        ["norad_cat_id"] = o.NoradCatID,
        ["object_name"] = string.IsNullOrEmpty(o.ObjectName) ? null : o.ObjectName,
        ["object_id"] = string.IsNullOrEmpty(o.ObjectID) ? null : o.ObjectID,
        ["epoch"] = Epoch(o.Epoch),
        ["mean_motion"] = o.MeanMotion,
        ["eccentricity"] = o.Eccentricity,
        ["inclination"] = o.Inclination,
        ["ra_of_asc_node"] = o.RAOfAscNode,
        ["arg_of_pericenter"] = o.ArgOfPericenter,
        ["mean_anomaly"] = o.MeanAnomaly,
        ["bstar"] = o.BStar,
        ["mean_motion_dot"] = o.MeanMotionDot,
        ["mean_motion_ddot"] = o.MeanMotionDDot,
        ["ephemeris_type"] = o.EphemerisType,
        ["classification_type"] = string.IsNullOrEmpty(o.ClassificationType) ? null : o.ClassificationType,
        ["element_set_no"] = o.ElementSetNo,
        ["rev_at_epoch"] = o.RevAtEpoch,
    };

    static List<object> ParseTle(string text)
    {
        var lines = text.Split('\n');
        for (int i = 0; i < lines.Length; i++) lines[i] = lines[i].TrimEnd('\r');
        var output = new List<object> { new Dictionary<string, object> { ["_adapter"] = new Dictionary<string, object> { ["refusals"] = true } } };
        for (int i = 0; i < lines.Length; i++)
        {
            if (lines[i].StartsWith("1 "))
            {
                // a line 1 with no line 2 after it goes to the library as it is, for the library to answer (D-439)
                bool paired = i + 1 < lines.Length && lines[i + 1].StartsWith("2 ");
                string l2 = paired ? lines[i + 1] : "";
                string name = i > 0 && lines[i - 1].Trim().Length > 0 && !lines[i - 1].StartsWith("2 ") ? lines[i - 1].Trim() : "";
                try { output.Add(FromTle(new Tle(name, lines[i], l2))); }
                catch (Exception e) when (e is TleException || e is FormatException || e is OverflowException || e is ArgumentException)
                {   // the library refused the set: the refusal channel, with its reason
                    output.Add(new Dictionary<string, object> { ["_refused"] = $"{e.GetType().Name}: {e.Message}",
                        ["_field"] = lines[i].Length >= 7 ? lines[i].Substring(2, 5) : null, ["_input"] = lines[i] });
                }
                if (paired) i++;
            }
        }
        return output;
    }

    static int Main(string[] args)
    {
        string fmt = args.Length > 0 ? args[0] : "tle";
        IOmmParser omm = fmt switch { "csv" => new OmmCsvParser(), "json" => new OmmJsonParser(), "xml" => new OmmXmlParser(), "kvn" => new OmmKvnParser(), _ => null };
        if (omm == null && fmt != "tle" && fmt != "2le") return 3;
        try
        {
            using var stdin = Console.OpenStandardInput();
            using var ms = new MemoryStream();
            stdin.CopyTo(ms);
            string text = new UTF8Encoding(false).GetString(ms.ToArray());
            var records = new List<object>();
            if (omm == null) records = ParseTle(text);
            else foreach (var o in omm.Parse(text)) records.Add(FromOmm(o));
            var bytes = JsonSerializer.SerializeToUtf8Bytes(records);
            using var stdout = Console.OpenStandardOutput();
            stdout.Write(bytes, 0, bytes.Length);
            return 0;
        }
        catch (Exception e)   // the file refused as a whole, with the library's reason
        {
            Console.Error.WriteLine($"{e.GetType().Name}: {e.Message}");
            return 1;
        }
    }
}
