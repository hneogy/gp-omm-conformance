// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// A gpconf adapter template for a parser in C# (or any .NET language), run by command:
//
//     dotnet build -c Release templates/csharp/Adapter.csproj
//     python3 -m gpconf run --cmd "dotnet templates/csharp/bin/Release/net8.0/Adapter.dll {fmt}"
//
// gpconf writes one file to standard input and reads a JSON array of records from standard output (docs/ADAPTERS.md,
// "The command protocol"). Replace ToyParse with a call to your library; keep the rest. The toy parser reads TLE only
// and is here so the template runs as it stands; it is not a parser to use. Same toy as templates/python/adapter.py.
// UNTESTED: written without a .NET SDK on the machine that wrote it; templates/README.md says which were run.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

static class Adapter
{
    const string Alpha5Letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"; // I and O are skipped

    sealed class Refusal : Exception { public Refusal(string why) : base(why) { } }

    static bool Digits(string s) => s.Length > 0 && s.All(c => c >= '0' && c <= '9');

    static string Cols(string l, int a, int b) => l.Substring(Math.Min(a, l.Length), Math.Min(b, l.Length) - Math.Min(a, l.Length));

    static string Trim(string s) => s.Trim(' ', '\t');

    static long Alpha5(string f)
    {
        if (f.Length != 5 || !Digits(f.Substring(1))) throw new Refusal($"invalid catalog field \"{f}\"");
        if (f[0] >= '0' && f[0] <= '9') return long.Parse(f);
        int k = Alpha5Letters.IndexOf(f[0]);
        if (k < 0) throw new Refusal($"invalid catalog field \"{f}\"");
        return (k + 10) * 10000L + long.Parse(f.Substring(1));
    }

    static int Checksum(string l) => l.Take(68).Sum(c => c >= '0' && c <= '9' ? c - '0' : c == '-' ? 1 : 0) % 10;

    // " 12345-3" -> "0.12345e-3", compared exactly as text
    static string Exponent(string field)
    {
        string f = Trim(field), sign = f.StartsWith("-") ? "-" : "";
        f = f.TrimStart('+', '-');
        return $"{sign}0.{Cols(f, 0, 5)}e{Cols(f, 5, f.Length)}";
    }

    // "DDD.DDDDDDDD" -> "YYYY-MM-DDThh:mm:ss.ffffff"; eight decimals of a day are whole microseconds (1e-8 day = 864 us)
    static string EpochText(int year, string day)
    {
        if (day.Length != 12 || day[3] != '.' || !Digits(day.Substring(0, 3) + day.Substring(4)))
            throw new Refusal($"epoch day \"{day}\" is not DDD.DDDDDDDD");
        long us = (long.Parse(day.Substring(0, 3)) - 1) * 86_400_000_000L + long.Parse(day.Substring(4)) * 864;
        var d = new DateTime(year, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddDays(us / 86_400_000_000L);
        long rest = us % 86_400_000_000L;
        return $"{d.Year:D4}-{d.Month:D2}-{d.Day:D2}T{rest / 3_600_000_000L:D2}:{rest / 60_000_000L % 60:D2}:{rest / 1_000_000L % 60:D2}.{rest % 1_000_000L:D6}";
    }

    static Dictionary<string, object?> Record(string? name, string l1, string l2)
    {
        if (l1.Length != 69 || l2.Length != 69) throw new Refusal($"line lengths {l1.Length}/{l2.Length}, not 69");
        if (l1[68] - '0' != Checksum(l1) || l2[68] - '0' != Checksum(l2)) throw new Refusal("checksum");
        if (Cols(l1, 2, 7) != Cols(l2, 2, 7)) throw new Refusal("line 2's catalog number is not line 1's");
        if (!Digits(Cols(l1, 18, 20))) throw new Refusal($"epoch year \"{Cols(l1, 18, 20)}\" is not two digits");
        int yy = int.Parse(Cols(l1, 18, 20));
        return new Dictionary<string, object?>
        {
            ["norad_cat_id"] = Alpha5(Cols(l1, 2, 7)),
            ["object_name"] = name,
            ["epoch"] = EpochText(yy >= 57 ? 1900 + yy : 2000 + yy, Cols(l1, 20, 32)),
            ["mean_motion"] = Trim(Cols(l2, 52, 63)),
            ["eccentricity"] = "0." + Cols(l2, 26, 33),
            ["inclination"] = Trim(Cols(l2, 8, 16)),
            ["ra_of_asc_node"] = Trim(Cols(l2, 17, 25)),
            ["arg_of_pericenter"] = Trim(Cols(l2, 34, 42)),
            ["mean_anomaly"] = Trim(Cols(l2, 43, 51)),
            ["bstar"] = Exponent(Cols(l1, 53, 61)),
            ["mean_motion_dot"] = Cols(l1, 33, 43).Replace(" ", ""),
            ["mean_motion_ddot"] = Exponent(Cols(l1, 44, 52)),
        };
    }

    // The toy: name line optional, two element lines, fixed columns, the checksum checked.
    static List<Dictionary<string, object?>> ToyParse(string text)
    {
        var lines = text.Split('\n').Select(l => l.EndsWith("\r") ? l[..^1] : l).ToArray();
        var output = new List<Dictionary<string, object?>>();
        for (int i = 0; i < lines.Length; i++)
        {
            string l1 = lines[i];
            if (l1.StartsWith("1 ") && i + 1 < lines.Length && lines[i + 1].StartsWith("2 "))
            {
                string prev = i > 0 ? lines[i - 1] : "";
                string? name = Trim(prev).Length > 0 && !prev.StartsWith("2 ") ? Trim(prev) : null;
                try { output.Add(Record(name, l1, lines[i + 1])); }
                catch (Exception e) when (e is Refusal || e is FormatException || e is OverflowException || e is ArgumentException)
                {   // the refusal channel: the record was dropped, and why
                    output.Add(new() { ["_refused"] = "error: " + e.Message, ["_field"] = Cols(l1, 2, 7), ["_input"] = Cols(l1, 0, 80) });
                }
                i++;
            }
            else if (l1.StartsWith("1 ") || l1.StartsWith("2 "))
            {
                output.Add(new() { ["_refused"] = "an element line that pairs with nothing", ["_field"] = Cols(l1, 2, 7), ["_input"] = Cols(l1, 0, 80) });
            }
        }
        return output;
    }

    static int Main(string[] args)
    {
        string fmt = args.Length > 0 ? args[0] : "tle";
        if (fmt != "tle" && fmt != "2le") return 3; // exit 3: format not supported; the file is reported as a skip
        try
        {
            using var stdin = Console.OpenStandardInput();
            using var ms = new MemoryStream();
            stdin.CopyTo(ms);
            var text = new UTF8Encoding(false).GetString(ms.ToArray());
            var json = JsonSerializer.SerializeToUtf8Bytes(ToyParse(text),
                new JsonSerializerOptions { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
            using var stdout = Console.OpenStandardOutput();
            stdout.Write(json, 0, json.Length);
            return 0;
        }
        catch (Exception e) // anything unexpected: say so and exit 1
        {
            Console.Error.WriteLine("adapter: " + e.Message);
            return 1;
        }
    }
}
