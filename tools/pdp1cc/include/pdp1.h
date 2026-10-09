/*
 * pdp1.h -- the pdp1c C dialect.
 *
 * Two readers:
 *   pdp1cc (defines __PDP1CC__): sees typedefs, attribute spellings and the
 *       builtin names it lowers by rule. No system headers.
 *   g++ -std=c++14 -include pdp1.h f.c: the executable reference. `word`
 *       is a class with 18-bit ones' complement operators, so the dialect
 *       C runs natively with the meaning the PDP-1 gives it. Semantics
 *       follow open-simh pdp1_cpu.c.
 *
 * Dialect summary. Storage is chosen by declaration: an automatic `word`
 * lives in AC, a `register word` lives in IO, an initialized file-scope
 * `word` is a data word placed at its definition, and a JDA function's first
 * parameter is its entry word. Operand order is instruction order:
 * `a + b` is `lac a / add b`. Comparisons are only against 0 and test the
 * sign bit and zero exactly as the skip group does (so -0 < 0 holds and
 * -0 == 0 does not). A negative C constant -n is the ones' complement of n.
 */
#ifndef PDP1_H
#define PDP1_H

#if defined(__PDP1CC__)

typedef int word;
#define JDA __attribute__((pdp1_jda))
void rcl(word hi, word lo, int n);

#elif defined(__cplusplus)

#include <cstdint>
#include <cstdlib>

#define JDA

typedef std::uint32_t pdp1_bits;
static const pdp1_bits PDP1_MASK = (1u << 18) - 1;
static const pdp1_bits PDP1_SIGN = 1u << 17;

struct word {
    pdp1_bits v;
    word() : v(0) {}
    word(int i) : v((i < 0 ? ~(pdp1_bits)(-i) : (pdp1_bits)i) & PDP1_MASK) {
        if (i > (int)PDP1_MASK || -i > (int)PDP1_MASK) std::abort();
    }
    static word bits(pdp1_bits b) { word w; w.v = b & PDP1_MASK; return w; }

    friend word operator+(word a, word b) {              /* add */
        pdp1_bits r = a.v + b.v;
        if (r > PDP1_MASK) r = (r + 1) & PDP1_MASK;
        return bits(r == PDP1_MASK ? 0 : r);
    }
    friend word operator-(word a, word b) {              /* sub */
        pdp1_bits r = (a.v ^ PDP1_MASK) + b.v;
        if (r > PDP1_MASK) r = (r + 1) & PDP1_MASK;
        return bits(r ^ PDP1_MASK);
    }
    friend word operator-(word a) { return bits(a.v ^ PDP1_MASK); }   /* cma */
    friend word operator~(word a) { return bits(a.v ^ PDP1_MASK); }   /* cma */
    friend word operator&(word a, word b) { return bits(a.v & b.v); }
    friend word operator|(word a, word b) { return bits(a.v | b.v); }
    friend word operator^(word a, word b) { return bits(a.v ^ b.v); }
    friend word operator<<(word a, int n) {              /* sal */
        while (n--) a.v = (a.v & PDP1_SIGN) | ((a.v << 1) & (PDP1_MASK >> 1)) | ((a.v & PDP1_SIGN) ? 1 : 0);
        return a;
    }
    friend word operator>>(word a, int n) {              /* sar */
        while (n--) a.v = (a.v >> 1) | (a.v & PDP1_SIGN);
        return a;
    }
    /* The skip group compares with 0 only. */
    static void zero_only(int z) { if (z != 0) std::abort(); }
    friend bool operator<(word a, int z)  { zero_only(z); return (a.v & PDP1_SIGN) != 0; }   /* sma */
    friend bool operator>=(word a, int z) { zero_only(z); return (a.v & PDP1_SIGN) == 0; }   /* spa */
    friend bool operator<=(word a, int z) { zero_only(z); return (a.v & PDP1_SIGN) || a.v == 0; }
    friend bool operator>(word a, int z)  { return !(a <= z); }
    friend bool operator==(word a, word b) { return a.v == b.v; }                            /* sza, sas */
    friend bool operator!=(word a, word b) { return a.v != b.v; }
    word &operator++() {                                 /* idx, isp */
        v = v + 1;
        if (v >= PDP1_MASK) v = (v + 1) & PDP1_MASK;
        return *this;
    }
};

/* rcl ns: rotate the 36-bit AC:IO pair left (h is AC, l is IO). */
static inline void rcl(word &h, word &l, int n) {
    while (n--) {
        pdp1_bits c = (h.v >> 17) & 1;
        h.v = ((h.v << 1) | ((l.v >> 17) & 1)) & PDP1_MASK;
        l.v = ((l.v << 1) | c) & PDP1_MASK;
    }
}

#else
#error "pdp1.h: compile with g++ (executable reference) or pdp1cc"
#endif

#endif /* PDP1_H */
