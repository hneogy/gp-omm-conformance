/* Harness for gp-omm-conformance: reads TLE text on stdin, hands every 3-line (or name-less 2-line) set to Gpredict's
   own Get_Next_Tle_Set() (src/sgpsdp/sgp_in.c, unmodified), and prints the parsed tle_t as JSON records in the
   runner's --cmd protocol. usage: gpredict-harness <fmt>; exit 3 = format unsupported. Written for the corpus; the
   Gpredict sources it links are GPL-2.0 and are fetched separately, never copied into the corpus. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include "sgp4sdp4.h"

static void json_string(const char *s) {
    putchar('"');
    for (; *s; s++) {
        if (*s == '"' || *s == '\\') { putchar('\\'); putchar(*s); }
        else if ((unsigned char)*s < 0x20) printf("\\u%04x", *s);
        else putchar(*s);
    }
    putchar('"');
}

/* Gpredict keeps the epoch as the raw YYDDD.DDDDDDDD double; its year pivot lives in Julian_Date_of_Epoch()
   (sgp_time.c). The year is taken from that Julian date through Gpredict's Calendar_Date(); the day fraction from the
   raw double, so the sub-second digits are Gpredict's storage, not the Julian date's 40 us resolution. */
static void iso_epoch(double epoch, char *out, size_t n) {
    struct tm cal;
    double jd = Julian_Date_of_Epoch(epoch);
    Calendar_Date(jd, &cal);
    int year = cal.tm_year;   /* Gpredict's Calendar_Date() stores the full year, not the C library's years-since-1900 */
    double doyf = fmod(epoch, 1000.0);
    int doy = (int)floor(doyf);
    long long us = llround((doyf - doy) * 86400e6);
    if (us >= 86400000000LL) { us -= 86400000000LL; doy += 1; }
    snprintf(out, n, "%04d-%03dT%02d:%02d:%02d.%06lld", year, doy, (int)(us / 3600000000LL), (int)((us % 3600000000LL) / 60000000LL),
             (int)((us % 60000000LL) / 1000000LL), us % 1000000LL);
}

int main(int argc, char **argv) {
    if (argc < 2 || (strcmp(argv[1], "tle") != 0 && strcmp(argv[1], "2le") != 0)) return 3;
    static char buf[1 << 24];
    size_t got = fread(buf, 1, sizeof buf - 1, stdin);
    buf[got] = '\0';
    /* split into lines */
    static char *lines[400000]; int n = 0;
    for (char *p = strtok(buf, "\n"); p && n < 400000; p = strtok(NULL, "\n")) { size_t l = strlen(p); if (l && p[l-1] == '\r') p[l-1] = '\0'; lines[n++] = p; }
    printf("[");
    int first = 1, refused = 0;
    for (int i = 0; i + 1 < n; i++) {
        if (strncmp(lines[i], "1 ", 2) != 0 || strncmp(lines[i + 1], "2 ", 2) != 0) continue;
        const char *name = (i > 0 && strncmp(lines[i-1], "1 ", 2) != 0 && strncmp(lines[i-1], "2 ", 2) != 0) ? lines[i-1] : NULL;
        char line[3][80]; memset(line, 0, sizeof line);
        /* a name-less 2LE pair gets the catalog field as its name: Get_Next_Tle_Set() reads a name line first */
        if (name) strncpy(line[0], name, 79); else strncpy(line[0], lines[i] + 2, 5);
        strncpy(line[1], lines[i], 79); strncpy(line[2], lines[i + 1], 79);
        tle_t tle; memset(&tle, 0, sizeof tle);
        int rc = Get_Next_Tle_Set(line, &tle);
        if (rc != 1) { refused++; fprintf(stderr, "gpredict refused line %d (Get_Next_Tle_Set returned %d): %s\n", i + 1, rc, lines[i]); continue; }
        char iso[40]; iso_epoch(tle.epoch, iso, sizeof iso);
        if (!first) printf(","); first = 0;
        printf("{\"norad_cat_id\":%d,\"object_name\":", tle.catnr);
        if (name) json_string(tle.sat_name); else printf("null");   /* the placeholder name is the harness's, not Gpredict's */
        printf(",\"_idesg\":"); json_string(tle.idesg);
        printf(",\"epoch\":\"%s\",\"_epoch_raw\":%.17g,\"_epoch_year_field\":%d", iso, tle.epoch, tle.epoch_year);
        printf(",\"mean_motion\":%.17g,\"eccentricity\":%.17g,\"inclination\":%.17g,\"ra_of_asc_node\":%.17g,\"arg_of_pericenter\":%.17g,\"mean_anomaly\":%.17g",
               tle.xno, tle.eo, tle.xincl, tle.xnodeo, tle.omegao, tle.xmo);
        printf(",\"bstar\":%.17g,\"mean_motion_dot\":%.17g,\"mean_motion_ddot\":%.17g,\"element_set_no\":%d,\"rev_at_epoch\":%d}",
               tle.bstar, tle.xndt2o, tle.xndd6o, tle.elset, tle.revnum);
    }
    printf("]\n");
    if (refused) fprintf(stderr, "%d set(s) refused\n", refused);
    return 0;
}
