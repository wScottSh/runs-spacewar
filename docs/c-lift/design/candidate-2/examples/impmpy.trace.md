# imp and mpy: C to listing words (source 257-301, listing 00156-00245)

Inline operands: `jda mpy` is followed by one word the callee executes, so the
C signature marks that parameter `inl_insn`. A read of the parameter is `xct`
of the link cell; the first read in layout order is the link cell itself.

<!-- range 00156-00245 -->

| addr | word | lowered | origin (C statement, rule) |
|---|---|---|---|
| 00156 | 000000 | 0 | imp: entry cell = param `a` (C1) |
| 00157 | 260160 | dap im1 | prologue; the link cell kind is `xct` because the function has an `inl_insn` parameter (C1, C3) |
| 00160 | 100000 | xct | `mpy(b, a)`: first read of `b` places the link cell here; executing it runs the caller's inline instruction, AC = B (C3, C4) |
| 00161 | 170171 | jda mpy | call, arg0 (the value of `b`) in AC (C1) |
| 00162 | 200156 | lac imp | inline operand for arg1 `a`, which is the entry cell: the call site emits `lac <operand>` (C4) |
| 00163 | 440160 | idx im1 | `skip_inline(1);` advance the link past the caller's inline word (C4) |
| 00164 | 672001 | rir 1s | `IO = rir(IO, 1);` one instruction on IO, AC untouched (S8, A2) |
| 00165 | 673777 | rcr 9s | `rcr(ANY(), 18)`: count 18 splits into 9+9; ANY loads nothing (S8) |
| 00166 | 673777 | rcr 9s |  |
| 00167 | 610160 | jmp i im1 | `return`: xct-kind link returns through the cursor, `jmp i` (C5) |
| 00170 | 000000 | 0 | `static word mp2 = 0;` in-stream (L1, L2) |
| 00171 | 000000 | 0 | mpy: entry cell = param `a` |
| 00172 | 260200 | dap mp1 | prologue (C1, C3) |
| 00173 | 200171 | lac mpy | `word m = a;` m is AC-resident (A1) |
| 00174 | 640200 | spa | `if (m < 0) m = ~m;` folded (S6) |
| 00175 | 761000 | cma |  |
| 00176 | 673777 | rcr 9s | `(void)rcr(m, 18);` IO := |a|, AC garbage (S8) |
| 00177 | 673777 | rcr 9s |  |
| 00200 | 100000 | xct | `word n = b;` first read of `b`: link cell placed here (C3, C4) |
| 00201 | 640200 | spa | `if (n < 0) n = ~n;` |
| 00202 | 761000 | cma |  |
| 00203 | 240170 | dac mp2 | `mp2 = n;` (S5) |
| 00204 | 760200 | cla | `word acc = 0;` zero into AC (S2) |
| 00205 | 540170 | mus mp2 | `PDP1_UNROLL for (i < 017) acc = mus(acc, mp2);` iteration 1 of 17; the loop variable has no cell (S10) |
| 00206 | 540170 | mus mp2 | iteration 2 |
| 00207 | 540170 | mus mp2 | iteration 3 |
| 00210 | 540170 | mus mp2 | iteration 4 |
| 00211 | 540170 | mus mp2 | iteration 5 |
| 00212 | 540170 | mus mp2 | iteration 6 |
| 00213 | 540170 | mus mp2 | iteration 7 |
| 00214 | 540170 | mus mp2 | iteration 8 |
| 00215 | 540170 | mus mp2 | iteration 9 |
| 00216 | 540170 | mus mp2 | iteration 10 |
| 00217 | 540170 | mus mp2 | iteration 11 |
| 00220 | 540170 | mus mp2 | iteration 12 |
| 00221 | 540170 | mus mp2 | iteration 13 |
| 00222 | 540170 | mus mp2 | iteration 14 |
| 00223 | 540170 | mus mp2 | iteration 15 |
| 00224 | 540170 | mus mp2 | iteration 16 |
| 00225 | 540170 | mus mp2 | iteration 17 |
| 00226 | 240170 | dac mp2 | `mp2 = acc;` |
| 00227 | 100200 | xct mp1 | `(b ^ a)`: second read of `b` executes the link cell, which executes the inline word again (C4) |
| 00230 | 060171 | xor mpy | `^ a` (S3) |
| 00231 | 640400 | sma | `if ((b ^ a) >= 0) goto mp3;` (S6) |
| 00232 | 600243 | jmp mp3 |  |
| 00233 | 200170 | lac mp2 | `word p = mp2;` AC was clobbered by the xct, so this load is needed (S4) |
| 00234 | 761000 | cma | `p = ~p;` |
| 00235 | 673777 | rcr 9s | `p = rcr(p, 18);` |
| 00236 | 673777 | rcr 9s |  |
| 00237 | 761000 | cma |  |
| 00240 | 673777 | rcr 9s |  |
| 00241 | 673777 | rcr 9s |  |
| 00242 | 240170 | dac mp2 | `mp2 = p;` |
| 00243 | 440200 | idx mp1 | label mp3; `skip_inline(1);` (C4) |
| 00244 | 200170 | lac mp2 | `return mp2;` |
| 00245 | 610200 | jmp i mp1 | (C5) |

All 56 words reproduced.

Honest note on what is *not* automatic: `(void)rcr(m, 18)` and
`rcr(ANY(), 18)` keep the author's choice of `rcr` over the macro `swap`
(`rcl`). Both are the same function of (AC, IO); the C names the instruction
the original used. A compiler that "normalized" them would break the hash, so
the dialect keeps rotate-left and rotate-right as distinct builtins.
