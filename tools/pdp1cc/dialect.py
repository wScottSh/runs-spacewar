"""C AST -> IR. Resolves every name to a Storage from its declaration and
rejects anything outside the dialect with a message naming the construct."""
from __future__ import annotations

import re
from dataclasses import replace

from pycparser import c_ast, c_generator

from . import ir, macro

PAIR_SHIFTS = {"rcl", "rcr", "scl", "scr"}
PAIR_STEPS = {"mus", "dis"}
BIN_OPS = {"+", "-", "&", "|", "^"}
MACRO_SYMBOL_LEN = 6
CMP_OPS = {"<", ">=", "==", "!=", "<=", ">"}
ATTR = re.compile(r"pdp1_(\w+)(?:\((.*)\))?$")
CONVS = {c.value: c for c in ir.Conv if c is not ir.Conv.INLINE}
ATTRIBUTES = CONVS.keys() | {"byname", "inline", "sym", "entry_cell", "at", "reserve", "pool", "homed",
                              "skips"}
HARDWARE = {"tyi", "lsm", "ioh", "hlt", "lat", "control_boxes"}   # one instruction, no operand
DISPLAY = {"dpy", "dpy_nowait"}
MAX_SENSE = 6
MAX_INTENSITY = 7
REGION_BREAK = "pdp1_region_break"
DIRECTIVES = {"pdp1_constants": "constants", "pdp1_variables": "variables"}
WORD_TYPES = {"word", "insn"}       # an insn is a word that holds an instruction
FLAG_OPS = {"stf", "clf"}
# Instruction-word constructors: an I_* name, its mnemonic, and its operand.
INSN_MEMORY = {f"I_{m.upper()}": m for m in
               ("lac", "lio", "dac", "dio", "add", "sub", "and", "xor", "jmp", "idx", "dzm")}
INSN_FLAG = {"I_STF": "stf", "I_CLF": "clf", "I_SZF": "szf"}
INSN_SHIFT = {"I_RCL": "rcl", "I_RAL": "ral", "I_SCL": "scl", "I_SCR": "scr", "I_SAR": "sar"}
# I_SCL_BITS(w & m): `scl` by as many places as w & m has bits set, m within the count field.
INSN_SHIFT_BITS = {f"{name}_BITS": op for name, op in INSN_SHIFT.items()}
SHIFT_UNSET = "SHIFT_UNSET"
INSN_CONSTANT = {"I_CMA": ir.Insn("cma"), SHIFT_UNSET: ir.Insn("hlt"),
                 "I_IOH": ir.Insn("iot", None, True),         # ioh: iot i, wait for completion
                 "I_DPY_NOWAIT": ir.Insn(ir.DPY_NOWAIT)}
MAX_FLAG = 7                        # flag 7 names all six program flags
MAX_INSN_SHIFT = 9                  # one shift instruction moves 0..9 places
SHIFT_COUNT_FIELD = 0o777
# A shift object's declarator: a shift, a pointer to one, an array of them, a function returning one.
SHIFT, SHIFT_POINTER, SHIFT_ARRAY, SHIFT_FUNCTION = "shift", "shift*", "shift[]", "shift()"
MACRO_SYMBOL = re.compile(r"[a-z][a-z0-9]{0,%d}" % (MACRO_SYMBOL_LEN - 1))


class DialectError(Exception):
    pass


def _err(node: c_ast.Node, msg: str) -> DialectError:
    where = f"{node.coord}: " if node is not None and node.coord else ""
    return DialectError(where + msg)


def _attrs(decl: c_ast.Decl) -> dict[str, str]:
    """The pdp1_* attributes on a declaration, in any position: name -> argument text."""
    gen = c_generator.CGenerator()
    texts: list[str] = []
    for spec in getattr(decl, "funcspec", None) or []:
        if hasattr(spec, "exprlist"):
            texts.append(gen.visit(spec.exprlist))
    t = decl.type
    while t is not None:
        attrs = getattr(t, "attributes", None)
        if attrs is not None and attrs.exprs:
            texts.append(gen.visit(attrs))
        t = getattr(t, "type", None)
    found: dict[str, str] = {}
    for text in texts:
        for part in re.split(r",\s*(?=pdp1_)", text):
            if m := ATTR.match(part.strip()):
                if m.group(1) not in ATTRIBUTES:
                    raise _err(decl, f"{decl.name}: unknown dialect attribute pdp1_{m.group(1)}")
                found[m.group(1)] = (m.group(2) or "").strip()
    return found


def _in_header(node: c_ast.Node) -> bool:
    """Builtins are declared in pdp1.h; they are lowered by rule, not called."""
    return node.coord is not None and node.coord.file.endswith("pdp1.h")


def _is_function(t: c_ast.Node) -> bool:
    return isinstance(t, c_ast.FuncDecl) or type(t).__name__ == "FuncDeclExt"


def _base_type(t: c_ast.Node) -> str | None:
    if isinstance(t, c_ast.TypeDecl) and isinstance(t.type, c_ast.IdentifierType):
        name = " ".join(t.type.names)
        return "word" if name in WORD_TYPES else name
    return None


def _shift_declarator(t: c_ast.Node) -> str | None:
    """SHIFT, SHIFT_POINTER, SHIFT_ARRAY or SHIFT_FUNCTION for a declarator of a shift, else None."""
    kind = SHIFT_FUNCTION if _is_function(t) else \
        {c_ast.PtrDecl: SHIFT_POINTER, c_ast.ArrayDecl: SHIFT_ARRAY}.get(type(t))
    if kind is not None:
        return kind if _base_type(t.type) == SHIFT else None
    return SHIFT if _base_type(t) == SHIFT else None


def _shifts(ast: c_ast.FileAST) -> dict[str, str]:
    """The file-scope names declared as shifts: name -> declarator kind."""
    shifts = {}
    for ext in ast.ext:
        decl = ext.decl if isinstance(ext, c_ast.FuncDef) else ext
        if isinstance(decl, c_ast.Decl) and not _in_header(decl) \
                and (kind := _shift_declarator(decl.type)) is not None:
            shifts[decl.name] = kind
    return shifts


def _is_shift_value(node: c_ast.Node, shifts: dict[str, str], sigs: dict[str, ir.Signature]) -> bool:
    """A shift constructor, SHIFT_UNSET, a shift, or a call of a function returning one."""
    if isinstance(node, c_ast.ID):
        return (node.name == SHIFT_UNSET and _builtin(node.name, sigs)) or shifts.get(node.name) == SHIFT
    if isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID):
        name = node.name.name
        return (name in INSN_SHIFT.keys() | INSN_SHIFT_BITS.keys() and _builtin(name, sigs)) \
            or shifts.get(name) == SHIFT_FUNCTION
    return False


def _is_shift_storage(node: c_ast.Node, shifts: dict[str, str]) -> bool:
    """A shift array, a pointer to a shift, or an address in a shift array."""
    if isinstance(node, c_ast.BinaryOp) and node.op == "+":
        node = node.left
    if isinstance(node, c_ast.UnaryOp) and node.op == "&" and isinstance(node.expr, c_ast.ArrayRef):
        node = node.expr.name
    return isinstance(node, c_ast.ID) and shifts.get(node.name) in (SHIFT_ARRAY, SHIFT_POINTER)


def _check_shift_store(target: str, kind: str | None, value: c_ast.Node, shifts: dict[str, str],
                       sigs: dict[str, ir.Signature]) -> None:
    """Only a shift is stored where a shift is executed, and a pointer to a
    shift points into shifts."""
    if kind in (SHIFT, SHIFT_ARRAY, SHIFT_FUNCTION) and not _is_shift_value(value, shifts, sigs):
        raise _err(value, f"{target} holds a shift: store I_SCL(n), I_SCL_BITS(w & m), "
                          f"SHIFT_UNSET or another shift")
    if kind == SHIFT_POINTER and not _is_shift_storage(value, shifts):
        raise _err(value, f"{target} points to a shift: store the address of a shift")


