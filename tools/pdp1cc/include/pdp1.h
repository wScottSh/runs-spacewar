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
 * AC:IO, or IO alone for an `io_word`). XCT: a function that is one
 * instruction, executed in place by `xct f`; its plain parameter is AC and
 * its register parameter IO. A pointer to a function type is a word holding
 * its address; `return p(...)` jumps through it, and `((f *)w)()` calls the
 * JSP function whose address is in w's address field (`dap L / L, jsp .`).
 * A BLOCK may tail-call several BLOCKs; it then has no exit of its own to
 * share. A function's name used as a value is its address.
 * ENTRY_CELL(f) names f's entry word; several names may share it.
 * START on a BLOCK function with no parameters makes it where the tape
 * starts the program: the tape ends with a jump to it. AT(a) lays a definition out
 * from address a. RESERVE sets aside the words of an uninitialized object
 * where it is defined; they are not punched, so the machine leaves whatever
 * core held there. MINUS_ZERO is the word with every bit set.
 *
 * Hardware builtins: tyi() reads the typewriter into IO; lat() reads the
 * test word switches into AC; control_boxes() reads the control boxes into
 * IO (iot 11); halt(ac, io) halts with ac and io on the console lights;
 * lsm() leaves sequence break mode; stf(n) and clf(n) set and clear program flag n, and
 * flag(n) tests it; sense(n) tests sense switch n. dpy(x, y, n) plots the
 * point (x, y) at intensity n without waiting; x is AC and y is IO, and
 * both keep their values. dpy_nowait(x, y) plots at intensity 0 and asks
 * the display for a completion pulse, which ioh() waits for. A comma
 * statement whose parts are each one operate-group instruction, writing
 * different registers (`x = 0, y = 0, clf(6);`), is one instruction.
 *
 * Memory. A POOL object is a word macro1 allocates at `variables` (`\x`).
 * CONSTANTS() and VARIABLES() at file scope place the literal constants and
 * the pool words there. a[k] for a file-scope array (or an address a + n in
 * one) and a constant k is the word k past it.
 * A HOMED pointer lives in the address field of one instruction, its home:
 * `*home(p)` is that instruction (`lac .`, `add .` or `sub .` as an operand,
 * `dac .`, `dzm .` or `dio .` as a store), `p = e` stores the address there
 * (dap) and `++p` advances it (idx). `p + n` for a HOMED p is arithmetic on
 * its home word, whose address field is p, so only a dap may store it. A
 * HOMED pointer declared extern has its home in other text. `x.addr = e` stores e's address bits into
 * word x (dap). `*p++ = e` stores through a pointer and advances it.
 * `*p` reads or writes the word p points to, for p held in memory or in a
 * homed address field: the instruction names p with the indirect bit.
 * A function's name used as a value is its address; `f | (word)c` with c's
 * bits above the address field is that address with flags set.
 * PLACE(x, ...) lays file-scope words out where the statement stands
 * instead of at their definition; control must not reach it. An INLINE
 * parameter is a constant word after the call, read as `lac i` through
 * the return address. ARGS_DONE() marks where a function with inline
 * words steps its return address past them. SKIPNOT(c), for a sign test c
 * of AC, skips when c fails on c's own skip with the i bit flipped (`spa i`
 * for `sma`). SWAP(x) moves x between AC and IO with the `swap` turn,
 * rcl 9s twice, where the default turns rcr.
 *
 * Instruction words. An `insn` is a word that holds an instruction. The
 * I_* constructors build one: I_LAC(&x) is the word `lac x`, I_JMP(f) is
 * `jmp f`, I_STF(n) is `stf n`; I_LIO(0) names address 0. For a HOMED
 * pointer p, I_LIO(p) is its home instruction word when that is `lio .`.
 * Code generated at run time is these words written to memory and entered
 * by a jump; nothing in this header executes such code.
 *
 * Shifts. A `shift` is a shift instruction: I_RCL(n) is `rcl ns`, and
 * I_RCL_BITS(m) is `rcl` by as many places as the mask m has bits set
 * (`m | (rcl`); m is `w & c` with c within 0777. SHIFT_UNSET is the `hlt`
 * a shift slot holds before the program first builds its shift. A shift
 * stored where an insn is wanted is its instruction word. A shift is the
 * one instruction that may be executed: xct(s, a) runs s on AC, xct(s, hi,
 * lo) on AC:IO. s is a constructor (`xct (s`), *home(p) for a HOMED
 * pointer p to a shift (`p, xct .`), or a HOMED shift. A HOMED shift is
 * the instruction at its home, which is its xct: it runs where it stands,
 * `x = e` stores the whole word there, and its initializer is the word it
 * holds first. Only a shift is stored in a shift.
 * `switch ((int)w)` over cases 0..n is a jump table indexed by w; a value
 * outside 0..n is undefined, as on the machine. When w is a HOMED word the
 * switch is Duff's device: the switch is w's home, the jump into the cases,
 * and `w = e` stores the address of case e there.
 *
 * A static inline function is laid out at each call.
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
typedef word insn;
typedef word shift;
typedef struct dword { word hi, lo; } dword;
#define JDA __attribute__((pdp1_jda))
#define BLOCK __attribute__((pdp1_block))
#define BYNAME __attribute__((pdp1_byname))
#define SKIPS __attribute__((pdp1_skips))
#define START __attribute__((pdp1_start))
#define ENTRY_CELL(f) __attribute__((pdp1_entry_cell(f)))
#define XCT __attribute__((pdp1_xct))
#define JSP __attribute__((pdp1_jsp))
#define AT(a) __attribute__((pdp1_at(a)))
#define RESERVE __attribute__((pdp1_reserve))
#define POOL __attribute__((pdp1_pool))
#define HOMED __attribute__((pdp1_homed))
#define INLINE __attribute__((pdp1_inline))
#define PLACE(...) pdp1_place(__VA_ARGS__)
#define ARGS_DONE() pdp1_args_done()
#define MINUS_ZERO (-(word)0)
word *home(const word *p);
void pdp1_place();
void pdp1_args_done(void);
void stf(int n);
void clf(int n);
int flag(int n);
int sense(int n);
void ioh(void);
void dpy(word x, word y, int intensity);
void dpy_nowait(word x, word y);
insn I_LAC(), I_LIO(), I_DAC(), I_DIO(), I_ADD(), I_SUB(), I_AND(), I_XOR(), I_JMP(), I_IDX();
insn I_STF(int n), I_CLF(int n), I_SZF(int n);
shift I_RCL(int n), I_RAL(int n), I_SCL(int n), I_SCR(int n), I_SAR(int n);
shift I_RCL_BITS(word m), I_RAL_BITS(word m), I_SCL_BITS(word m), I_SCR_BITS(word m),
    I_SAR_BITS(word m);
