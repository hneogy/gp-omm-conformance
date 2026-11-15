// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// A gpconf adapter template for a parser in Java (or any JVM language), run by command:
//
//     java templates/java/Adapter.java {fmt}        (Java 11 and later run a single source file directly)
//     python3 -m gpconf run --cmd "java templates/java/Adapter.java {fmt}"
//
// gpconf writes one file to standard input and reads a JSON array of records from standard output (docs/ADAPTERS.md,
// "The command protocol"). Replace toyParse with a call to your library; keep the rest. The toy parser reads TLE only
// and is here so the template runs as it stands; it is not a parser to use. Same toy as templates/python/adapter.py.
// UNTESTED: written without a JDK on the machine that wrote it; templates/README.md says which templates were run.
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public class Adapter {
    static final String ALPHA5 = "ABCDEFGHJKLMNPQRSTUVWXYZ"; // I and O are skipped

    static class Refusal extends Exception {
        Refusal(String why) { super(why); }
    }

    static boolean digits(String s) {
        if (s.isEmpty()) return false;
        for (char c : s.toCharArray()) if (c < '0' || c > '9') return false;
        return true;
    }

    static String json(String s) { // a JSON string; control characters escaped
        StringBuilder o = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"' || c == '\\') o.append('\\').append(c);
            else if (c < 0x20 || c == 0x7f) o.append(String.format("\\u%04x", (int) c));
            else o.append(c);
        }
        return o.append('"').toString();
    }

    static String cols(String l, int a, int b) { return l.substring(Math.min(a, l.length()), Math.min(b, l.length())); }

    static String trim(String s) { return s.replaceAll("^[ \t]+|[ \t]+$", ""); }

    static long alpha5(String f) throws Refusal {
        if (f.length() != 5 || !digits(f.substring(1))) throw new Refusal("invalid catalog field " + json(f));
        char c = f.charAt(0);
        if (c >= '0' && c <= '9') return Long.parseLong(f);
        int k = ALPHA5.indexOf(c);
        if (k < 0) throw new Refusal("invalid catalog field " + json(f));
        return (k + 10) * 10000L + Long.parseLong(f.substring(1));
    }

    static int checksum(String l) {
        int s = 0;
        for (int i = 0; i < 68 && i < l.length(); i++) {
            char c = l.charAt(i);
            s += (c >= '0' && c <= '9') ? c - '0' : (c == '-' ? 1 : 0);
        }
        return s % 10;
    }

    static String exponent(String field) { // " 12345-3" -> "0.12345e-3", compared exactly as text
        String f = trim(field), sign = f.startsWith("-") ? "-" : "";
        if (f.startsWith("-") || f.startsWith("+")) f = f.substring(1);
        return sign + "0." + cols(f, 0, 5) + "e" + cols(f, 5, f.length());
    }

    // "DDD.DDDDDDDD" -> "YYYY-MM-DDThh:mm:ss.ffffff"; eight decimals of a day are whole microseconds (1e-8 day = 864 us)
    static String epochText(int year, String day) throws Refusal {
        if (day.length() != 12 || day.charAt(3) != '.' || !digits(day.substring(0, 3) + day.substring(4)))
            throw new Refusal("epoch day " + json(day) + " is not DDD.DDDDDDDD");
        long us = (Long.parseLong(day.substring(0, 3)) - 1) * 86_400_000_000L + Long.parseLong(day.substring(4)) * 864;
        LocalDate d = LocalDate.of(year, 1, 1).plusDays(us / 86_400_000_000L);
        long rest = us % 86_400_000_000L;
        return String.format("%04d-%02d-%02dT%02d:%02d:%02d.%06d", d.getYear(), d.getMonthValue(), d.getDayOfMonth(),
                rest / 3_600_000_000L, rest / 60_000_000L % 60, rest / 1_000_000L % 60, rest % 1_000_000L);
    }

    static String record(String name, String l1, String l2) throws Refusal {
        if (l1.length() != 69 || l2.length() != 69) throw new Refusal("line lengths " + l1.length() + "/" + l2.length() + ", not 69");
        if (l1.charAt(68) - '0' != checksum(l1) || l2.charAt(68) - '0' != checksum(l2)) throw new Refusal("checksum");
        if (!cols(l1, 2, 7).equals(cols(l2, 2, 7))) throw new Refusal("line 2's catalog number is not line 1's");
        if (!digits(cols(l1, 18, 20))) throw new Refusal("epoch year " + json(cols(l1, 18, 20)) + " is not two digits");
        int yy = Integer.parseInt(cols(l1, 18, 20));
        return "{\"norad_cat_id\":" + alpha5(cols(l1, 2, 7))
                + ",\"object_name\":" + (name == null ? "null" : json(name))
                + ",\"epoch\":" + json(epochText(yy >= 57 ? 1900 + yy : 2000 + yy, cols(l1, 20, 32)))
                + ",\"mean_motion\":" + json(trim(cols(l2, 52, 63)))
                + ",\"eccentricity\":" + json("0." + cols(l2, 26, 33))
                + ",\"inclination\":" + json(trim(cols(l2, 8, 16)))
                + ",\"ra_of_asc_node\":" + json(trim(cols(l2, 17, 25)))
                + ",\"arg_of_pericenter\":" + json(trim(cols(l2, 34, 42)))
                + ",\"mean_anomaly\":" + json(trim(cols(l2, 43, 51)))
                + ",\"bstar\":" + json(exponent(cols(l1, 53, 61)))
                + ",\"mean_motion_dot\":" + json(cols(l1, 33, 43).replace(" ", ""))
                + ",\"mean_motion_ddot\":" + json(exponent(cols(l1, 44, 52))) + "}";
    }

    // The toy: name line optional, two element lines, fixed columns, the checksum checked.
    static List<String> toyParse(String text) {
        String[] lines = text.split("\n", -1);
        for (int i = 0; i < lines.length; i++) if (lines[i].endsWith("\r")) lines[i] = lines[i].substring(0, lines[i].length() - 1);
        List<String> out = new ArrayList<>();
        for (int i = 0; i < lines.length; i++) {
            String l1 = lines[i];
            if (l1.startsWith("1 ") && i + 1 < lines.length && lines[i + 1].startsWith("2 ")) {
                String prev = i > 0 ? lines[i - 1] : "";
                String name = !trim(prev).isEmpty() && !prev.startsWith("2 ") ? trim(prev) : null;
                try {
                    out.add(record(name, l1, lines[i + 1]));
                } catch (Refusal | RuntimeException e) { // the refusal channel: the record was dropped, and why
                    out.add("{\"_refused\":" + json("error: " + e.getMessage()) + ",\"_field\":" + json(cols(l1, 2, 7))
                            + ",\"_input\":" + json(cols(l1, 0, 80)) + "}");
                }
                i++;
            } else if (l1.startsWith("1 ") || l1.startsWith("2 ")) {
                out.add("{\"_refused\":\"an element line that pairs with nothing\",\"_field\":" + json(cols(l1, 2, 7))
                        + ",\"_input\":" + json(cols(l1, 0, 80)) + "}");
            }
        }
        return out;
    }

    static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] buf = new byte[65536];
        for (int n; (n = in.read(buf)) > 0; ) b.write(buf, 0, n);
        return b.toByteArray();
    }

    public static void main(String[] args) {
        String fmt = args.length > 0 ? args[0] : "tle";
        if (!fmt.equals("tle") && !fmt.equals("2le")) System.exit(3); // exit 3: format not supported, reported as a skip
        try {
            String text = new String(readAll(System.in), StandardCharsets.UTF_8);
            System.out.write(("[" + String.join(",", toyParse(text)) + "]").getBytes(StandardCharsets.UTF_8)); // UTF-8 whatever the platform's default
            System.out.flush();
        } catch (Exception e) { // anything unexpected: say so and exit 1
            System.err.println("adapter: " + e);
            System.exit(1);
        }
    }
}