def _word_type(t: c_ast.Node) -> str | None:
    """"word" for a word (or insn), "word*" for a pointer to one or to a shift, else None."""
    if isinstance(t, c_ast.PtrDecl):
        return "word*" if _base_type(t.type) in ("word", SHIFT) else None
    return "word" if _base_type(t) == "word" else None


C_INT_OPS = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b,
             "<<": lambda a, b: a << b, ">>": lambda a, b: a >> b}


def c_int(node: c_ast.Node) -> int:
    if isinstance(node, c_ast.Constant) and node.type == "int":
        text = node.value.rstrip("uUlL")
        return int(text, 8 if _is_octal(text) else 0)
    if isinstance(node, c_ast.UnaryOp) and node.op == "-":
        return -c_int(node.expr)
    if isinstance(node, c_ast.BinaryOp) and node.op in C_INT_OPS:
        return C_INT_OPS[node.op](c_int(node.left), c_int(node.right))
    raise _err(node, "expected a compile-time integer constant")


def is_c_int(node: c_ast.Node) -> bool:
    try:
        c_int(node)
    except DialectError:
        return False
    return True


def _is_octal(text: str) -> bool:
    return len(text) > 1 and text[0] == "0" and text[1] not in "xXbB"


def const_word(node: c_ast.Node) -> int:
    """A constant word. Integer constants convert as C converts them, so -0 is
    +0; a cast to word makes the operators the machine's: -(word)0 is -0."""
    match node:
        case c_ast.Constant(type="int") | c_ast.UnaryOp(op="-", expr=c_ast.Constant()):
            return to_word(c_int(node), node)
        case c_ast.BinaryOp() | c_ast.UnaryOp(op="-") if is_c_int(node):
            return to_word(c_int(node), node)
        case c_ast.Cast() if _base_type(node.to_type.type) == "word":
            return const_word(node.expr)
        case c_ast.UnaryOp(op="-" | "~", expr=c_ast.Cast()):
            return const_word(node.expr) ^ ir.WORD_MASK
    raise _err(node, "expected a constant word")


def to_word(value: int, node: c_ast.Node) -> int:
    """C integer -> 18-bit word. A negative constant is the ones' complement."""
    if abs(value) > ir.WORD_MASK:
        raise _err(node, f"constant {value:#o} does not fit an 18-bit word")
    return value if value >= 0 else (-value) ^ ir.WORD_MASK


class Namer:
    """Generated Macro symbols: the region prefix and a counter."""

    def __init__(self, prefix: str, start: int = 0):
        self.prefix, self.counter = prefix, start

    def fresh(self) -> str:
        self.counter += 1
        name = f"{self.prefix}{self.counter}"
        if len(name) > MACRO_SYMBOL_LEN:
            raise DialectError(f"generated symbol {name} exceeds {MACRO_SYMBOL_LEN} characters")
        return name


class _Scope:
    def __init__(self, globals_: dict[str, ir.Storage]):
        self.frames: list[dict[str, ir.Storage]] = [globals_]
        self.pairs: set[str] = set()

    def lookup(self, node: c_ast.ID) -> ir.Var:
        for frame in reversed(self.frames):
            if node.name in frame:
                return ir.Var(node.name, frame[node.name])
        raise _err(node, f"undeclared name {node.name!r}")


def _symbol(name: str, attrs: dict[str, str], namer: Namer, node: c_ast.Node) -> str:
    """SYM("x") pins a symbol; a short C name is its own symbol; a long one gets a fresh one."""
    if "sym" in attrs:
        sym = attrs["sym"].strip('"')
        if not MACRO_SYMBOL.fullmatch(sym):
            raise _err(node, f"SYM({sym!r}) is not a Macro symbol: a lower-case letter, then "
                             f"letters or digits, {MACRO_SYMBOL_LEN} characters at most")
        if macro.predefined(sym):
            raise _err(node, f"SYM({sym!r}) is predefined by macro1")
        return sym
    if MACRO_SYMBOL.fullmatch(name) and not macro.predefined(name):
        return name
    return namer.fresh()


def _signature(decl: c_ast.Decl, namer: Namer, symbol: bool = True) -> ir.Signature:
    """symbol=False: a function type (typedef), which has no entry of its own."""
    attrs = _attrs(decl)
    convs = [CONVS[a] for a in attrs if a in CONVS]
    if "inline" in (getattr(decl, "funcspec", None) or []) and "static" in decl.storage:
        if convs:
            raise _err(decl, f"{decl.name}: a static inline function is laid out at each call; "
                             "it has no calling convention")
        convs = [ir.Conv.INLINE]
    if len(convs) != 1:
        raise _err(decl, f"{decl.name}: a function needs exactly one calling convention "
                         "(JDA, JSP, XCT or BLOCK)")
    conv = convs[0]
    ftype = decl.type
    params: list[ir.Param] = []
    for p in (ftype.args.params if ftype.args else []):
        if isinstance(p, c_ast.Typename) and _base_type(p.type) == "void":
            continue
        kind_of_type = _word_type(p.type)
        if kind_of_type is None:
            raise _err(p, f"{p.name}: a parameter must be a `word` or a pointer to one")
        p_attrs = _attrs(p)
        if "byname" in p_attrs and "inline" in p_attrs:
            raise _err(p, f"{p.name}: a parameter is BYNAME or INLINE, not both")
        if "byname" in p_attrs:
            kind = ir.ParamKind.BYNAME
        elif "inline" in p_attrs:
            kind = ir.ParamKind.INLINE
        elif "register" in p.storage:
            kind = ir.ParamKind.IO
        else:
            kind = ir.ParamKind.AC
        if kind is ir.ParamKind.BYNAME and kind_of_type != "word":
            raise _err(p, f"{p.name}: a BYNAME parameter is a `word`")
        params.append(ir.Param(p.name, kind, kind_of_type == "word*"))
    kinds = [p.kind for p in params]
    after = sum(k.after_call for k in kinds)
    if kinds.count(ir.ParamKind.AC) > 1 or kinds.count(ir.ParamKind.IO) > 1:
        raise _err(decl, f"{decl.name}: at most one AC parameter and one register parameter")
    if after > 1:
        raise _err(decl, f"{decl.name}: more than one word after the call is not implemented yet")
    if after and not kinds[-1].after_call:
        raise _err(decl, f"{decl.name}: BYNAME and INLINE parameters come last, as the words "
                         "after the call")
    if after and conv in (ir.Conv.XCT, ir.Conv.JSP, ir.Conv.INLINE):
        raise _err(decl, f"{decl.name}: an {conv.name} function has no inline words")
    if ir.ParamKind.AC in kinds and conv is ir.Conv.JSP:
        raise _err(decl, f"{decl.name}: a JSP function receives its return address in AC; "
                         "pass a register parameter")
    returns = "word" if _base_type(ftype.type) == SHIFT else _word_type(ftype.type) or _base_type(ftype.type)
    returns = "io" if returns == "io_word" else returns
    if returns not in ("word", "word*", "dword", "io", "void"):
        raise _err(decl, f"{decl.name}: returns word, a pointer to word, dword, io_word or void")
    skips = "skips" in attrs
    if skips and conv not in (ir.Conv.JDA, ir.Conv.BLOCK):
        raise _err(decl, f"{decl.name}: SKIPS returns past a word after a jda call; "
                         "only a JDA function or the BLOCK it tail-calls can")
    if not symbol:
        return ir.Signature(decl.name, "", conv, tuple(params), returns, "", skips)
    return ir.Signature(decl.name, _symbol(decl.name, attrs, namer, decl), conv, tuple(params),
                        returns, namer.fresh(), skips)


