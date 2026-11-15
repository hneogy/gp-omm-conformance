// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// A gpconf adapter template for a parser in C++, run by command:
//
//     c++ -std=c++17 -O2 -o adapter templates/cpp/adapter.cpp
//     python3 -m gpconf run --cmd "./adapter {fmt}"
//
// gpconf writes one file to standard input and reads a JSON array of records from standard output (docs/ADAPTERS.md,
// "The command protocol"). Replace toy_parse with a call to your library; keep the rest. The toy parser reads TLE only
// and is here so the template runs as it stands; it is not a parser to use. Same toy as templates/python/adapter.py.
// Catch your library's exceptions and exit 1: an uncaught one calls std::terminate, an abort, which gpconf reads as a
// crash, never a refusal.
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <iterator>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

static const std::string ALPHA5 = "ABCDEFGHJKLMNPQRSTUVWXYZ";  // I and O are skipped

static bool digits(const std::string& s) {
  if (s.empty()) return false;
  for (char c : s) if (c < '0' || c > '9') return false;
  return true;
}

static std::string json(const std::string& s) {  // a JSON string; UTF-8 passes through, control characters escaped
  std::string o = "\"";
  for (unsigned char c : s) {
    if (c == '"' || c == '\\') { o += '\\'; o += char(c); }
    else if (c < 0x20 || c == 0x7f) { char b[8]; std::snprintf(b, sizeof b, "\\u%04x", c); o += b; }
    else o += char(c);
  }
  return o + "\"";
}

static long alpha5(const std::string& f) {
  if (f.size() != 5 || !digits(f.substr(1))) throw std::runtime_error("invalid catalog field " + json(f));
  if (f[0] >= '0' && f[0] <= '9') return std::stol(f);
  auto k = ALPHA5.find(f[0]);
  if (k == std::string::npos) throw std::runtime_error("invalid catalog field " + json(f));
  return long(k + 10) * 10000 + std::stol(f.substr(1));
}

static int checksum(const std::string& l) {
  int s = 0;
  for (size_t i = 0; i < 68 && i < l.size(); i++) s += (l[i] >= '0' && l[i] <= '9') ? l[i] - '0' : (l[i] == '-');
  return s % 10;
}

static std::string trim(const std::string& s) {
  auto a = s.find_first_not_of(" \t"), b = s.find_last_not_of(" \t");
  return a == std::string::npos ? "" : s.substr(a, b - a + 1);
}

static std::string exponent(const std::string& field) {  // " 12345-3" -> "0.12345e-3", compared exactly as text
  std::string f = trim(field), sign;
  if (!f.empty() && f[0] == '-') sign = "-";
  if (!f.empty() && (f[0] == '-' || f[0] == '+')) f = f.substr(1);
  return sign + "0." + f.substr(0, 5) + "e" + (f.size() > 5 ? f.substr(5) : "");
}

static int64_t days_from_civil(int64_t y, unsigned m, unsigned d) {  // H. Hinnant's algorithm, days since 1970-01-01
  y -= m <= 2;
  const int64_t era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = unsigned(y - era * 400);
  const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + int64_t(doe) - 719468;
}

static void civil_from_days(int64_t z, int64_t& y, unsigned& m, unsigned& d) {
  z += 719468;
  const int64_t era = (z >= 0 ? z : z - 146096) / 146097;
  const unsigned doe = unsigned(z - era * 146097);
  const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const unsigned mp = (5 * doy + 2) / 153;
  d = doy - (153 * mp + 2) / 5 + 1;
  m = mp < 10 ? mp + 3 : mp - 9;
  y = int64_t(yoe) + era * 400 + (m <= 2);
}

// "DDD.DDDDDDDD" -> "YYYY-MM-DDThh:mm:ss.ffffff"; eight decimals of a day are whole microseconds (1e-8 day = 864 us)
static std::string epoch_text(int year, const std::string& day) {
  if (day.size() != 12 || day[3] != '.' || !digits(day.substr(0, 3) + day.substr(4)))
    throw std::runtime_error("epoch day " + json(day) + " is not DDD.DDDDDDDD");
  int64_t us = (std::stoll(day.substr(0, 3)) - 1) * 86400000000LL + std::stoll(day.substr(4)) * 864;
  int64_t days = days_from_civil(year, 1, 1) + us / 86400000000LL, rest = us % 86400000000LL;
  int64_t y; unsigned m, d;
  civil_from_days(days, y, m, d);
  char b[40];
  std::snprintf(b, sizeof b, "%04lld-%02u-%02uT%02lld:%02lld:%02lld.%06lld", (long long)y, m, d,
                (long long)(rest / 3600000000LL), (long long)(rest / 60000000LL % 60), (long long)(rest / 1000000 % 60),
                (long long)(rest % 1000000));
  return b;
}

