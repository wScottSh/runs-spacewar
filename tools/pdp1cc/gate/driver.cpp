/* Reads one call per line (octal AC, IO, by-name input and sense switches),
 * runs SETUP, makes CALL, and prints AC, IO, the words returned past call+1
 * (INLINE plus skips) and the WATCH words, then `;` and each point plotted
 * during the call (instruction, x, y), in octal. A void CALL leaves AC and
 * IO 0. Built with -include pdp1.h -include prog.c. */
#include <cstdio>
#include <type_traits>

static inline unsigned ac_of(word r) { return r.v; }
static inline unsigned ac_of(word *p) { return pdp1_address(p); }
static inline unsigned io_of(word *) { return 0; }
static inline unsigned ac_of(dword r) { return r.hi.v; }
static inline unsigned io_of(word) { return 0; }
static inline unsigned io_of(dword r) { return r.lo.v; }

template <class F>
static auto result(F f) -> typename std::enable_if<!std::is_void<decltype(f())>::value, decltype(f())>::type {
    return f();
}
template <class F>
static auto result(F f) -> typename std::enable_if<std::is_void<decltype(f())>::value, word>::type {
    f();
    return word::bits(0);
}

int main() {
    unsigned ac, io, byname, sense;
    while (std::scanf("%o %o %o %o", &ac, &io, &byname, &sense) == 4) {
        pdp1_skips = 0;
        pdp1_sense_switches = sense;
        pdp1_plotted.clear();
        SETUP
        auto r = result([&] { return CALL; });
        std::printf("%06o %06o %o", ac_of(r), io_of(r), INLINE_WORDS + pdp1_skips);
        WATCH
        std::printf(" ;");
        for (const pdp1_point &p : pdp1_plotted)
            std::printf(" %06o %06o %06o", p.instruction, p.x, p.y);
        std::printf("\n");
    }
    return 0;
}
