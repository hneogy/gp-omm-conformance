// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// gpconf harness for Orekit's TLE reader (0.9.0 item b1), behind --cmd: reads TLE and 2LE through
// org.orekit.propagation.analytical.tle.TLE and prints the records as Orekit holds them, in the corpus's units.
// UNTESTED: written without a JDK or Orekit on the machine that wrote it, from Orekit's documented interface (README.md).
// Values are the library's; nothing is decided for it. Run: java -cp orekit.jar:hipparchus-*.jar:. Harness {fmt}
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.orekit.data.DataContext;
import org.orekit.data.DirectoryCrawler;
import org.orekit.propagation.analytical.tle.TLE;
import org.orekit.time.DateTimeComponents;
import org.orekit.time.TimeScale;
import org.orekit.time.TimeScalesFactory;

public class Harness {
    static final double RAD = 180.0 / Math.PI;
    static final double DAY = 86400.0;

    static String json(String s) {
        StringBuilder o = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"' || c == '\\') o.append('\\').append(c);
            else if (c < 0x20 || c == 0x7f) o.append(String.format("\\u%04x", (int) c));
            else o.append(c);
        }
        return o.append('"').toString();
    }

    static String num(double v) { return Double.isFinite(v) ? Double.toString(v) : json(Double.toString(v)); }

    static String record(String name, String line1, TLE t, TimeScale utc) {
        DateTimeComponents c = t.getDate().getComponents(utc);
        double sec = c.getTime().getSecond();
        long us = Math.round(sec * 1e6);
        String epoch = String.format("%04d-%02d-%02dT%02d:%02d:%02d.%06d", c.getDate().getYear(), c.getDate().getMonth(),
                c.getDate().getDay(), c.getTime().getHour(), c.getTime().getMinute(), us / 1_000_000, us % 1_000_000);
        // Orekit holds the mean motion in rad/s and its derivatives in rad/s² and rad/s³; the TLE prints rev/day,
        // rev/day² over 2 and rev/day³ over 6, so the harness turns them back as the TLE printed them
        double revPerDay = t.getMeanMotion() * DAY / (2 * Math.PI);
        double ndot = t.getMeanMotionFirstDerivative() * DAY * DAY / (4 * Math.PI);
        double nddot = t.getMeanMotionSecondDerivative() * DAY * DAY * DAY / (12 * Math.PI);
        // a blank designator field (columns 10-17, as an analyst object's) is no designator: Orekit's launch getters
        // read it as year 2000, number 0, so the harness writes null there and Orekit's values everywhere else (D-480)
        boolean blank = line1.length() < 17 || line1.substring(9, 17).trim().isEmpty();
        String id = blank ? null
                : String.format("%04d-%03d%s", t.getLaunchYear(), t.getLaunchNumber(), t.getLaunchPiece().trim());
        return "{\"norad_cat_id\":" + t.getSatelliteNumber()
                + ",\"object_name\":" + (name == null ? "null" : json(name))
                + ",\"object_id\":" + (id == null ? "null" : json(id))
                + ",\"epoch\":" + json(epoch)
                + ",\"mean_motion\":" + num(revPerDay)
                + ",\"eccentricity\":" + num(t.getE())
                + ",\"inclination\":" + num(t.getI() * RAD)
                + ",\"ra_of_asc_node\":" + num(t.getRaan() * RAD)
                + ",\"arg_of_pericenter\":" + num(t.getPerigeeArgument() * RAD)
                + ",\"mean_anomaly\":" + num(t.getMeanAnomaly() * RAD)
                + ",\"bstar\":" + num(t.getBStar())
                + ",\"mean_motion_dot\":" + num(ndot)
                + ",\"mean_motion_ddot\":" + num(nddot)
                + ",\"classification_type\":" + json(String.valueOf(t.getClassification()))
                + ",\"ephemeris_type\":" + t.getEphemerisType()
                + ",\"element_set_no\":" + t.getElementNumber()
                + ",\"rev_at_epoch\":" + t.getRevolutionNumberAtEpoch() + "}";
    }

    public static void main(String[] args) throws Exception {
        String fmt = args.length > 0 ? args[0] : "tle";
        if (!fmt.equals("tle") && !fmt.equals("2le")) System.exit(3); // Orekit's TLE class reads element lines only
        String data = System.getenv().getOrDefault("OREKIT_DATA", "orekit-data");
        DataContext.getDefault().getDataProvidersManager().addProvider(new DirectoryCrawler(new File(data)));
        TimeScale utc = TimeScalesFactory.getUTC();
        InputStream in = System.in;
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] buf = new byte[65536];
        for (int n; (n = in.read(buf)) > 0; ) b.write(buf, 0, n);
        String[] lines = new String(b.toByteArray(), StandardCharsets.UTF_8).split("\n", -1);
        for (int i = 0; i < lines.length; i++) if (lines[i].endsWith("\r")) lines[i] = lines[i].substring(0, lines[i].length() - 1);
        List<String> out = new ArrayList<>();
        out.add("{\"_adapter\":{\"refusals\":true}}"); // the harness reports the library's refusals (D-480)
        for (int i = 0; i < lines.length; i++) {
            if (lines[i].startsWith("1 ")) {
                String prev = i > 0 ? lines[i - 1].trim() : "";
                String name = !prev.isEmpty() && !lines[i - 1].startsWith("2 ") ? prev : null;
                // a line 1 with no line 2 after it goes to Orekit too, with an empty line 2, so the answer is the
                // library's, not a silent drop by the harness (D-480)
                boolean paired = i + 1 < lines.length && lines[i + 1].startsWith("2 ");
                String line2 = paired ? lines[i + 1] : "";
                try {
                    // the library's own check first: TLE.isFormatOK tests the lengths, the fields and the checksums
                    if (!TLE.isFormatOK(lines[i], line2)) throw new IllegalArgumentException("TLE.isFormatOK: false");
                    out.add(record(name, lines[i], new TLE(lines[i], line2, utc), utc));
                } catch (Exception e) { // the refusal channel: the record was dropped, with the library's reason
                    out.add("{\"_refused\":" + json(e.getClass().getSimpleName() + ": " + e.getMessage())
                            + ",\"_field\":" + json(lines[i].length() >= 7 ? lines[i].substring(2, 7) : "")
                            + ",\"_input\":" + json(lines[i].length() > 80 ? lines[i].substring(0, 80) : lines[i]) + "}");
                }
                if (paired) i++;
            }
        }
        System.out.write(("[" + String.join(",", out) + "]").getBytes(StandardCharsets.UTF_8));
        System.out.flush();
    }
}