def lower_unit(ast: c_ast.FileAST, prefix: str = "z") -> ir.Unit:
    namer = Namer(prefix)
    sigs: dict[str, ir.Signature] = {}
    first: dict[str, c_ast.Decl] = {}
    for ext in ast.ext:
        decl = ext.decl if isinstance(ext, c_ast.FuncDef) else ext
        if isinstance(decl, c_ast.Decl) and _is_function(decl.type) and not _in_header(decl) \
                and decl.name != REGION_BREAK and decl.name not in DIRECTIVES:
            if "at" in _attrs(decl) and not isinstance(ext, c_ast.FuncDef):
                raise _err(decl, f"{decl.name}: AT places a definition, not a declaration")
            if decl.name not in sigs:
                sigs[decl.name], first[decl.name] = _signature(decl, namer), decl
            elif not _same_declaration(decl, first[decl.name]):
                raise _err(decl, f"{decl.name}: declarations disagree with the one at "
                                 f"{first[decl.name].coord}")

    types = {e.name: _signature(e, Namer("q"), symbol=False) for e in ast.ext
             if isinstance(e, c_ast.Typedef) and _is_function(e.type) and not _in_header(e)}

    globals_: dict[str, ir.Storage] = {}
    pointers: dict[str, ir.Signature] = {}
    shifts = _shifts(ast)
    objects = [e for e in ast.ext if isinstance(e, c_ast.Decl) and not _is_function(e.type)
               and not _in_header(e)]
    seen: dict[str, c_ast.Decl] = {}
    for ext in objects:
        if ext.name in seen and not _same_object(ext, seen[ext.name]):
            raise _err(ext, f"{ext.name}: declarations disagree with the one at {seen[ext.name].coord}")
        seen.setdefault(ext.name, ext)
        if (fn_type := _pointee(ext.type, types)) is not None:
            pointers[ext.name] = fn_type
    arrays: set[str] = set()
    for ext in objects:                       # definitions first: an extern may precede one
        attrs = _attrs(ext)
        if isinstance(ext.type, c_ast.ArrayDecl):
            arrays.add(ext.name)
        storages = {"entry_cell", "pool", "homed", "reserve"} & attrs.keys()
        if len(storages) > 1:
            raise _err(ext, f"{ext.name}: {', '.join(s.upper() for s in sorted(storages))} "
                            "name different storage; use one")
        if "entry_cell" in attrs:
            owner = sigs.get(attrs["entry_cell"])
            if owner is None or owner.conv is not ir.Conv.JDA or \
                    not any(p.kind is ir.ParamKind.AC for p in owner.params):
                raise _err(ext, f"{ext.name}: ENTRY_CELL names a JDA function with an AC "
                                "parameter, declared above")
            globals_[ext.name] = ir.Entry(owner.sym, alias=True)
        elif "homed" in attrs and shifts.get(ext.name) == SHIFT:
            if ext.init is None or not is_insn(ext.init, sigs):
                raise _err(ext, f"{ext.name}: a HOMED shift is the instruction at its home; "
                                "initialize it with the instruction it holds first")
            globals_[ext.name] = ir.HomedInsn(_symbol(ext.name, attrs, namer, ext),
                                         insn(ext.init, _Scope(globals_), sigs, arrays))
        elif "pool" in attrs or "homed" in attrs:
            if ext.init is not None and ("pool" in attrs or _word_type(ext.type) != "word*"):
                raise _err(ext, f"{ext.name}: a POOL object or a HOMED word has no initializer")
            if "homed" in attrs and _word_type(ext.type) is None and ext.name not in pointers:
                raise _err(ext, f"{ext.name}: HOMED declares a pointer, or a word that "
                                "indexes the switch that is its home")
            if "pool" in attrs and _word_type(ext.type) is None and ext.name not in pointers:
                raise _err(ext, f"{ext.name}: a POOL object is a `word` or a pointer")
            sym = _symbol(ext.name, attrs, namer, ext)
            if "pool" in attrs:
                globals_[ext.name] = ir.Pool(sym)
            else:
                defined = any("extern" not in o.storage for o in objects if o.name == ext.name)
                globals_[ext.name] = ir.Homed(sym, _home_init(ext, globals_, sigs, arrays), defined)
        elif ext.init is not None or "reserve" in attrs:
            globals_[ext.name] = ir.Placed(_symbol(ext.name, attrs, namer, ext))
    for ext in objects:
        if ext.name in globals_:
            continue
        attrs = _attrs(ext)
        if "extern" not in ext.storage:
            raise _err(ext, f"{ext.name}: an uninitialized file-scope object needs a storage "
                            "class: POOL, RESERVE or HOMED (or extern for unlifted text)")
        if not MACRO_SYMBOL.fullmatch(ext.name) and "sym" not in attrs:
            raise _err(ext, f"{ext.name}: an extern names unlifted text; give it SYM(\"x\")")
        globals_[ext.name] = ir.Extern(_symbol(ext.name, attrs, namer, ext))

    for ext in objects:
        if ext.init is not None:
            inits = ext.init.exprs if isinstance(ext.init, c_ast.InitList) else [ext.init]
            for value in inits:
                _check_shift_store(ext.name, shifts.get(ext.name), value, shifts, sigs)
    data: dict[str, ir.Datum] = {}
    for ext in objects:
        if ext.init is not None and isinstance(globals_.get(ext.name), ir.Placed):
            data[ext.name] = _datum(ext, globals_[ext.name].sym, globals_, sigs, arrays)
    placed_later = _placed_names(ast)
    if missing := placed_later - data.keys():
        raise DialectError(f"PLACE names {sorted(missing)}, which are not initialized "
                           "file-scope words defined in this file")

    items: list[ir.TopItem] = []
    inlines: dict[str, ir.Function] = {}
    for ext in ast.ext:
        if isinstance(ext, c_ast.FuncDef):
            fn = _lower_function(ext, sigs[ext.decl.name], globals_, sigs, pointers, namer,
                                 data, arrays, types, shifts)
            if fn.sig.conv is ir.Conv.INLINE:
                if _origin(ext.decl) is not None:
                    raise _err(ext, f"{fn.sig.name}: a static inline function is laid out at "
                                    "its calls; AT does not apply")
                inlines[fn.sig.name] = fn
                continue
            items.append(ir.Function(fn.sig, fn.params, fn.body, _origin(ext.decl)))
        elif isinstance(ext, c_ast.Decl) and ext.name == REGION_BREAK:
            items.append(ir.RegionBreak())
        elif isinstance(ext, c_ast.Decl) and ext.name in DIRECTIVES:
            items.append(ir.Directive(DIRECTIVES[ext.name]))
        elif isinstance(ext, c_ast.Decl) and not _is_function(ext.type) and not _in_header(ext):
            attrs = _attrs(ext)
            if isinstance(globals_[ext.name], (ir.Homed, ir.HomedInsn)):
                continue
            if ext.init is None and "reserve" not in attrs:
                if "at" in attrs:
                    raise _err(ext, f"{ext.name}: AT places a definition, not a declaration")
                continue
            storage = globals_[ext.name]
            if not isinstance(storage, ir.Placed):
                raise _err(ext, f"{ext.name}: defined here but declared elsewhere as {storage}")
            if "reserve" in attrs:
                if ext.init is not None or "extern" in ext.storage:
                    raise _err(ext, f"{ext.name}: RESERVE sets aside uninitialized words; "
                                    "it has no initializer and is not extern")
                items.append(ir.Space(storage.sym, _words(ext), ext.name, _origin(ext),
                                      array=isinstance(ext.type, c_ast.ArrayDecl),
                                      pointer=isinstance(ext.type, c_ast.PtrDecl)))
                continue
            if ext.name not in placed_later:
                items.append(data[ext.name])
    return ir.Unit(tuple(items), sigs, namer.counter, globals_, data, inlines)


def _home_init(ext: c_ast.Decl, globals_: dict[str, ir.Storage], sigs: dict[str, ir.Signature],
               arrays: set[str]) -> ir.Sym | ir.Num | None:
    if ext.init is None:
        return None
    if is_c_int(ext.init) and c_int(ext.init) == 0:
        return ir.Num(0)
    return _operand_of(ext.init, _Scope(globals_), sigs, arrays)