extern const shift SHIFT_UNSET;
extern const insn I_CMA, I_IOH, I_DPY_NOWAIT;
dword xct();
word tyi(void);
void lsm(void);
void hlt(void);
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
typedef word io_word;
#define SKIPNOT(c) pdp1_skipnot(c)
#define SWAP(x) pdp1_swap(x)
#define CONSTANTS() extern void pdp1_constants(void)
#define VARIABLES() extern void pdp1_variables(void)
int pdp1_skipnot(int c);
word pdp1_swap(word x);
insn I_DZM();
word lat(void);
word control_boxes(void);
void halt(word ac, word io);

#elif defined(__cplusplus)

#include <cstdint>
#include <cstdlib>
#include <type_traits>
#include <vector>

#define JDA
#define BLOCK
#define BYNAME
#define SKIPS
#define START
#define ENTRY_CELL(f)
#define XCT
#define JSP
#define AT(a)
#define RESERVE
#define POOL
#define HOMED
#define INLINE
#define PLACE(...)
#define ARGS_DONE()
#define MINUS_ZERO (-(word)0)

typedef std::uint32_t pdp1_bits;
static const pdp1_bits PDP1_MASK = (1u << 18) - 1;
static const pdp1_bits PDP1_SIGN = 1u << 17;
static const pdp1_bits PDP1_ADDR = (1u << 12) - 1;

