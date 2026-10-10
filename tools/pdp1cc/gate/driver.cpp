/* Reads one call per line (octal AC, IO and by-name inputs), makes CALL, and
 * prints AC, IO, the words returned past call+1 (INLINE plus skips) and the
 * WATCH words, in octal. Built with -include pdp1.h -include prog.c. */
#include <cstdio>

static inline unsigned ac_of(word r) { return r.v; }
static inline unsigned ac_of(word *p) { return pdp1_address(p); }
static inline unsigned io_of(word *) { return 0; }
static inline unsigned ac_of(dword r) { return r.hi.v; }
static inline unsigned io_of(word) { return 0; }
static inline unsigned io_of(dword r) { return r.lo.v; }

int main() {
    unsigned ac, io, byname;
    while (std::scanf("%o %o %o", &ac, &io, &byname) == 3) {
        pdp1_skips = 0;
        auto r = CALL;
        std::printf("%06o %06o %o", ac_of(r), io_of(r), INLINE_WORDS + pdp1_skips);
        WATCH
        std::printf("\n");
    }
    return 0;
}
