"""C AST -> IR. Resolves every name to a Storage from its declaration and
rejects anything outside the dialect with a message naming the construct."""
from __future__ import annotations

import re

from pycparser import c_ast, c_generator

from . import ir, macro

PAIR_SHIFTS = {"rcl", "rcr", "scl", "scr"}
PAIR_STEPS = {"mus", "dis"}
ROTATES = {"ral": "ac", "rar": "ac", "ril": "io", "rir": "io"}
BIN_OPS = {"+", "-", "&", "|", "^"}
MACRO_SYMBOL_LEN = 6
CMP_OPS = {"<", ">=", "==", "!=", "<=", ">"}
ATTR = re.compile(r"pdp1_(\w+)(?:\((.*)\))?$")
CONVS = {"jda", "block", "xct", "jsp"}
ATTRIBUTES = CONVS | {"byname", "sym", "entry_cell", "at", "reserve"}
HARDWARE = {"tyi", "lsm"}           # builtins that are one instruction with no operand
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
        return " ".join(t.type.names)
    return None


def c_int(node: c_ast.Node) -> int:
    """A compile-time C integer constant expression."""
    if isinstance(node, c_ast.Constant) and node.type == "int":
        text = node.value.rstrip("uUlL")
        return int(text, 8 if _is_octal(text) else 0)
    if isinstance(node, c_ast.UnaryOp) and node.op == "-":
        return -c_int(node.expr)
    raise _err(node, "expected a compile-time integer constant")


def _is_octal(text: str) -> bool:
    return len(text) > 1 and text[0] == "0" and text[1] not in "xXbB"


def const_word(node: c_ast.Node) -> int:
    """A constant word. Integer constants convert as C converts them, so -0 is
    +0; a cast to word makes the operators the machine's: -(word)0 is -0."""
    match node:
        case c_ast.Constant(type="int") | c_ast.UnaryOp(op="-", expr=c_ast.Constant()):
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
    convs = CONVS & attrs.keys()
    if len(convs) != 1:
        raise _err(decl, f"{decl.name}: a function needs exactly one calling convention "
                         "(JDA, JSP, XCT or BLOCK)")
    conv = convs.pop()
    ftype = decl.type
    params: list[ir.Param] = []
    for p in (ftype.args.params if ftype.args else []):
        if isinstance(p, c_ast.Typename) and _base_type(p.type) == "void":
            continue
        if _base_type(p.type) != "word":
            raise _err(p, f"{p.name}: a parameter must be a `word`")
        if "byname" in _attrs(p):
            kind = "byname"
        elif "register" in p.storage:
            kind = "io"
        else:
            kind = "ac"
        params.append(ir.Param(p.name, kind))
    kinds = [p.kind for p in params]
    if kinds.count("ac") > 1 or kinds.count("io") > 1:
        raise _err(decl, f"{decl.name}: at most one AC parameter and one register parameter")
    if kinds.count("byname") > 1:
        raise _err(decl, f"{decl.name}: more than one BYNAME parameter is not implemented yet")
    if "byname" in kinds and kinds[-1] != "byname":
        raise _err(decl, f"{decl.name}: BYNAME parameters come last, as the words after the call")
    if "byname" in kinds and conv in ("xct", "jsp"):
        raise _err(decl, f"{decl.name}: an {conv.upper()} function has no inline words")
    if "ac" in kinds and conv == "jsp":
        raise _err(decl, f"{decl.name}: a JSP function receives its return address in AC; "
                         "pass a register parameter")
    returns = _base_type(ftype.type)
    if returns not in ("word", "dword", "void"):
        raise _err(decl, f"{decl.name}: returns word, dword or void")
    if not symbol:
        return ir.Signature(decl.name, "", conv, tuple(params), returns, "")
    return ir.Signature(decl.name, _symbol(decl.name, attrs, namer, decl), conv, tuple(params),
                        returns, namer.fresh())