def _placed_names(ast: c_ast.FileAST) -> set[str]:
    """Objects some PLACE(...) lays out inside a function."""
    found: set[str] = set()

    def visit(node: c_ast.Node) -> None:
        if isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID) \
                and node.name.name == "pdp1_place":
            for arg in (node.args.exprs if node.args else []):
                if not isinstance(arg, c_ast.ID):
                    raise _err(arg, "PLACE takes the names of file-scope words")
                if arg.name in found:
                    raise _err(arg, f"{arg.name} is PLACEd twice")
                found.add(arg.name)
        for _, child in node.children():
            visit(child)
    for ext in ast.ext:
        if isinstance(ext, c_ast.FuncDef):
            visit(ext.body)
    return found


def _datum(ext: c_ast.Decl, sym: str, globals_: dict[str, ir.Storage],
           sigs: dict[str, ir.Signature], arrays: set[str]) -> ir.Datum:
    """An initialized file-scope word or word array: one value per word."""
    t = ext.type
    if isinstance(t, c_ast.ArrayDecl):
        if _base_type(t.type) not in ("word", SHIFT) or not isinstance(ext.init, c_ast.InitList):
            raise _err(ext, f"{ext.name}: a placed array is `word name[N] = {{ ... }}`")
        inits = ext.init.exprs
        if t.dim is not None and c_int(t.dim) != len(inits):
            raise _err(ext, f"{ext.name}: {c_int(t.dim)} words declared, {len(inits)} given; "
                            "set the rest aside with RESERVE")
        values = tuple(_data_value(e, globals_, sigs, arrays) for e in inits)
        return ir.Datum(sym, values, ext.name, _origin(ext), array=True)
    if _word_type(t) == "word*":
        value = _operand_of(ext.init, _Scope(globals_), sigs, arrays)
        return ir.Datum(sym, (value,), ext.name, _origin(ext))
    if _base_type(t) != "word":
        raise _err(ext, f"{ext.name}: only `word` objects, pointers and word arrays can be placed")
    return ir.Datum(sym, (_data_value(ext.init, globals_, sigs, arrays),), ext.name, _origin(ext))


def _data_value(node: c_ast.Node, globals_: dict[str, ir.Storage],
                sigs: dict[str, ir.Signature], arrays: set[str]) -> int | ir.Insn:
    if isinstance(node, c_ast.FuncCall) or (isinstance(node, c_ast.ID) and node.name in INSN_CONSTANT):
        return insn(node, _Scope(globals_), sigs, arrays)
    return const_word(node)


def _operand_of(node: c_ast.Node, scope: _Scope, sigs: dict[str, ir.Signature],
                arrays: set[str]) -> ir.Sym:
    if isinstance(node, c_ast.BinaryOp) and node.op == "+" and is_c_int(node.right):
        if not _array_address(node.left, arrays):
            raise _err(node, "an offset address is `array + n`")
        base = _operand_of(node.left, scope, sigs, arrays)
        return ir.Sym(base.name, base.pool, base.offset + c_int(node.right))
    if isinstance(node, c_ast.UnaryOp) and node.op == "&" and isinstance(node.expr, c_ast.ArrayRef) \
            and isinstance(node.expr.name, c_ast.ID) and node.expr.name.name in arrays:
        base = _operand_of(node.expr.name, scope, sigs, arrays)
        return ir.Sym(base.name, base.pool, c_int(node.expr.subscript))
    if isinstance(node, c_ast.UnaryOp) and node.op == "&" and isinstance(node.expr, c_ast.ID):
        var = scope.lookup(node.expr)
        if isinstance(var.storage, ir.Memory):
            return ir.Sym(ir.mem_sym(var.storage), pool=isinstance(var.storage, ir.Pool))
        raise _err(node, f"{node.expr.name} has no address: it is not a word in memory")
    if isinstance(node, c_ast.ID) and node.name in arrays:
        return ir.Sym(ir.mem_sym(scope.lookup(node).storage))
    if isinstance(node, c_ast.ID) and node.name in sigs and \
            not any(node.name in f for f in scope.frames):
        return ir.Sym(sigs[node.name].sym)
    raise _err(node, "an instruction's address is &object, an array or a function")


def _array_address(node: c_ast.Node, arrays: set[str]) -> bool:
    """An array's name, or `a + n` for such an address a and a constant n."""
    if isinstance(node, c_ast.ID):
        return node.name in arrays
    return isinstance(node, c_ast.BinaryOp) and node.op == "+" and is_c_int(node.right) \
        and _array_address(node.left, arrays)


def insn(node: c_ast.Node, scope: _Scope, sigs: dict[str, ir.Signature],
         arrays: set[str]) -> ir.Insn:
    """An I_* constructor: an instruction word, a constant."""
    if isinstance(node, c_ast.ID) and node.name in INSN_CONSTANT and _builtin(node.name, sigs):
        return INSN_CONSTANT[node.name]
    if not (isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID)):
        raise _err(node, "expected an instruction constructor")
    name = node.name.name
    args = node.args.exprs if node.args else []
    if len(args) != 1:
        raise _err(node, f"{name} takes one argument")
    if name in INSN_MEMORY:
        if is_c_int(args[0]) and c_int(args[0]) == 0:
            return ir.Insn(INSN_MEMORY[name])
        return ir.Insn(INSN_MEMORY[name], _operand_of(args[0], scope, sigs, arrays))
    n = c_int(args[0])
    if name in INSN_FLAG:
        if not 1 <= n <= MAX_FLAG:
            raise _err(node, f"{name}({n}): program flags are 1..6, and 7 for all")
        return ir.Insn(INSN_FLAG[name], ir.Num(n))
    if name in INSN_SHIFT:
        if not 0 <= n <= MAX_INSN_SHIFT:
            raise _err(node, f"{name}({n}): one instruction shifts 0..9 places")
        return ir.Insn(INSN_SHIFT[name], ir.ShiftCount(n) if n else None)
    raise _err(node, f"{name} is not an instruction constructor")


def is_insn(node: c_ast.Node, sigs: dict[str, ir.Signature]) -> bool:
    if isinstance(node, c_ast.ID):
        return node.name in INSN_CONSTANT and _builtin(node.name, sigs)
    return isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID) and \
        node.name.name in INSN_MEMORY.keys() | INSN_FLAG.keys() | INSN_SHIFT.keys() and \
        _builtin(node.name.name, sigs)


def _decl_attrs(decl: c_ast.Decl) -> dict[str, str]:
    """Attributes every declaration of an object repeats: all but placement."""
    return {k: v for k, v in _attrs(decl).items() if k not in ("at", "reserve")}


def _same_object(a: c_ast.Decl, b: c_ast.Decl) -> bool:
    """Declarations of one object agree on its attributes. HOMED belongs to
    the definition, as a storage class does in C: an extern declaration
    reaches the pointer through its home by name, with or without it."""
    attrs_a, attrs_b = _decl_attrs(a), _decl_attrs(b)
    if "extern" in a.storage or "extern" in b.storage:
        attrs_a.pop("homed", None)
        attrs_b.pop("homed", None)
    return attrs_a == attrs_b


def _origin(decl: c_ast.Decl) -> int | None:
    attrs = _attrs(decl)
    if "at" not in attrs:
        return None
    try:
        at = int(attrs["at"], 0 if not _is_octal(attrs["at"]) else 8)
    except ValueError:
        raise _err(decl, f"{decl.name}: AT({attrs['at']}) needs an integer address") from None
    if not 0 <= at <= ir.ADDR_MASK:
        raise _err(decl, f"{decl.name}: AT({at:o}) is outside core")
    return at


def _words(decl: c_ast.Decl) -> int:
    """Words a RESERVE object occupies: 1, or an array's constant length."""
    t = decl.type
    if isinstance(t, c_ast.ArrayDecl):
        if _base_type(t.type) != "word" or t.dim is None:
            raise _err(decl, f"{decl.name}: a reserved array is `word name[N]`")
        return c_int(t.dim)
    if _base_type(t) == "word" or isinstance(t, c_ast.PtrDecl):
        return 1
    raise _err(decl, f"{decl.name}: RESERVE takes a word, a word array or a pointer")