static std::string record(const std::string& name, const std::string& l1, const std::string& l2) {
  if (l1.size() != 69 || l2.size() != 69)
    throw std::runtime_error("line lengths " + std::to_string(l1.size()) + "/" + std::to_string(l2.size()) + ", not 69");
  if (l1[68] - '0' != checksum(l1) || l2[68] - '0' != checksum(l2)) throw std::runtime_error("checksum");
  if (l1.substr(2, 5) != l2.substr(2, 5)) throw std::runtime_error("line 2's catalog number is not line 1's");
  if (!digits(l1.substr(18, 2))) throw std::runtime_error("epoch year " + json(l1.substr(18, 2)) + " is not two digits");
  int yy = std::stoi(l1.substr(18, 2));
  std::string ndot;
  for (char c : l1.substr(33, 10)) if (c != ' ') ndot += c;
  std::ostringstream o;
  o << "{\"norad_cat_id\":" << alpha5(l1.substr(2, 5))
    << ",\"object_name\":" << (name.empty() ? "null" : json(name))
    << ",\"epoch\":" << json(epoch_text(yy >= 57 ? 1900 + yy : 2000 + yy, l1.substr(20, 12)))
    << ",\"mean_motion\":" << json(trim(l2.substr(52, 11)))
    << ",\"eccentricity\":" << json("0." + l2.substr(26, 7))
    << ",\"inclination\":" << json(trim(l2.substr(8, 8)))
    << ",\"ra_of_asc_node\":" << json(trim(l2.substr(17, 8)))
    << ",\"arg_of_pericenter\":" << json(trim(l2.substr(34, 8)))
    << ",\"mean_anomaly\":" << json(trim(l2.substr(43, 8)))
    << ",\"bstar\":" << json(exponent(l1.substr(53, 8)))
    << ",\"mean_motion_dot\":" << json(ndot)
    << ",\"mean_motion_ddot\":" << json(exponent(l1.substr(44, 8))) << "}";
  return o.str();
}

static bool starts(const std::string& s, const char* p) { return s.rfind(p, 0) == 0; }

// The toy: name line optional, two element lines, fixed columns, the checksum checked.
static std::vector<std::string> toy_parse(const std::string& text) {
  std::vector<std::string> lines, out;
  std::string cur;
  for (char c : text) {
    if (c == '\n') { if (!cur.empty() && cur.back() == '\r') cur.pop_back(); lines.push_back(cur); cur.clear(); }
    else cur += c;
  }
  if (!cur.empty() && cur.back() == '\r') cur.pop_back();
  lines.push_back(cur);
  for (size_t i = 0; i < lines.size(); i++) {
    const std::string& l1 = lines[i];
    if (starts(l1, "1 ") && i + 1 < lines.size() && starts(lines[i + 1], "2 ")) {
      std::string name = i > 0 && !starts(lines[i - 1], "2 ") ? trim(lines[i - 1]) : "";
      try {
        out.push_back(record(name, l1, lines[i + 1]));
      } catch (const std::exception& e) {  // the refusal channel: the record was dropped, and why
        out.push_back("{\"_refused\":" + json(std::string("error: ") + e.what()) + ",\"_field\":" + json(l1.substr(2, 5)) +
                      ",\"_input\":" + json(l1.substr(0, 80)) + "}");
      }
      i++;
    } else if (starts(l1, "1 ") || starts(l1, "2 ")) {
      out.push_back("{\"_refused\":\"an element line that pairs with nothing\",\"_field\":" +
                    json(l1.substr(2, l1.size() >= 7 ? 5 : l1.size() - 2)) + ",\"_input\":" + json(l1.substr(0, 80)) + "}");
    }
  }
  return out;
}

int main(int argc, char** argv) {
  std::string fmt = argc > 1 ? argv[1] : "tle";
  if (fmt != "tle" && fmt != "2le") return 3;  // exit 3: format not supported; the file is reported as a skip
  try {
    std::string text((std::istreambuf_iterator<char>(std::cin)), std::istreambuf_iterator<char>());
    auto recs = toy_parse(text);
    std::cout << "[";
    for (size_t i = 0; i < recs.size(); i++) std::cout << (i ? "," : "") << recs[i];
    std::cout << "]";
  } catch (const std::exception& e) {  // anything unexpected: say so and exit 1, never abort
    std::cerr << "adapter: " << e.what() << "\n";
    return 1;
  }
  return 0;
}