/* Where the C objects are in core. Instruction words name addresses, so
 * the reference build supplies the table from the assembled listing:
 * each entry is a C object (or function), how many words it spans, and
 * the address of its first word. */
struct pdp1_symbol { const void *at; unsigned words; unsigned address; bool code; };
extern const pdp1_symbol pdp1_symbols[];
extern const unsigned pdp1_symbol_count;

static inline unsigned pdp1_address(const void *p) {
    if (p == nullptr)                   /* a pointer word that holds 0 */
        return 0;
    const char *c = static_cast<const char *>(p);
    for (unsigned past = 0; past <= 1; ++past)     /* inside an object, else just past one */
        for (unsigned k = 0; k < pdp1_symbol_count; ++k) {
            const char *at = static_cast<const char *>(pdp1_symbols[k].at);
            if (c >= at && c < at + (pdp1_symbols[k].words + past) * sizeof(pdp1_bits))
                return (pdp1_symbols[k].address + (unsigned)(c - at) / sizeof(pdp1_bits)) & PDP1_ADDR;
        }
    std::abort();                       /* an object the listing does not place */
}
template <class F> static inline unsigned pdp1_address(F *f) {
    return pdp1_address(reinterpret_cast<const void *>(f));
}

/* The function whose entry is at an address: a call through a word that
 * holds it, as `dap L / L, jsp .` calls through the word's address field. */
static inline const void *pdp1_code(unsigned a) {
    for (unsigned k = 0; k < pdp1_symbol_count; ++k)
        if (pdp1_symbols[k].code && pdp1_symbols[k].address == a)
            return pdp1_symbols[k].at;
    std::abort();                       /* no function starts there */
}

/* The address bits of a word: storing a pointer here is `dap`. */
struct pdp1_address_field {
    pdp1_bits v;
    template <class T> pdp1_address_field &operator=(T *p) {
        v = (v & ~PDP1_ADDR) | pdp1_address(p);
        return *this;
    }
    pdp1_address_field &operator=(int a) {          /* an address given as a number */
        v = (v & ~PDP1_ADDR) | ((pdp1_bits)a & PDP1_ADDR);
        return *this;
    }
    template <class W> auto operator=(const W &w) -> decltype((void)w.v, *this) {   /* a word's address bits */
        v = (v & ~PDP1_ADDR) | (w.v & PDP1_ADDR);
        return *this;
    }
};

struct word {
    union { pdp1_bits v; pdp1_address_field addr; };
    word() : v(0) {}
    word(int i) : v((i < 0 ? ~(pdp1_bits)(-i) : (pdp1_bits)i) & PDP1_MASK) {
        if (i > (int)PDP1_MASK || -i > (int)PDP1_MASK) std::abort();
    }
    static word bits(pdp1_bits b) { word w; w.v = b & PDP1_MASK; return w; }
    template <class R, class... A> word(R (*f)(A...)) : v(pdp1_address(f)) {}  /* a function's address */

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
    explicit operator int() const { return (int)v; }    /* a jump table index */
    /* (f *)w: the function at the address in w's address field. */
    template <class F, class = typename std::enable_if<std::is_function<F>::value>::type>
    explicit operator F *() const { return reinterpret_cast<F *>(const_cast<void *>(pdp1_code(v & PDP1_ADDR))); }
};
typedef word insn;

/* The word the machine holds: a pointer is the address it points to. */
static inline pdp1_bits pdp1_value(word w) { return w.v; }
template <class T> static inline pdp1_bits pdp1_value(T *p) { return pdp1_address(p); }

/* The C object at an address, for a pointer the caller passes as a word. */
static inline word *pdp1_pointer(pdp1_bits a) {
    for (unsigned k = 0; k < pdp1_symbol_count; ++k) {
        const pdp1_symbol &s = pdp1_symbols[k];
        if (a >= s.address && a < s.address + s.words)
            return (word *)const_cast<void *>(s.at) + (a - s.address);
    }
    std::abort();
}

/* p + w: the address p names plus the word w, as `law p / add w` adds them. */
static inline word *operator+(word *p, word w) {
    return pdp1_pointer((word::bits(pdp1_address(p)) + w).v & PDP1_ADDR);
}