def _pointee(t: c_ast.Node, types: dict[str, ir.Signature]) -> ir.Signature | None:
    """The function type of a pointer-to-function object `ftype *p`."""
    if isinstance(t, c_ast.PtrDecl):
        name = _base_type(t.type)
        if name in types:
            return types[name]
        if name in ("word", SHIFT):
            return None
        raise _err(t, "a pointer points to a word or to a function type declared with typedef")
    return None


def _same_declaration(a: c_ast.Decl, b: c_ast.Decl) -> bool:
    """Same parameters, return type and dialect attributes, so no single
    declaration's attribute is decoration."""
    sa, sb = _signature(a, Namer("q")), _signature(b, Namer("q"))
    placement = {"at"}          # AT belongs to the definition alone
    attrs_a = {k: v for k, v in _attrs(a).items() if k not in placement}
    attrs_b = {k: v for k, v in _attrs(b).items() if k not in placement}
    return (sa.params, sa.returns, sa.conv) == (sb.params, sb.returns, sb.conv) and attrs_a == attrs_b


def _lower_function(fn: c_ast.FuncDef, sig: ir.Signature, globals_: dict[str, ir.Storage],
                    sigs: dict[str, ir.Signature], pointers: dict[str, ir.Signature],
                    namer: Namer, data: dict[str, ir.Datum], arrays: set[str],
                    types: dict[str, ir.Signature], shifts: dict[str, str]) -> ir.Function:
    scope = _Scope(globals_)
    frame: dict[str, ir.Storage] = {}
    params: list[ir.Var] = []
    for p in sig.params:
        if p.kind is ir.ParamKind.AC:
            storage = ir.Entry(sig.sym) if sig.conv is ir.Conv.JDA else ir.Acc(p.name)
        elif p.kind is ir.ParamKind.IO:
            storage = ir.Io(p.name)
        elif p.kind is ir.ParamKind.INLINE:
            storage = ir.Inline(p.name)
        else:
            storage = ir.ByName(p.name)
        frame[p.name] = storage
        params.append(ir.Var(p.name, storage))
    scope.frames.append(frame)
    lowerer = _Lowerer(scope, sigs, pointers, namer, data, arrays, types, shifts, sig.name)
    body = lowerer.block(fn.body)
    if missing := lowerer.labels_used - lowerer.labels_defined:
        raise _err(fn, f"{sig.name}: goto to undefined label(s) {sorted(missing)}")
    return ir.Function(sig, tuple(params), body)