def lower_unit(ast: c_ast.FileAST, prefix: str = "z") -> ir.Unit:
    namer = Namer(prefix)
    sigs: dict[str, ir.Signature] = {}
    first: dict[str, c_ast.Decl] = {}
    for ext in ast.ext:
        decl = ext.decl if isinstance(ext, c_ast.FuncDef) else ext
        if isinstance(decl, c_ast.Decl) and _is_function(decl.type) and not _in_header(decl):
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
    objects = [e for e in ast.ext if isinstance(e, c_ast.Decl) and not _is_function(e.type)]
    seen: dict[str, c_ast.Decl] = {}
    for ext in objects:
        if ext.name in seen and _decl_attrs(ext) != _decl_attrs(seen[ext.name]):
            raise _err(ext, f"{ext.name}: declarations disagree with the one at {seen[ext.name].coord}")
        seen.setdefault(ext.name, ext)
        if (fn_type := _pointee(ext.type, types)) is not None:
            pointers[ext.name] = fn_type
    for ext in objects:                       # definitions first: an extern may precede one
        attrs = _attrs(ext)
        if "entry_cell" in attrs:
            owner = sigs.get(attrs["entry_cell"])
            if owner is None or owner.conv != "jda" or not any(p.kind == "ac" for p in owner.params):
                raise _err(ext, f"{ext.name}: ENTRY_CELL names a JDA function with an AC "
                                "parameter, declared above")
            globals_[ext.name] = ir.Entry(owner.sym, alias=True)
        elif ext.init is not None or "reserve" in attrs:
            globals_[ext.name] = ir.Placed(_symbol(ext.name, attrs, namer, ext))
    for ext in objects:
        if ext.name in globals_:
            continue
        attrs = _attrs(ext)
        if "extern" not in ext.storage:
            raise _err(ext, f"{ext.name}: uninitialized file-scope object "
                            "(pool variable) is not in the implemented dialect yet")
        if not MACRO_SYMBOL.fullmatch(ext.name) and "sym" not in attrs:
            raise _err(ext, f"{ext.name}: an extern names unlifted text; give it SYM(\"x\")")
        globals_[ext.name] = ir.Extern(_symbol(ext.name, attrs, namer, ext))

    items: list[ir.TopItem] = []
    for ext in ast.ext:
        if isinstance(ext, c_ast.FuncDef):
            fn = _lower_function(ext, sigs[ext.decl.name], globals_, sigs, pointers, namer)
            items.append(ir.Function(fn.sig, fn.params, fn.body, _origin(ext.decl)))
        elif isinstance(ext, c_ast.Decl) and not _is_function(ext.type):
            attrs = _attrs(ext)
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
            if _base_type(ext.type) != "word":
                raise _err(ext, f"{ext.name}: only `word` objects can be placed")
            items.append(ir.Datum(storage.sym, const_word(ext.init), ext.name, _origin(ext)))
    return ir.Unit(tuple(items), sigs, namer.counter, globals_)


def _decl_attrs(decl: c_ast.Decl) -> dict[str, str]:
    """Attributes every declaration of an object repeats: all but placement."""
    return {k: v for k, v in _attrs(decl).items() if k not in ("at", "reserve")}


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
        raise _err(t, "a pointer must point to a function type declared with typedef")
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
                    namer: Namer) -> ir.Function:
    scope = _Scope(globals_)
    frame: dict[str, ir.Storage] = {}
    params: list[ir.Var] = []
    for p in sig.params:
        if p.kind == "ac":
            storage = ir.Entry(sig.sym) if sig.conv == "jda" else ir.Acc(p.name)
        elif p.kind == "io":
            storage = ir.Io(p.name)
        else:
            storage = ir.ByName(p.name)
        frame[p.name] = storage
        params.append(ir.Var(p.name, storage))
    scope.frames.append(frame)
    lowerer = _Lowerer(scope, sigs, pointers, namer)
    body = lowerer.block(fn.body)
    if missing := lowerer.labels_used - lowerer.labels_defined:
        raise _err(fn, f"{sig.name}: goto to undefined label(s) {sorted(missing)}")
    return ir.Function(sig, tuple(params), body)


