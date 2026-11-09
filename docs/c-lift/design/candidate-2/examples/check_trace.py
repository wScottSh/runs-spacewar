#!/usr/bin/env python3
"""check_trace.py -- machine-check the hand traces in *.trace.md.

Each trace row is   | ADDR | WORD | MNEMONIC | ORIGIN |
The checker (1) assembles MNEMONIC with a tiny independent Macro-subset
assembler, using symbol values and the literal pool read from
build/oracle.lst, and (2) requires  assembled == WORD == the word the oracle
listing holds at ADDR.  It proves each row's text, word, and address agree
with the oracle.  It does NOT prove the lowering rules produced the row; that
is what the hand trace beside it argues, and what the compiler's rule-hit
report checks once the compiler exists.

usage: check_trace.py [--fill] FILE...     (--fill rewrites ?????? words)
"""
import re, sys, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
LST = os.path.join(ROOT, "build/oracle.lst")

def load_lst():
    words, syms = {}, {}
    insym = False
    for ln in open(LST):
        ln = ln.rstrip("\n")
        if "Symbol Table" in ln:
            insym = True
            continue
        if insym:
            m = re.match(r"^\s*(\S+)\s+([0-7]{6})\s*$", ln)
            if m:
                syms[m.group(1)] = int(m.group(2), 8)
            continue
        for m in re.finditer(r"(?:^|\s)([0-7]{5}) ([0-7]{6})(?=\s|$)", ln[:24]):
            words[int(m.group(1), 8)] = int(m.group(2), 8)
    return words, syms

OPS = {  # memory-reference: opcode<<13 (indirect adds 010000)
 'and':0o010000*0+0o20000, 'ior':0o40000, 'xor':0o60000, 'xct':0o100000,
 'jda':0o170000, 'lac':0o200000, 'lio':0o220000, 'dac':0o240000, 'dap':0o260000,
 'dip':0o300000, 'dio':0o320000, 'dzm':0o340000, 'add':0o400000, 'sub':0o420000,
 'idx':0o440000, 'isp':0o460000, 'sad':0o500000, 'sas':0o520000, 'mus':0o540000,
 'jmp':0o600000, 'jsp':0o620000, 'law':0o700000,
}
FIXED = {  # whole words / microinstructions
 'opr':0o760000,'cla':0o760200,'cma':0o761000,'hlt':0o760400,'cli':0o764000,
 'lat':0o762200,'spa':0o640200,'sma':0o640400,'sza':0o640100,'spi':0o642000,
 'szm':0o640500,'spq':0o650500,'ioh':0o730000,'tyi':0o720004,'lsm':0o720054,
 'dpy':0o730007,
}
SHIFT = {'ral':0o661000,'ril':0o662000,'rcl':0o663000,'sal':0o665000,'sil':0o666000,
         'scl':0o667000,'rar':0o671000,'rir':0o672000,'rcr':0o673000,'sar':0o675000,
         'sir':0o676000,'scr':0o677000}