class _Lowerer:
    def __init__(self, scope: _Scope, sigs: dict[str, ir.Signature],
                 pointers: dict[str, ir.Signature], namer: Namer,
                 data: dict[str, ir.Datum], arrays: set[str], types: dict[str, ir.Signature],
                 shifts: dict[str, str], fn_name: str):
        self.scope, self.sigs, self.pointers, self.namer = scope, sigs, pointers, namer
        self.types = types
        self.data, self.arrays, self.shifts, self.fn_name = data, arrays, shifts, fn_name
        self.labels: dict[str, str] = {}
        self.labels_used: set[str] = set()
        self.labels_defined: set[str] = set()

    def label(self, name: str) -> str:
        """C labels are function-scoped; each gets a generated Macro symbol."""
        if name not in self.labels:
            self.labels[name] = self.namer.fresh()
        return self.labels[name]

    # ---------------------------------------------------------- statements
    def block(self, node: c_ast.Compound) -> ir.Block:
        self.scope.frames.append({})
        out: list[ir.Stmt] = []
        for item in node.block_items or []:
            s = self.stmt(item)
            if s is not None:
                out.append(s)
        self.scope.frames.pop()
        return ir.Block(tuple(out))

    def stmt(self, node: c_ast.Node) -> ir.Stmt | None:
        if isinstance(node, c_ast.Assignment):
            self.check_shift_store(node)
        match node:
            case c_ast.Compound():
                return self.block(node)
            case c_ast.Decl():
                return self.local(node)
            case c_ast.Assignment(op="=", lvalue=c_ast.UnaryOp(op="*", expr=c_ast.UnaryOp(op="p++"))):
                pointer = self.scope.lookup(node.lvalue.expr.expr) \
                    if isinstance(node.lvalue.expr.expr, c_ast.ID) else None
                if pointer is None or not isinstance(pointer.storage, ir.Memory):
                    raise _err(node, "*p++ = e needs a pointer p held in a memory word")
                return ir.StoreNext(pointer, self.expr(node.rvalue))
            case c_ast.Assignment(op="=", lvalue=c_ast.StructRef(type=".", field=c_ast.ID(name="addr"))):
                target = node.lvalue.name
                var = self.scope.lookup(target) if isinstance(target, c_ast.ID) else None
                if var is None or not isinstance(var.storage, ir.Memory):
                    raise _err(node, "x.addr = e needs a word x in memory")
                return ir.AssignAddr(var, self.expr(node.rvalue))
            case c_ast.Assignment(op="=", lvalue=c_ast.UnaryOp(op="*", expr=c_ast.FuncCall())) \
                    if (p := self.home_of(node.lvalue.expr)) is not None:
                return ir.HomeStore(p, self.expr(node.rvalue))
            case c_ast.Assignment(op="=", lvalue=c_ast.StructRef(type="->", field=c_ast.ID(name="addr"))) \
                    if (p := self.home_of(node.lvalue.name)) is not None:
                return ir.HomeStore(p, self.expr(node.rvalue), addr=True)
            case c_ast.Assignment(op="=", lvalue=c_ast.UnaryOp(op="*")):
                return ir.Assign(self.lvalue(node.lvalue), self.expr(node.rvalue))
            case c_ast.Assignment(op="=", lvalue=c_ast.ID()) if self._homed(node.lvalue.name):
                return ir.AssignAddr(self.scope.lookup(node.lvalue), self.expr(node.rvalue))
            case c_ast.Assignment(op="="):
                return self.assign(node.lvalue, self.expr(node.rvalue), node)
            case c_ast.Assignment(op="+=" | "-="):
                target = self.expr(node.lvalue)
                return self.assign(node.lvalue, ir.Binary(node.op[0], target, self.expr(node.rvalue)), node)
            case c_ast.FuncCall(name=c_ast.ID(name="skip_return")):
                return ir.SkipReturn()
            case c_ast.FuncCall(name=c_ast.ID(name="pdp1_args_done")):
                return ir.ArgsDone()
            case c_ast.FuncCall(name=c_ast.ID(name="pdp1_place")):
                return ir.PlaceHere(tuple(self.data[a.name] for a in node.args.exprs))
            case c_ast.FuncCall(name=c_ast.ID(name=op)) if op in FLAG_OPS and _builtin(op, self.sigs):
                args = node.args.exprs if node.args else []
                if len(args) != 1 or not 1 <= c_int(args[0]) <= MAX_FLAG:
                    raise _err(node, f"{op}(n) takes a program flag 1..6, or 7 for all")
                return ir.Eval(ir.Flag(op, c_int(args[0])))
            case c_ast.Switch():
                return self.switch(node)
            case c_ast.ExprList():
                return ir.OprCombine(tuple(self.stmt(e) for e in node.exprs))
            case c_ast.UnaryOp(op="++") | c_ast.FuncCall():
                return ir.Eval(self.expr(node))
            case c_ast.If():
                return ir.If(self.cond(node.cond), self.stmt(node.iftrue),
                             self.stmt(node.iffalse) if node.iffalse else None)
            case c_ast.For(init=None, cond=None, next=None):
                return ir.Forever(self.stmt(node.stmt))
            case c_ast.For():
                return self.unroll(node)
            case c_ast.Continue():
                return ir.Continue()
            case c_ast.Return():
                if node.expr is not None:
                    _check_shift_store(self.fn_name, self.shifts.get(self.fn_name), node.expr,
                                       self.shifts, self.sigs)
                return ir.Return(self.expr(node.expr) if node.expr else None)
            case c_ast.Goto():
                self.labels_used.add(node.name)
                return ir.Goto(self.label(node.name))
            case c_ast.Label():
                if node.name in self.labels_defined:
                    raise _err(node, f"label {node.name} defined twice")
                self.labels_defined.add(node.name)
                inner = self.stmt(node.stmt)
                return ir.Labeled(self.label(node.name), inner if inner is not None else ir.Block(()))
            case c_ast.EmptyStatement():
                return None
        raise _err(node, f"statement {type(node).__name__} is not in the implemented dialect yet")

    def switch(self, node: c_ast.Switch) -> ir.Switch:
        """switch ((int)e) { case 0: ... case n: ... }: every case 0..n in order,
        no default. A case before the last is `goto L` or empty (it falls into
        the next); the last case's statements sit in its slot and end in a jump."""
        cond = node.cond
        if not (isinstance(cond, c_ast.Cast) and _base_type(cond.to_type.type) == "int"):
            raise _err(node, "a jump table switches on a word cast to int: switch ((int)w)")
        if isinstance(cond.expr, c_ast.ID) and self._homed(cond.expr.name):
            return self.homed_switch(node, self.scope.lookup(cond.expr))
        cases = _cases(node, "a jump table", "a jump table's cases")
        slots: list[ir.Stmt | None] = []
        for stmts in cases[:-1]:
            if not stmts:
                slots.append(None)
            elif len(stmts) == 1 and isinstance(stmts[0], c_ast.Goto):
                slots.append(self.stmt(stmts[0]))
            else:
                raise _err(stmts[0], "a case before the last is `goto label;` or empty")
        self.scope.frames.append({})
        last = ir.Block(tuple(s for s in map(self.stmt, cases[-1]) if s is not None))
        self.scope.frames.pop()
        return ir.Switch(self.expr(cond.expr), tuple(slots), last)

    def homed_switch(self, node: c_ast.Switch, index: ir.Var) -> ir.HomedSwitch:
        cases = _cases(node, "a switch", "the cases")
        lowered = []
        for stmts in cases:
            self.scope.frames.append({})
            lowered.append(ir.Block(tuple(s for s in map(self.stmt, stmts) if s is not None)))
            self.scope.frames.pop()
        return ir.HomedSwitch(index, self.namer.fresh(), tuple(lowered[:-1]), lowered[-1])

    def assign(self, lvalue: c_ast.Node, value: ir.Expr, node: c_ast.Node) -> ir.Stmt:
        if isinstance(lvalue, c_ast.ID) and lvalue.name in self.scope.pairs:
            hi, lo = self.pair_halves(lvalue)
            return ir.AssignPair(hi, lo, value)
        return ir.Assign(self.lvalue(lvalue), value)

    def unroll(self, node: c_ast.For) -> ir.Unroll:
        """for (int i = 0; i < N; i++) S: a compile-time loop, S emitted N times."""
        init = node.init.decls if isinstance(node.init, c_ast.DeclList) else []
        ok = (len(init) == 1 and _base_type(init[0].type) == "int" and init[0].init is not None
              and c_int(init[0].init) == 0
              and isinstance(node.cond, c_ast.BinaryOp) and node.cond.op == "<"
              and isinstance(node.cond.left, c_ast.ID) and node.cond.left.name == init[0].name
              and isinstance(node.next, c_ast.UnaryOp) and node.next.op in ("p++", "++")
              and isinstance(node.next.expr, c_ast.ID) and node.next.expr.name == init[0].name)
        if not ok:
            raise _err(node, "a counted loop must be `for (int i = 0; i < N; i++)` (unrolled)")
        if _mentions(node.stmt, init[0].name):
            raise _err(node, f"the unrolled body must not use the counter {init[0].name}")
        return ir.Unroll(c_int(node.cond.right), self.stmt(node.stmt), str(node.coord))

    def local(self, node: c_ast.Decl) -> ir.Stmt | None:
        if "static" in node.storage or "extern" in node.storage:
            raise _err(node, f"{node.name}: static locals are not implemented yet")
        kind = _base_type(node.type)
        if kind == "dword":
            frame = self.scope.frames[-1]
            frame[node.name + ".hi"] = ir.Acc(node.name + ".hi")
            frame[node.name + ".lo"] = ir.Io(node.name + ".lo")
            self.scope.pairs.add(node.name)
            if node.init is None:
                return None
            hi, lo = self.pair_halves(c_ast.ID(node.name, node.coord))
            return ir.AssignPair(hi, lo, self.expr(node.init))
        if kind != "word" and _word_type(node.type) != "word*":
            raise _err(node, f"{node.name}: locals must be `word`, `insn`, `dword` or `word *`")
        storage = ir.Io(node.name) if "register" in node.storage else ir.Acc(node.name)
        self.scope.frames[-1][node.name] = storage
        if node.init is None:
            return None
        return ir.Assign(ir.Var(node.name, storage), self.expr(node.init))

    def check_shift_store(self, node: c_ast.Assignment) -> None:
        """x = e for a shift x, *p = e and *p++ = e for a pointer p to a shift:
        e is a shift. p = e for such a pointer: e is the address of one."""
        target, through = node.lvalue, False
        while isinstance(target, c_ast.UnaryOp) and target.op in ("*", "p++"):
            target, through = target.expr, through or target.op == "*"
        if not isinstance(target, c_ast.ID) or self._is_local(target.name):
            return
        kind = self.shifts.get(target.name)
        if through:
            kind = SHIFT if kind == SHIFT_POINTER else None
        if kind is not None and node.op != "=":
            raise _err(node, f"{target.name}: a shift is built by a constructor, not by {node.op}")
        _check_shift_store(target.name, kind, node.rvalue, self.shifts, self.sigs)

    def pair_halves(self, node: c_ast.ID) -> tuple[ir.Var, ir.Var]:
        return (self.scope.lookup(c_ast.ID(node.name + ".hi", node.coord)),
                self.scope.lookup(c_ast.ID(node.name + ".lo", node.coord)))

    def lvalue(self, node: c_ast.Node) -> ir.Var | ir.Deref | ir.HomeLoad:
        if isinstance(node, c_ast.UnaryOp) and node.op == "*" and isinstance(node.expr, c_ast.FuncCall):
            home = self.expr(node)
            if not isinstance(home, ir.HomeLoad):
                raise _err(node, "*f(...) is not something to assign; *home(p) is")
            return home
        if isinstance(node, c_ast.UnaryOp) and node.op == "*":
            return self.deref(node)
        if isinstance(node, c_ast.ArrayRef):
            return self.element(node)
        if isinstance(node, c_ast.StructRef) and node.type == "." and isinstance(node.name, c_ast.ID) \
                and node.name.name in self.scope.pairs and node.field.name in ("hi", "lo"):
            return self.scope.lookup(c_ast.ID(f"{node.name.name}.{node.field.name}", node.coord))
        if not isinstance(node, c_ast.ID):
            raise _err(node, "only plain names and dword halves can be assigned")
        var = self.scope.lookup(node)
        if isinstance(var.storage, ir.ByName):
            raise _err(node, f"{node.name}: a BYNAME parameter is the caller's word and cannot be assigned")
        return var

    def cond(self, node: c_ast.Node) -> ir.Compare | ir.FlagTest:
        if isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID) \
                and node.name.name == "pdp1_skipnot":
            args = node.args.exprs if node.args else []
            c = self.cond(args[0]) if len(args) == 1 else None
            if not isinstance(c, ir.Compare) or c.against is not None or c.op not in ("<", ">=") \
                    or isinstance(c.operand, ir.PreInc) \
                    or (isinstance(c.operand, ir.Var) and isinstance(c.operand.storage, ir.Io)):
                raise _err(node, "SKIPNOT(c) takes a sign test of AC: `e < 0` or `e >= 0`")
            return replace(c, skipnot=True)
        negated = isinstance(node, c_ast.UnaryOp) and node.op == "!"
        test = node.expr if negated else node
        if isinstance(test, c_ast.FuncCall) and isinstance(test.name, c_ast.ID) \
                and test.name.name == "flag" and _builtin("flag", self.sigs):
            args = test.args.exprs if test.args else []
            if len(args) != 1 or not 1 <= c_int(args[0]) <= MAX_FLAG - 1:
                raise _err(node, "flag(n) tests a program flag 1..6")
            return ir.FlagTest(c_int(args[0]), negated)
        if isinstance(test, c_ast.FuncCall) and isinstance(test.name, c_ast.ID) \
                and test.name.name == "sense" and _builtin("sense", self.sigs):
            args = test.args.exprs if test.args else []
            if len(args) != 1 or not 1 <= c_int(args[0]) <= MAX_SENSE:
                raise _err(node, "sense(n) tests a sense switch 1..6")
            return ir.SenseTest(c_int(args[0]), negated)
        if isinstance(node, c_ast.BinaryOp) and node.op in CMP_OPS:
            if is_c_int(node.right) and to_word(c_int(node.right), node.right) == 0:
                return ir.Compare(node.op, self.expr(node.left))
            if node.op not in ("==", "!="):
                raise _err(node, "a comparison with a value other than 0 is == or != "
                                 "(sas, sad): the skip group orders only against 0")
            return ir.Compare(node.op, self.expr(node.left), self.expr(node.right))
        raise _err(node, "a condition must be `e <op> 0`, `a == b` or `a != b`")

    # --------------------------------------------------------- expressions
    def expr(self, node: c_ast.Node) -> ir.Expr:
        match node:
            case c_ast.Constant(type="int"):
                return ir.Const(to_word(c_int(node), node))
            case c_ast.Cast(to_type=c_ast.Typename(type=c_ast.PtrDecl())):
                return self.expr(node.expr)         # an address is the same word as any pointer
            case c_ast.Cast() if _base_type(node.to_type.type) == "word" and not _is_constant(node.expr):
                return self.expr(node.expr)         # a pointer is the word that holds its address
            case c_ast.Cast() | c_ast.UnaryOp(op="-" | "~", expr=c_ast.Cast()):
                return ir.Const(const_word(node))
            case c_ast.FuncCall(name=c_ast.ID(name=name)) if name in INSN_MEMORY and \
                    _builtin(name, self.sigs) and (word := self.home_word(node, INSN_MEMORY[name])):
                return word
            case _ if is_insn(node, self.sigs):
                return insn(node, self.scope, self.sigs, self.arrays)
            case c_ast.FuncCall(name=c_ast.ID(name=name)) if name in INSN_SHIFT_BITS and \
                    _builtin(name, self.sigs):
                return self.shift_bits(node, name)
            case c_ast.BinaryOp() if is_c_int(node):
                return ir.Const(to_word(c_int(node), node))
            case c_ast.BinaryOp(op="+") if _array_address(node, self.arrays) \
                    and not self._is_local(_array_root(node).name):
                return ir.AddrOf(_operand_of(node, self.scope, self.sigs, self.arrays))
            case c_ast.ArrayRef():
                return self.element(node)
            case c_ast.UnaryOp(op="*", expr=c_ast.FuncCall(name=c_ast.ID(name="home"))) \
                    if _builtin("home", self.sigs):
                args = node.expr.args.exprs if node.expr.args else []
                var = self.scope.lookup(args[0]) if len(args) == 1 and isinstance(args[0], c_ast.ID) else None
                if var is None or not isinstance(var.storage, ir.Homed):
                    raise _err(node, "*home(p) names a HOMED pointer p")
                return ir.HomeLoad(var)
            case c_ast.UnaryOp(op="*"):
                return self.deref(node)
            case c_ast.BinaryOp(op="|", left=c_ast.ID()) if node.left.name in self.sigs \
                    and not self._is_variable(node.left.name):
                return self.code_flags(node)
            case c_ast.ID() if node.name in self.arrays and not self._is_local(node.name):
                return ir.AddrOf(_operand_of(node, self.scope, self.sigs, self.arrays))
            case c_ast.UnaryOp(op="&", expr=c_ast.ID()):
                return ir.AddrOf(_operand_of(node, self.scope, self.sigs, self.arrays))
            case c_ast.ID() if node.name in self.sigs and not self._is_variable(node.name):
                return ir.CodeRef(self.sigs[node.name])
            case c_ast.ID():
                return self.scope.lookup(node)
            case c_ast.StructRef(type="."):
                if isinstance(node.name, c_ast.FuncCall) and node.field.name in ("hi", "lo"):
                    call = self.expr(node.name)
                    if not isinstance(call, ir.Call) or call.sig.returns != "dword":
                        raise _err(node, "only a dword call result has .hi and .lo")
                    return ir.Half(call, node.field.name)
                return self.lvalue(node)
            case c_ast.UnaryOp(op="-", expr=c_ast.Constant()):
                return ir.Const(to_word(c_int(node), node))
            case c_ast.UnaryOp(op="-" | "~"):
                return ir.Neg(self.expr(node.expr))
            case c_ast.UnaryOp(op="++"):
                return ir.PreInc(self.lvalue(node.expr))
            case c_ast.BinaryOp(op="<<" | ">>"):
                return ir.Shift(node.op, self.expr(node.left), c_int(node.right))
            case c_ast.BinaryOp() if node.op in BIN_OPS:
                return ir.Binary(node.op, self.expr(node.left), self.expr(node.right))
            case c_ast.CompoundLiteral():
                if _base_type(node.type.type) != "dword" or len(node.init.exprs) != 2:
                    raise _err(node, "the only compound literal is (dword){ hi, lo }")
                return ir.Pair(self.expr(node.init.exprs[0]), self.expr(node.init.exprs[1]))
            case c_ast.FuncCall(name=c_ast.ID(name=name)):
                return self.call(node, name)
            case c_ast.FuncCall(name=c_ast.Cast()):
                return self.computed_call(node)
            case c_ast.FuncCall(name=c_ast.UnaryOp(op="*")) if (p := self.home_of(node.name.expr)) is not None:
                if p.name not in self.pointers:
                    raise _err(node, f"(*home({p.name}))(...) jumps through a pointer to a function type")
                sig = self.pointers[p.name]
                args = node.args.exprs if node.args else []
                if len(args) != len(sig.params):
                    raise _err(node, f"{p.name} points to a {sig.name}, which takes {len(sig.params)} arguments")
                return ir.IndirectCall(p, sig, tuple(self.expr(a) for a in args), home=True)
        raise _err(node, f"expression {type(node).__name__} is not in the implemented dialect yet")

    def element(self, node: c_ast.ArrayRef) -> ir.Var:
        """a[k] for a file-scope array a (or an address a + n into one) and a
        constant k: the word k past a, named as a memory operand."""
        if not (_array_address(node.name, self.arrays) and is_c_int(node.subscript)) \
                or self._is_local(_array_root(node.name).name):
            raise _err(node, "a[k] indexes a file-scope array (or an address in one) by a constant")
        at = _operand_of(node.name, self.scope, self.sigs, self.arrays)
        offset = at.offset + c_int(node.subscript)
        return ir.Var(f"{at.name}[{offset:o}]", ir.Element(at.name, offset))

    def computed_call(self, node: c_ast.FuncCall) -> ir.ComputedCall:
        """((f *)e)(): call the routine at the address in e's address field,
        for f a function type declared with typedef."""
        cast = node.name
        t = cast.to_type.type
        sig = self.types.get(_base_type(t.type)) if isinstance(t, c_ast.PtrDecl) else None
        if sig is None:
            raise _err(node, "a computed call casts to a pointer to a function type declared with typedef")
        if sig.params or node.args:
            raise _err(node, "a computed call takes no arguments")
        if sig.conv is not ir.Conv.JSP:
            raise _err(node, "a computed call is `jsp`: the function type is JSP")
        return ir.ComputedCall(self.expr(cast.expr), sig)

    def shift_bits(self, node: c_ast.FuncCall, name: str) -> ir.Binary:
        """I_SCL_BITS(w & m): the count field w & m joined to `scl`, `ior (scl`."""
        args = node.args.exprs if node.args else []
        mask = args[0] if len(args) == 1 else None
        if not (isinstance(mask, c_ast.BinaryOp) and mask.op == "&"
                and any(is_c_int(m) and not to_word(c_int(m), m) & ~SHIFT_COUNT_FIELD
                        for m in (mask.left, mask.right))):
            raise _err(node, f"{name}(w & m): the count bits are w & m, m within "
                             f"{SHIFT_COUNT_FIELD:o}")
        return ir.Binary("|", self.expr(mask), ir.Insn(INSN_SHIFT_BITS[name]))

    def deref(self, node: c_ast.UnaryOp) -> ir.Deref:
        """*p for a pointer p held in a memory word or in a homed address field."""
        if isinstance(node.expr, c_ast.ID) and node.expr.name in self.arrays:
            raise _err(node, f"*{node.expr.name}: an array's name is its address, not a pointer word; "
                             "the instruction would reach through its first word")
        var = self.scope.lookup(node.expr) if isinstance(node.expr, c_ast.ID) else None
        if var is None or not isinstance(var.storage, ir.Memory + (ir.Homed,)) \
                or isinstance(var.storage, ir.HomedInsn):
            raise _err(node, "*p reads through a pointer p held in memory or a homed address field")
        return ir.Deref(var)

    def code_flags(self, node: c_ast.BinaryOp) -> ir.CodeRef:
        """f | c: a function's address with flag bits c above the address field."""
        flags = const_word(node.right)
        if flags & ir.ADDR_MASK:
            raise _err(node, f"{node.left.name} | {flags:o}: the flags must lie above the "
                             "address field (no bits in 07777)")
        return ir.CodeRef(self.sigs[node.left.name], flags, word=True)

    def home_of(self, node: c_ast.Node) -> ir.Var | None:
        """p for `home(p)` with p a HOMED pointer."""
        if not (isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID)
                and node.name.name == "home" and _builtin("home", self.sigs)):
            return None
        args = node.args.exprs if node.args else []
        if len(args) != 1 or not isinstance(args[0], c_ast.ID) or not self._homed(args[0].name):
            raise _err(node, "home(p) names a HOMED pointer p")
        return self.scope.lookup(args[0])

    def xct(self, node: c_ast.FuncCall, args: list[c_ast.Node]) -> ir.Xct:
        """xct(w, a) runs instruction word w on AC; xct(w, hi, lo) on AC:IO.
        w is an instruction constant, *home(p) for a HOMED pointer p (the
        `xct .` that holds p), or a HOMED shift (the word itself, run in place)."""
        if len(args) not in (2, 3):
            raise _err(node, "xct(w, a) or xct(w, hi, lo)")
        w = self.expr(args[0])
        if not (isinstance(w, ir.Insn)
                or (isinstance(w, ir.HomeLoad) and self.shifts.get(w.pointer.name) == SHIFT_POINTER)
                or (isinstance(w, ir.Var) and isinstance(w.storage, ir.HomedInsn))):
            raise _err(node, "xct runs a shift constructor, *home(p) for a pointer p to a shift, "
                             "or a HOMED shift")
        lo = self.lvalue(args[2]) if len(args) == 3 else None
        if lo is not None and not (isinstance(lo, ir.Var) and isinstance(lo.storage, ir.Io)):
            raise _err(node, "xct(w, hi, lo): lo is a register local")
        return ir.Xct(w, self.expr(args[1]), lo)

    def home_word(self, node: c_ast.FuncCall, op: str) -> ir.HomeWord | None:
        args = node.args.exprs if node.args else []
        if len(args) != 1:
            return None
        arg, inc = args[0], False
        if isinstance(arg, c_ast.UnaryOp) and arg.op == "++":
            arg, inc = arg.expr, True
        if isinstance(arg, c_ast.ID) and self._homed(arg.name):
            return ir.HomeWord(self.scope.lookup(arg), op, inc)
        return None

    def _is_variable(self, name: str) -> bool:
        return any(name in frame for frame in self.scope.frames)

    def _homed(self, name: str) -> bool:
        return any(isinstance(frame.get(name), ir.Homed) for frame in self.scope.frames) \
            and not self._is_local(name)

    def _is_local(self, name: str) -> bool:
        return any(name in frame for frame in self.scope.frames[1:])

    def call(self, node: c_ast.FuncCall, name: str) -> ir.Expr:
        args = node.args.exprs if node.args else []
        if name == "pdp1_swap":
            if len(args) != 1:
                raise _err(node, "SWAP(x) takes one value")
            return ir.Swapped(self.expr(args[0]))
        if name == "halt" and _builtin(name, self.sigs):
            if len(args) != 2:
                raise _err(node, "halt(ac, io) takes two arguments")
            io = self.lvalue(args[1])
            if not (isinstance(io, ir.Var) and isinstance(io.storage, ir.Io)):
                raise _err(node, "halt(ac, io): io is a register local")
            return ir.Halt(self.expr(args[0]), io)
        if name in HARDWARE and _builtin(name, self.sigs):
            if args:
                raise _err(node, f"{name}() takes no arguments")
            return ir.Hw(name)
        if name in DISPLAY and _builtin(name, self.sigs):
            want = 3 if name == "dpy" else 2
            if len(args) != want:
                raise _err(node, f"{name} takes {want} arguments")
            if name == "dpy_nowait":
                return ir.DpyNowait(self.expr(args[0]), self.lvalue(args[1]))
            intensity = c_int(args[2])
            if not 0 <= intensity <= MAX_INTENSITY:
                raise _err(node, "dpy(x, y, n): the intensity n is 0..7")
            return ir.Dpy(self.expr(args[0]), self.lvalue(args[1]), intensity)
        if name == "xct" and _builtin(name, self.sigs):
            return self.xct(node, args)
        if name in self.pointers and self._is_variable(name):
            sig = self.pointers[name]
            if len(args) != len(sig.params):
                raise _err(node, f"{name} points to a {sig.name}, which takes {len(sig.params)} arguments")
            return ir.IndirectCall(self.scope.lookup(node.name), sig, tuple(self.expr(a) for a in args))
        if name in PAIR_SHIFTS | PAIR_STEPS:
            if len(args) != 3:
                raise _err(node, f"{name}(hi, lo, x) takes three arguments")
            hi, lo = self.lvalue(args[0]), self.lvalue(args[1])
            if name in PAIR_SHIFTS:
                return ir.PairShift(name, hi, lo, c_int(args[2]))
            return ir.PairStep(name, hi, lo, self.expr(args[2]))
        if name in ir.AC_ROTATES | ir.IO_ROTATES:
            if len(args) != 2:
                raise _err(node, f"{name}(x, n) takes two arguments")
            return ir.Rot(name, self.lvalue(args[0]), c_int(args[1]))
        sig = self.sigs.get(name)
        if sig is None:
            raise _err(node, f"call of undeclared function {name!r}")
        if len(args) != len(sig.params):
            raise _err(node, f"{name} takes {len(sig.params)} arguments")
        return ir.Call(sig, tuple(self.expr(a) for a in args))


