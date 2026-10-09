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
 *
 * Calling conventions. JDA: the first plain parameter arrives in AC and is
 * stored in the entry word, which is its storage. A `register` parameter
 * arrives in IO. A BYNAME parameter is the word after the call (`lac x`),
 * which the callee fetches with `xct` each time it reads the parameter, and
 * the callee returns past it. BLOCK: no entry word and no prologue; entered
 * by a jump with its plain parameter in AC. A JDA function whose returns all
 * tail-call one BLOCK shares that block's exit. skip_return() makes the
 * current call return one word further, skipping the caller's next word.
 * JSP: entered by `jsp f`, which leaves the return address in AC, so the
 * only parameter is a `register` one; the result comes back in AC (or
 * AC:IO). XCT: a function that is one instruction, executed in place by
 * `xct f`; its plain parameter is AC and its register parameter IO. A
 * pointer to a function type is a word holding its address; `return p(...)`
 * jumps through it. A function's name used as a value is its address.
 * ENTRY_CELL(f) names f's entry word; several names may share it.
 * SYM("x") gives a C name the Macro symbol x. AT(a) lays a definition out
 * from address a. RESERVE sets aside the words of an uninitialized object
 * where it is defined; they are not punched, so the machine leaves whatever
 * core held there. MINUS_ZERO is the word with every bit set.
 *
 * Hardware builtins: tyi() reads the typewriter into IO; lsm() leaves
 * sequence break mode.
 *
 * Under g++ the macros below are empty. The reference build
 * (tools/pdp1cc/gate/reference.py) binds the two storage facts a macro
 * cannot spell: a JDA function's first parameter and every ENTRY_CELL name
 * of it become one cell, which the call fills; a BYNAME parameter becomes a
 * `const word &` to the caller's word, read again at every use.
 */
#ifndef PDP1_H
#define PDP1_H

#if defined(__PDP1CC__)

typedef int word;
typedef struct dword { word hi, lo; } dword;
#define JDA __attribute__((pdp1_jda))
#define BLOCK __attribute__((pdp1_block))
#define BYNAME __attribute__((pdp1_byname))
#define SYM(s) __attribute__((pdp1_sym(s)))
#define ENTRY_CELL(f) __attribute__((pdp1_entry_cell(f)))
#define XCT __attribute__((pdp1_xct))
#define JSP __attribute__((pdp1_jsp))
#define AT(a) __attribute__((pdp1_at(a)))
#define RESERVE __attribute__((pdp1_reserve))
#define MINUS_ZERO (-(word)0)
word tyi(void);
void lsm(void);
void rcl(word hi, word lo, int n);
void rcr(word hi, word lo, int n);
void scl(word hi, word lo, int n);
void scr(word hi, word lo, int n);
void mus(word hi, word lo, word m);
void dis(word hi, word lo, word m);
word ral(word a, int n);
word rar(word a, int n);
word ril(word io, int n);
word rir(word io, int n);
void skip_return(void);

#elif defined(__cplusplus)

#include <cstdint>
#include <cstdlib>

#define JDA
#define BLOCK
#define BYNAME
#define SYM(s)
#define ENTRY_CELL(f)
#define XCT
#define JSP
#define AT(a)
#define RESERVE
#define MINUS_ZERO (-(word)0)

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
    word &operator+=(word b) { return *this = *this + b; }
    word &operator-=(word b) { return *this = *this - b; }
    word &operator++() {                                 /* idx, isp */
        v = v + 1;
        if (v >= PDP1_MASK) v = (v + 1) & PDP1_MASK;
        return *this;
    }
};

/* The AC:IO pair: hi is AC, lo is IO. */
struct dword { word hi, lo; };

/* Single-register rotates: ral/rar on AC, ril/rir on IO. */
static inline word ral(word a, int n) {
    while (n--) a.v = ((a.v << 1) | (a.v >> 17)) & PDP1_MASK;
    return a;
}
static inline word rar(word a, int n) {
    while (n--) a.v = ((a.v >> 1) | ((a.v & 1) << 17)) & PDP1_MASK;
    return a;
}
static inline word ril(word io, int n) { return ral(io, n); }
static inline word rir(word io, int n) { return rar(io, n); }

/* Pair operations on the 36-bit AC:IO register (h is AC, l is IO). */
static inline void rcl(word &h, word &l, int n) {        /* rcl ns */
    while (n--) {
        pdp1_bits c = (h.v >> 17) & 1;
        h.v = ((h.v << 1) | ((l.v >> 17) & 1)) & PDP1_MASK;
        l.v = ((l.v << 1) | c) & PDP1_MASK;
    }
}
static inline void rcr(word &h, word &l, int n) {        /* rcr ns */
    while (n--) {
        pdp1_bits c = l.v & 1;
        l.v = ((l.v >> 1) | ((h.v & 1) << 17)) & PDP1_MASK;
        h.v = ((h.v >> 1) | (c << 17)) & PDP1_MASK;
    }
}
static inline void scl(word &h, word &l, int n) {        /* scl ns: sign of h kept */
    while (n--) {
        pdp1_bits s = h.v & PDP1_SIGN;
        h.v = s | ((h.v << 1) & (PDP1_MASK >> 1)) | ((l.v >> 17) & 1);
        l.v = ((l.v << 1) | (s ? 1 : 0)) & PDP1_MASK;
    }
}
static inline void scr(word &h, word &l, int n) {        /* scr ns: sign of h kept */
    while (n--) {
        l.v = ((l.v >> 1) | ((h.v & 1) << 17)) & PDP1_MASK;
        h.v = (h.v & PDP1_SIGN) | (h.v >> 1);
    }
}
/* Multiply step `mus m` on a machine without the multiply/divide option. */
static inline void mus(word &h, word &l, word m) {
    pdp1_bits ac = h.v;
    if (l.v & 1) {
        ac += m.v;
        if (ac > PDP1_MASK) ac = (ac + 1) & PDP1_MASK;
    }
    l.v = (l.v >> 1) | ((ac & 1) << 17);
    h.v = ac >> 1;
}
/* Divide step `dis m` on a machine without the multiply/divide option. */
static inline void dis(word &h, word &l, word m) {
    pdp1_bits t = h.v >> 17;
    pdp1_bits ac = ((h.v << 1) | (l.v >> 17)) & PDP1_MASK;
    l.v = ((l.v << 1) | (t ^ 1)) & PDP1_MASK;
    ac = (l.v & 1) ? ac + (m.v ^ PDP1_MASK) : ac + m.v + 1;
    if (ac > PDP1_MASK) ac = (ac + 1) & PDP1_MASK;
    if (ac == PDP1_MASK) ac = 0;
    h.v = ac;
}

/* Words the current call returns past beyond its inline parameters. The
 * reference driver clears it before a call and reads it after. */
static int pdp1_skips;
static inline void skip_return() { ++pdp1_skips; }

/* Hardware. The typewriter buffer holds what was last typed (nothing, in a
 * reference run); sequence break mode is a flag. */
static word pdp1_typewriter;
static bool pdp1_break_mode;
static inline word tyi() { return pdp1_typewriter; }
static inline void lsm() { pdp1_break_mode = false; }

#else
#error "pdp1.h: compile with g++ (executable reference) or pdp1cc"
#endif

#endif /* PDP1_H */