class _Lowerer:
    def __init__(self, scope: _Scope, sigs: dict[str, ir.Signature],
                 pointers: dict[str, ir.Signature], namer: Namer):
        self.scope, self.sigs, self.pointers, self.namer = scope, sigs, pointers, namer
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
        match node:
            case c_ast.Compound():
                return self.block(node)
            case c_ast.Decl():
                return self.local(node)
            case c_ast.Assignment(op="="):
                return self.assign(node.lvalue, self.expr(node.rvalue), node)
            case c_ast.Assignment(op="+=" | "-="):
                target = self.expr(node.lvalue)
                return self.assign(node.lvalue, ir.Binary(node.op[0], target, self.expr(node.rvalue)), node)
            case c_ast.FuncCall(name=c_ast.ID(name="skip_return")):
                return ir.SkipReturn()
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
        return ir.Unroll(c_int(node.cond.right), self.stmt(node.stmt))

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
        if kind != "word":
            raise _err(node, f"{node.name}: locals must be `word` or `dword`")
        storage = ir.Io(node.name) if "register" in node.storage else ir.Acc(node.name)
        self.scope.frames[-1][node.name] = storage
        if node.init is None:
            return None
        return ir.Assign(ir.Var(node.name, storage), self.expr(node.init))

    def pair_halves(self, node: c_ast.ID) -> tuple[ir.Var, ir.Var]:
        return (self.scope.lookup(c_ast.ID(node.name + ".hi", node.coord)),
                self.scope.lookup(c_ast.ID(node.name + ".lo", node.coord)))

    def lvalue(self, node: c_ast.Node) -> ir.Var:
        if isinstance(node, c_ast.StructRef) and node.type == "." and isinstance(node.name, c_ast.ID) \
                and node.name.name in self.scope.pairs and node.field.name in ("hi", "lo"):
            return self.scope.lookup(c_ast.ID(f"{node.name.name}.{node.field.name}", node.coord))
        if not isinstance(node, c_ast.ID):
            raise _err(node, "only plain names and dword halves can be assigned")
        var = self.scope.lookup(node)
        if isinstance(var.storage, ir.ByName):
            raise _err(node, f"{node.name}: a BYNAME parameter is the caller's word and cannot be assigned")
        return var

    def cond(self, node: c_ast.Node) -> ir.Compare:
        if isinstance(node, c_ast.BinaryOp) and node.op in CMP_OPS:
            if to_word(c_int(node.right), node.right) != 0:
                raise _err(node, "conditions compare with 0 only (the skip group)")
            return ir.Compare(node.op, self.expr(node.left))
        raise _err(node, "a condition must be `e <op> 0`")

    # --------------------------------------------------------- expressions
    def expr(self, node: c_ast.Node) -> ir.Expr:
        match node:
            case c_ast.Constant(type="int"):
                return ir.Const(to_word(c_int(node), node))
            case c_ast.Cast() | c_ast.UnaryOp(op="-" | "~", expr=c_ast.Cast()):
                return ir.Const(const_word(node))
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
        raise _err(node, f"expression {type(node).__name__} is not in the implemented dialect yet")

    def _is_variable(self, name: str) -> bool:
        return any(name in frame for frame in self.scope.frames)

    def call(self, node: c_ast.FuncCall, name: str) -> ir.Expr:
        args = node.args.exprs if node.args else []
        if name in HARDWARE and _in_header_name(name, self.sigs):
            if args:
                raise _err(node, f"{name}() takes no arguments")
            return ir.Hw(name)
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
                return ir.PairOp(name, hi, lo, count=c_int(args[2]))
            return ir.PairOp(name, hi, lo, operand=self.expr(args[2]))
        if name in ROTATES:
            if len(args) != 2:
                raise _err(node, f"{name}(x, n) takes two arguments")
            return ir.Rot(name, self.lvalue(args[0]), c_int(args[1]))
        sig = self.sigs.get(name)
        if sig is None:
            raise _err(node, f"call of undeclared function {name!r}")
        if len(args) != len(sig.params):
            raise _err(node, f"{name} takes {len(sig.params)} arguments")
        return ir.Call(sig, tuple(self.expr(a) for a in args))


def _in_header_name(name: str, sigs: dict[str, ir.Signature]) -> bool:
    """A hardware builtin is pdp1.h's, unless the program defines a function of that name."""
    return name not in sigs


def _mentions(node: c_ast.Node, name: str) -> bool:
    if isinstance(node, c_ast.ID) and node.name == name:
        return True
    return any(_mentions(child, name) for _, child in node.children())