def _cases(node: c_ast.Switch, switch: str, its_cases: str) -> list[list[c_ast.Node]]:
    body = node.stmt.block_items or [] if isinstance(node.stmt, c_ast.Compound) else []
    cases: list[list[c_ast.Node]] = []
    for item in body:
        if isinstance(item, c_ast.Default) or not isinstance(item, c_ast.Case):
            raise _err(item, f"{switch} has cases 0..n and no default")
        if c_int(item.expr) != len(cases):
            raise _err(item, f"case {c_int(item.expr)}: {its_cases} are 0, 1, ... in order")
        cases.append(item.stmts or [])
    if len(cases) < 2:
        raise _err(node, f"{switch} has at least two cases")
    return cases


def _is_constant(node: c_ast.Node) -> bool:
    try:
        const_word(node)
    except DialectError:
        return False
    return True


def _array_root(node: c_ast.Node) -> c_ast.ID:
    while isinstance(node, c_ast.BinaryOp):
        node = node.left
    return node


def _builtin(name: str, sigs: dict[str, ir.Signature]) -> bool:
    """A hardware builtin is pdp1.h's, unless the program defines a function of that name."""
    return name not in sigs


def _mentions(node: c_ast.Node, name: str) -> bool:
    if isinstance(node, c_ast.ID) and node.name == name:
        return True
    return any(_mentions(child, name) for _, child in node.children())