template <class T> static inline T *home(T *p) { return p; }

/* Instruction words, encoded as the machine encodes them. A memory
 * reference instruction is a 5-bit operation in the high bits and an
 * address; the operate, skip and shift groups add microcoded bits. */
static inline insn pdp1_insn(pdp1_bits op, pdp1_bits low) { return word::bits(op << 12 | low); }
#define PDP1_MRI(name, op) \
    template <class T> static inline insn name(T *p) { return pdp1_insn(op, pdp1_address(p)); } \
    static inline insn name(decltype(nullptr)) { return pdp1_insn(op, 0); }
PDP1_MRI(I_AND, 002) PDP1_MRI(I_XOR, 006) PDP1_MRI(I_LAC, 020) PDP1_MRI(I_LIO, 022)
PDP1_MRI(I_DAC, 024) PDP1_MRI(I_DIO, 032) PDP1_MRI(I_ADD, 040) PDP1_MRI(I_SUB, 042)
PDP1_MRI(I_IDX, 044) PDP1_MRI(I_JMP, 060) PDP1_MRI(I_DZM, 034)
#undef PDP1_MRI
static const pdp1_bits PDP1_OPR = 076, PDP1_SKP = 064, PDP1_SHIFT = 066, PDP1_IOT = 072;
static const pdp1_bits PDP1_I = 1u << 12;           /* the indirect (or IOT wait) bit */
static inline insn I_STF(int n) { return pdp1_insn(PDP1_OPR, 010 | (n & 7)); }
static inline insn I_CLF(int n) { return pdp1_insn(PDP1_OPR, n & 7); }
static inline insn I_SZF(int n) { return pdp1_insn(PDP1_SKP, n & 7); }

/* A shift instruction as a value: what it does and its count field. The
 * constructors build it, xct runs it by its kind, and storing it where an
 * insn is wanted encodes it. */
enum class pdp1_shift_kind : std::uint16_t {    /* each named by its field in the word */
    unset = 0, ral = 01, rcl = 03, scl = 07, sar = 015, scr = 017
};
struct shift {
    pdp1_shift_kind kind;
    std::uint16_t count_bits;           /* shifts as many places as bits set */
    operator word() const {             /* the instruction word */
        if (kind == pdp1_shift_kind::unset)
            return word::bits(PDP1_OPR << 12 | 0400);                   /* hlt */
        return pdp1_insn(PDP1_SHIFT, (pdp1_bits)kind << 9 | count_bits);
    }
};
/* A shift array is laid out one word per shift. */
static_assert(sizeof(shift) == sizeof(pdp1_bits), "shift is one word");
static const shift SHIFT_UNSET = {pdp1_shift_kind::unset, 0};
static inline shift pdp1_shift(pdp1_shift_kind kind, int n) {
    if (n < 0 || n > 9) std::abort();               /* one instruction shifts 0..9 */
    return shift{kind, (std::uint16_t)((1u << n) - 1)};
}
static inline shift pdp1_shift_bits(pdp1_shift_kind kind, word m) {
    if (m.v & ~0777u) std::abort();                 /* the count field is nine bits */
    return shift{kind, (std::uint16_t)m.v};
}
#define PDP1_SHIFT_CONSTRUCTORS(name, kind) \
    static inline shift name(int n) { return pdp1_shift(pdp1_shift_kind::kind, n); } \
    static inline shift name##_BITS(word m) { return pdp1_shift_bits(pdp1_shift_kind::kind, m); }
PDP1_SHIFT_CONSTRUCTORS(I_RAL, ral) PDP1_SHIFT_CONSTRUCTORS(I_RCL, rcl)
PDP1_SHIFT_CONSTRUCTORS(I_SCL, scl) PDP1_SHIFT_CONSTRUCTORS(I_SAR, sar)
PDP1_SHIFT_CONSTRUCTORS(I_SCR, scr)
#undef PDP1_SHIFT_CONSTRUCTORS
static const insn I_CMA = word::bits(PDP1_OPR << 12 | 01000);
static const insn I_IOH = word::bits(PDP1_IOT << 12 | PDP1_I);     /* iot i: wait for completion */
static const insn I_DPY_NOWAIT = word::bits((PDP1_IOT << 12 | PDP1_I | 07) - 04000);  /* dpy-4000 */

