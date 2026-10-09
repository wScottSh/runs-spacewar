# sqt: C to listing words (source 309-343, listing 00246-00305)

Rule ids are defined in `../compiler.md`. Words are machine-checked against
`build/oracle.lst` by `check_trace.py`; the origin column is the hand trace.

<!-- range 00246-00305 -->

| addr | word | lowered | origin (C statement, rule) |
|---|---|---|---|
| 00246 | 000000 | 0 | entry cell = param `x` home (C1) |
| 00247 | 260260 | dap sqx | prologue: AC holds return address, stored in the link cell (C1) |
| 00250 | 710023 | law i 23 | `sq1 = -023;` small negative immediate (S2) |
| 00251 | 240304 | dac sq1 | store to in-stream cell (S5) |
| 00252 | 340305 | dzm sq2 | `sq2 = 0;` zero store (S5) |
| 00253 | 220246 | lio sqt | `IO = x;` IO assignment from memory (S5, A2) |
| 00254 | 340246 | dzm sqt | `x = 0;` param is the entry cell (C1, S5) |
| 00255 | 460304 | isp sq1 | `if (++sq1 >= 0)` label sq3; fused index-and-skip (S6) |
| 00256 | 600261 | jmp .+3 | else edge: first statement after the if-body, which includes the return cell (C3, S6) |
| 00257 | 200305 | lac sq2 | `return sq2;` result to AC (C5, S1) |
| 00260 | 600260 | jmp . | return cell `sqx`, placed after the textually last return (C3) |
| 00261 | 200305 | lac sq2 | `sq2 = sal(sq2, 1);` (S1) |
| 00262 | 665001 | sal 1s | builtin shift, one instruction (S8) |
| 00263 | 240305 | dac sq2 | (S5) |
| 00264 | 200246 | lac sqt | `word r = rcl(x, 2);` r is AC-resident (A1) |
| 00265 | 663003 | rcl 2s | combined rotate; other half stays in IO (S8) |
| 00266 | 650100 | sza i | `if (r == 0) goto sq3;` skip when the fall-through condition holds, i.e. r != 0 (S6) |
| 00267 | 600255 | jmp sq3 | (S6) |
| 00270 | 240246 | dac sqt | `x = r;` AC already holds r, no load (S4) |
| 00271 | 200305 | lac sq2 | `sal(sq2, 1) + 1 - x`: left operand first (S3) |
| 00272 | 665001 | sal 1s | (S8) |
| 00273 | 402777 | add (1 | AC busy, so `+ 1` is an `add` of a pool literal (S2, S3, L3) |
| 00274 | 420246 | sub sqt | `- x` (S3) |
| 00275 | 640500 | szm | `if (r > 0) goto sq3;` skip when r <= 0 is `sma+sza-skip` (S6) |
| 00276 | 600255 | jmp sq3 | |
| 00277 | 640200 | spa | `if (r < 0) r = -r;` single-word body folded into the skip (S6) |
| 00300 | 761000 | cma | `-r` is complement (S3) |
| 00301 | 240246 | dac sqt | `x = r;` |
| 00302 | 440305 | idx sq2 | `sq2++;` statement context, value unused (S7) |
| 00303 | 600255 | jmp sq3 | `goto sq3;` |
| 00304 | 000000 | 0 | `word sq1 = 0` placed in-stream at its defining declaration (L1, L2) |
| 00305 | 000000 | 0 | `sq2` |

All 32 words reproduced. Rules that carried weight here: S6 (condition to
skip), C3 (return cell after the last return), L2 (initialized static is
in-stream). Nothing missing.