class Asm:
    def __init__(self, words, syms):
        self.words, self.syms = words, syms
    def val(self, tok, dot):
        if tok == '.': return dot
        if re.fullmatch(r"[0-7]+", tok): return int(tok, 8)
        t = tok.lstrip('\\')
        if t in self.syms: return self.syms[t]
        raise KeyError(tok)
    def expr(self, s, dot):
        """sum of terms; space or + adds, - subtracts; handles leading instruction"""
        s = s.strip()
        m = re.match(r"^([a-z]{3})\b\s*(i\b)?\s*(.*)$", s)
        if m and (m.group(1) in OPS or m.group(1) in SHIFT or m.group(1) in FIXED
                  or m.group(1) in ('stf','clf','szf','szs','iot')):
            return self.insn(s, dot)
        total, sign = 0, 1
        for tk in re.findall(r"[-+]|[^\s+-]+", s):
            if tk == '+': sign = 1
            elif tk == '-': sign = -1
            else:
                total += sign * self.val(tk, dot); sign = 1
        if total < 0: total = 0o777777 - (-total)
        return total & 0o777777
    def insn(self, s, dot):
        s = s.strip()
        m = re.match(r"^(\S+)\s*(.*)$", s)
        op, rest = m.group(1), m.group(2).strip()
        ind = False
        mi = re.match(r"^i\b\s*(.*)$", rest)
        if mi: ind, rest = True, mi.group(1).strip()
        adj = 0
        mm = re.match(r"^([a-z]{3})([-+][0-7]+)$", op)
        if mm: op = mm.group(1); adj = int(mm.group(2), 8)
        if op in OPS:
            if op == 'law':
                v = self.expr(rest, dot) & 0o7777
                return (OPS['law'] | (0o10000 if ind else 0) | v) + adj
            base = OPS[op] | (0o10000 if ind else 0)
            if rest.startswith('('):
                lit = self.expr(rest[1:], dot)
                addrs = [a for a, w in self.words.items() if w == lit and 0o2767 <= a <= 0o3112]
                if not addrs: raise KeyError("literal not in pool: " + rest)
                y = min(addrs)
            elif rest == '':
                y = 0
            else:
                y = self.expr(rest, dot) & 0o7777
            return (base | y) + adj
        if op in SHIFT:
            n = int(rest.rstrip('s'))
            return SHIFT[op] | ((1 << n) - 1)
        if op in ('stf','clf','szf','szs','iot'):
            n = int(rest.rstrip('s') or 0, 8)
            if op == 'stf': return 0o760010 | n
            if op == 'clf': return 0o760000 | n
            if op == 'szf': return (0o650000 if ind else 0o640000) | n
            if op == 'szs': return 0o640000 | (n << 3)
            if op == 'iot': return 0o720000 | n
        if op in FIXED:
            base = FIXED[op]
            if ind: base |= 0o10000
            return base + adj
        raise KeyError(s)
    def asm(self, mn, dot):
        mn = mn.strip()
        if re.fullmatch(r"[0-7]{1,6}", mn): return int(mn, 8)
        return self.expr(mn, dot)

def main():
    args = sys.argv[1:]
    fill = '--fill' in args
    files = [a for a in args if not a.startswith('--')]
    words, syms = load_lst()
    A = Asm(words, syms)
    bad = ok = 0
    for f in files:
        out = []
        rng = None; seen = set()
        for ln in open(f):
            mr = re.match(r"^<!-- range ([0-7]{5})-([0-7]{5}) -->", ln)
            if mr: rng = (int(mr.group(1), 8), int(mr.group(2), 8))
            m = re.match(r"^\| ([0-7]{5}) \| ([0-7?]{6}) \| (.*?) \| (.*)\|\s*$", ln.rstrip("\n"))
            if not m:
                out.append(ln); continue
            addr = int(m.group(1), 8); seen.add(addr); wtxt = m.group(2); mn = m.group(3).strip()
            mn_clean = mn.replace('`', '')
            try:
                got = A.asm(re.sub(r"\s*\[.*\]$", "", mn_clean), addr)
            except Exception as e:
                print(f"{f}: {m.group(1)} cannot assemble '{mn}': {e}"); bad += 1; out.append(ln); continue
            want = words.get(addr)
            if want is None:
                print(f"{f}: {m.group(1)} not in listing"); bad += 1
            elif got != want:
                print(f"{f}: {m.group(1)} '{mn}' assembles to {got:06o}, oracle has {want:06o}"); bad += 1
            elif '?' not in wtxt and int(wtxt, 8) != want:
                print(f"{f}: {m.group(1)} word column {wtxt} != oracle {want:06o}"); bad += 1
            else:
                ok += 1
                if fill and '?' in wtxt:
                    ln = ln.replace(f"| {wtxt} |", f"| {want:06o} |", 1)
            out.append(ln)
        if rng:
            miss = [a for a in range(rng[0], rng[1] + 1) if a not in seen]
            if miss:
                print(f"{f}: range gaps: {' '.join('%05o' % a for a in miss)}"); bad += 1
        if fill:
            open(f, 'w').write(''.join(out))
    print(f"rows ok: {ok}, bad: {bad}")
    sys.exit(1 if bad else 0)

main()
