# sin and cos: C to listing words (source 190-254, listing 00066-00155)

Pool order check (L3): the literals first appear in this order in the emitted
text: 62210 (cos), 311040, 242763, 756103, 121312, 532511, 144417, 377777, and
then `1` from sqt. The oracle pool at 02767.. holds exactly that sequence.
That works because cosine is laid out before sine, as in the original.

<!-- range 00066-00155 -->

| addr | word | lowered | origin (C statement, rule) |
|---|---|---|---|
| 00066 | 000000 | 0 | cosine: entry cell |
| 00067 | 260142 | dap csx | prologue of a forwarding function: stores the return address into the *callee's* link cell (C6) |
| 00070 | 202767 | lac (62210 | `HALF_PI + x`: neither operand is a small immediate, so source order; constant is a pool literal (S3, S2, L3) |
| 00071 | 400066 | add cos | `+ x`, x is the entry cell (C1, S3) |
| 00072 | 240074 | dac sin | tail call: argument stored straight into sine's entry cell instead of `jda` (C6) |
| 00073 | 600077 | jmp .+4 | tail call: jump to sine's fast entry, the instruction after its `lac x` (C6) |
| 00074 | 000000 | 0 | sine: entry cell, param `x` |
| 00075 | 260142 | dap csx | prologue; csx is sine's own return cell (C1) |
| 00076 | 200074 | lac sin | `word a = x;` a is AC-resident; fast entry label follows (A1, C6) |
| 00077 | 640200 | spa | `if (a < 0)` with a one-word body: skip folded, no jump (S6) |
| 00100 | 402770 | add (311040 | label si1; `a += TWO_PI` (S3) |
| 00101 | 422767 | sub (62210 | `a -= HALF_PI` (S3, L3 reuses the pool word) |
| 00102 | 640400 | sma | `if (a >= 0) goto si2;` (S6) |
| 00103 | 600143 | jmp si2 | |
| 00104 | 402767 | add (62210 | `a += HALF_PI` |
| 00105 | 661003 | ral 2s | label si3; `a = ral(a, 2)` (S8) |
| 00106 | 170171 | jda mpy | `a = mpy(a, 0242763)`: arg0 is already in AC (C1) |
| 00107 | 202771 | lac (242763 | inline operand: call site emits the one-word fetch for arg1 (C4) |
| 00110 | 240074 | dac sin | `x = a;` (S5) |
| 00111 | 170171 | jda mpy | `a = mpy(a, x)`; AC cache says AC = x = a, so arg0 costs nothing (S4) |
| 00112 | 200074 | lac sin | inline operand for `x` (C4) |
| 00113 | 240066 | dac cos | `C = a;` C is `ENTRY(cosine)`, an ordinary cell here |
| 00114 | 170171 | jda mpy | `mpy(a, 0756103)`, AC cache holds a |
| 00115 | 202772 | lac (756103 | (C4) |
| 00116 | 402773 | add (121312 | `+ 0121312` (S3) |
| 00117 | 170171 | jda mpy | `a = mpy(a, C) + 0532511` |
| 00120 | 200066 | lac cos | (C4) |
| 00121 | 402774 | add (532511 | |
| 00122 | 170171 | jda mpy | `a = mpy(a, C) + 0144417` |
| 00123 | 200066 | lac cos | |
| 00124 | 402775 | add (144417 | |
| 00125 | 170171 | jda mpy | `a = mpy(a, x)` |
| 00126 | 200074 | lac sin | |
| 00127 | 667007 | scl 3s | `a = scl(a, 3)`; reads IO left by mpy (S8) |
| 00130 | 240066 | dac cos | `C = a;` |
| 00131 | 060074 | xor sin | `(a ^ x)` (S3) |
| 00132 | 640400 | sma | `if ((a ^ x) < 0) {`: skip when the block is entered, then jump over it (S6) |
| 00133 | 600141 | jmp csx-1 | else edge = the `return C;` statement, i.e. the word before the return cell (C3) |
| 00134 | 202776 | lac (377777 | `word sat = 0377777;` AC-resident (A1) |
| 00135 | 220074 | lio sin | `IO = x;` does not disturb AC (A2) |
| 00136 | 642000 | spi | `if (IO < 0) sat = ~sat;` folded (S6) |
| 00137 | 761000 | cma | |
| 00140 | 600142 | jmp csx | `return sat;` value already in AC; jump to the return cell (C5) |
| 00141 | 200066 | lac cos | `return C;` (C5) |
| 00142 | 600142 | jmp . | return cell csx, after the last return (C3) |
| 00143 | 761000 | cma | label si2; `a = ~a;` |
| 00144 | 402767 | add (62210 | |
| 00145 | 640400 | sma | `if (a >= 0) goto si3;` |
| 00146 | 600105 | jmp si3 | |
| 00147 | 402767 | add (62210 | |
| 00150 | 640200 | spa | `if (a < 0) goto si4;` skip when it falls through |
| 00151 | 600154 | jmp .+3 | si4 |
| 00152 | 422767 | sub (62210 | |
| 00153 | 600105 | jmp si3 | `goto si3;` |
| 00154 | 422767 | sub (62210 | label si4 |
| 00155 | 600100 | jmp si1 | `goto si1;` jumps into the body of the `if`, legal C |

All 56 words reproduced.

What makes cos work without a special case: C6 (link forwarding plus fast
entry) is a general tail-call lowering for `jda` callees, and `ENTRY(f)` makes
the shared-cell aliasing explicit in C. What must exist in the compiler for it:
the callee's fast-entry address is "the instruction after the first load of the
parameter into an AC-resident local", recorded when sine is compiled. The
compiler compiles sine first (dependency order) and cosine's lowering reads
that record. Layout order stays source order.
