/* Stand-in for GLib, for compiling Gpredict's sgpsdp module in isolation: the module uses g_ascii_strtod only.
   In the "C" locale, which this harness never changes, strtod is the locale-independent conversion g_ascii_strtod promises. */
#include <stdlib.h>
#define g_ascii_strtod(s, endp) strtod((s), (endp))