struct pdp1_point { pdp1_bits instruction, x, y; };
static std::vector<pdp1_point> pdp1_plotted;
static inline void dpy(word x, word y, int intensity) {
    pdp1_plotted.push_back({PDP1_IOT << 12 | 07 | (pdp1_bits)(intensity & 7) << 6, x.v, y.v});
}
static inline void dpy_nowait(word x, word y) { pdp1_plotted.push_back({I_DPY_NOWAIT.v, x.v, y.v}); }
static inline void ioh() {}

static unsigned pdp1_sense_switches;
static inline bool sense(int n) { return (pdp1_sense_switches & (1u << (6 - n))) != 0; }

/* Program flags 1-6; flag 7 names all six. */
static unsigned pdp1_program_flags;
static inline unsigned pdp1_flag_bits(int n) { return n == 7 ? 077u : 1u << (6 - n); }
static inline void stf(int n) { pdp1_program_flags |= pdp1_flag_bits(n); }
static inline void clf(int n) { pdp1_program_flags &= ~pdp1_flag_bits(n); }
static inline bool flag(int n) { return (pdp1_program_flags & pdp1_flag_bits(n)) != 0; }

/* The console and the control boxes. lat() reads the test word switches;
 * control_boxes() is `iot 11`, the MIT control boxes' buttons; halt(ac, io)
 * stops with ac and io on the console lights, until continued. */
static word pdp1_test_word;
static word pdp1_control_boxes;
static inline word lat() { return pdp1_test_word; }
static inline word control_boxes() { return pdp1_control_boxes; }
static inline void halt(word ac, word io) { pdp1_plotted.push_back({PDP1_OPR << 12 | 0400, ac.v, io.v}); }

/* A word returned in IO; SKIPNOT(c) is c; SWAP(x) is x (both choose an
 * encoding only). CONSTANTS() and VARIABLES() place the literal and pool
 * words, which the native build has no place for. */
typedef word io_word;
#define SKIPNOT(c) (c)
#define SWAP(x) (x)
#define CONSTANTS() extern void pdp1_constants(void)
#define VARIABLES() extern void pdp1_variables(void)

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

/* Executing a shift: xct(s, a) runs s on AC, xct(s, hi, lo) on the AC:IO
 * pair. A slot still SHIFT_UNSET holds `hlt`, which stops the run.
 * xct(s, a) takes only a shift of AC. */
static inline void pdp1_xct(shift s, word &h, word &l) {
    int n = __builtin_popcount(s.count_bits);
    switch (s.kind) {
    case pdp1_shift_kind::ral: h = ral(h, n); return;
    case pdp1_shift_kind::sar: h = h >> n; return;
    case pdp1_shift_kind::rcl: rcl(h, l, n); return;
    case pdp1_shift_kind::scl: scl(h, l, n); return;
    case pdp1_shift_kind::scr: scr(h, l, n); return;
    case pdp1_shift_kind::unset: break;
    }
    std::abort();
}
static inline word xct(shift s, word a) {
    if (s.kind != pdp1_shift_kind::ral && s.kind != pdp1_shift_kind::sar)
        std::abort();                   /* the shift reaches IO: use the pair form */
    word io;
    pdp1_xct(s, a, io);
    return a;
}
static inline dword xct(shift s, word hi, word lo) {
    pdp1_xct(s, hi, lo);
    return dword{hi, lo};
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
static inline void hlt() { std::abort(); }      /* the machine stops */

/* A function that is not SKIPS returns to the word after its call, whatever
 * its callees skip: the reference build opens each such definition with a
 * guard that restores pdp1_skips when it returns. */
struct pdp1_skip_guard {
    int saved = pdp1_skips;
    ~pdp1_skip_guard() { pdp1_skips = saved; }
};

#else
#error "pdp1.h: compile with g++ (executable reference) or pdp1cc"
#endif

#endif /* PDP1_H */
