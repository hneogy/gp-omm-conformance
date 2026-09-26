// Shared by the harness and the vectors helper: JSON output helpers, the ISO rendering of a libsgp4 DateTime,
// and a checksum routine of my own for the synthetic lines the vectors helper builds.
#pragma once
#include <cstdio>
#include <string>
#include "Tle.h"
#include "DateTime.h"
static void jstr(const std::string &s) { putchar('"'); for (unsigned char c : s) { if (c == '"' || c == '\\') { putchar('\\'); putchar(c); } else if (c < 0x20) printf("\\u%04x", c); else putchar(c); } putchar('"'); }
static std::string iso(const libsgp4::DateTime &d) { char b[40]; snprintf(b, sizeof b, "%04d-%02d-%02dT%02d:%02d:%02d.%06d", d.Year(), d.Month(), d.Day(), d.Hour(), d.Minute(), d.Second(), d.Microsecond()); return b; }
static std::string with_checksum(std::string line) { int s = 0; for (size_t i = 0; i < 68 && i < line.size(); i++) { char c = line[i]; if (c >= '0' && c <= '9') s += c - '0'; else if (c == '-') s += 1; } line.resize(68, ' '); line += char('0' + s % 10); return line; }
