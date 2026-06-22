import ast, tokenize, io, decimal, inspect, mpmath, re
threading = None
time      = None

dec           = decimal.Decimal
ctx           = decimal.getcontext()
ctx.prec      = 50
DISPLAY_PREC  = 30
mpmath.mp.dps = 55

ISO_INLINE   = True
GUARD_DIGITS = 20
IMG          = False

RED    = "\x1b[38;2;255;0;0m"
YELLOW = "\x1b[38;2;204;204;0m"
BRBL   = "\x1b[38;2;0;150;255m"
LSBL   = "\x1b[38;2;94;140;255m"
GREEN  = "\x1b[38;2;60;180;80m"
GRAY   = "\x1b[38;2;104;104;104m"
VIOLET = "\x1b[38;2;238;50;238m"
WHITE  = "\x1b[38;2;250;250;250m"
BOLD   = "\x1b[1m"
RST    = "\x1b[0m"


class Tok:
    __slots__ = ('type', 'string')
    def __init__(self, type_: int, string: str):
        self.type   = type_
        self.string = string
    def __repr__(self):
        return f'Tok({self.type}, {self.string!r})'

class _MissingArgs:
    __slots__ = ('lam', 'provided', 'missing')
    def __init__(self, lam, provided: tuple, missing: list):
        self.lam      = lam
        self.provided = provided
        self.missing  = missing
    def __repr__(self):
        names = ', '.join(_longvar_inner(p) if _is_longvar(p) else p for p in self.missing)
        return f"{RED}Invalid syntax: missing argument(s): {names}{RST}"
    def __str__(self):
        return self.__repr__()

class SubProxy:
    __slots__ = ('name', 'env')
    def __init__(self, name: str, env: dict):
        self.name = name
        self.env  = env
    def __getitem__(self, key):
        k = f"{self.name}[{int(key)}]"
        if k in self.env:
            return self.env[k]
        raise NameError(f"'{k}' is not defined")
    def __repr__(self):
        return f"SubProxy({self.name!r})"

class _DisplayDec(dec):
    def __str__(self):
        s, d, e = self.as_tuple()
        order = e + len(d) - 1
        if e < 0 and abs(order) < DISPLAY_PREC:
            return format(self, 'f')
        return super().__str__()
    def __repr__(self):
        return self.__str__()


def get_sub_specs(s: str) -> list:
    specs  = []
    seen   = set()
    tokens = get_clean_tokens(s)
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if (t.type == tokenize.NAME and t.string not in dco and
                i + 1 < len(tokens) and
                tokens[i+1].type == tokenize.OP and
                tokens[i+1].string == '['):
            j = i + 2
            depth = 1
            while j < len(tokens):
                if   tokens[j].string == '[': depth += 1
                elif tokens[j].string == ']':
                    depth -= 1
                    if depth == 0: break
                j += 1
            index_expr = ''.join(tk.string for tk in tokens[i+2:j])
            key = (t.string, index_expr)
            if key not in seen:
                specs.append((t.string, index_expr))
                seen.add(key)
            i = j + 1
            continue
        i += 1
    return specs

_lv_to_mangled = {}
_mangled_to_lv = {}

def _register_longvar(inner: str) -> str:
    if inner not in _lv_to_mangled:
        n   = len(_lv_to_mangled)
        m   = f"XLONGx{n}x"
        _lv_to_mangled[inner] = m
        _mangled_to_lv[m]     = inner
    return _lv_to_mangled[inner]

def _is_longvar(s: str) -> bool:
    return s in _mangled_to_lv

def _longvar_inner(s: str) -> str:
    return _mangled_to_lv.get(s, s)

def _preprocess_lv(s: str) -> str:
    buf = []
    i = 0
    while i < len(s):
        if s[i] == '_':
            j = s.find('_', i + 1)
            if j > i:
                buf.append(_register_longvar(s[i+1:j]))
                i = j + 1
            else:
                buf.append('_')
                i += 1
        else:
            buf.append(s[i])
            i += 1
    return re.sub(r'(XLONGx\d+x)(\d)', r'\1*\2', ''.join(buf))

def _split_alnum(s: str) -> list:
    raw_segs = []
    i = 0
    while i < len(s):
        if s[i].isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            raw_segs.append((tokenize.NUMBER, s[i:j]))
            i = j
        else:
            j = i
            while j < len(s) and not s[j].isdigit():
                j += 1
            raw_segs.append(('LETTERS', s[i:j]))
            i = j

    result = []
    for kind, val in raw_segs:
        if kind == tokenize.NUMBER:
            result.append(Tok(tokenize.NUMBER, val))
        elif _is_longvar(val):
            result.append(Tok(tokenize.NAME, val))
        else:
            result.extend(_greedy_name(val))
    return result


def _greedy_name(s: str) -> list:
    result = []
    i = 0
    while i < len(s):
        matched = False
        for length in range(len(s) - i, 1, -1):
            candidate = s[i:i+length]
            if candidate in dco:
                result.append(Tok(tokenize.NAME, candidate))
                i += length
                matched = True
                break
        if not matched:
            result.append(Tok(tokenize.NAME, s[i]))
            i += 1
    return result


def _should_split(name: str) -> bool:
    if not any(c.isdigit() for c in name):
        return False
    if name not in dco or not callable(dco[name]):
        return False
    i = 0
    while i < len(name) and not name[i].isdigit():
        i += 1
    letter_part = name[:i]
    if not letter_part:
        return False
    toks = _greedy_name(letter_part)
    return all(t.string in dco and not callable(dco[t.string]) for t in toks)


_TOK_STRING = 200                                              

def get_clean_tokens(s: str) -> list:
    s = _preprocess_lv(s)
    s = re.sub(r'(\d)(_[A-Za-z])', r'\1 \2', s)
    raw_tokens = []
    try:
        gen = tokenize.tokenize(io.BytesIO(s.encode('utf-8')).readline)
        for t in gen:

            if t.type == tokenize.STRING:
                inner = t.string[1:-1]                             
                raw_tokens.append(Tok(_TOK_STRING, inner))
                continue

            if t.type not in (tokenize.NUMBER, tokenize.NAME, tokenize.OP):
                continue

            if t.type == tokenize.NUMBER and t.string.lower().endswith('j') and not IMG:
                coeff = t.string[:-1]
                if coeff:
                    raw_tokens.append(Tok(tokenize.NUMBER, coeff))
                raw_tokens.append(Tok(tokenize.NAME, t.string[-1]))
                continue

            if t.type == tokenize.NAME:
                if _is_longvar(t.string):
                    raw_tokens.append(Tok(t.type, t.string))
                    continue
                if t.string not in dco:
                    has_digit = any(c.isdigit() for c in t.string)
                    if has_digit:
                        raw_tokens.extend(_split_alnum(t.string))
                        continue
                    if len(t.string) > 1:
                        raw_tokens.extend(_greedy_name(t.string))
                        continue
                elif _should_split(t.string):
                    raw_tokens.extend(_split_alnum(t.string))
                    continue

            raw_tokens.append(Tok(t.type, t.string))

    except tokenize.TokenError:
        pass

    merged = []
    i = 0
    while i < len(raw_tokens):
        t0 = raw_tokens[i]
        if (i + 2 < len(raw_tokens)
                and t0.type == tokenize.NUMBER
                and raw_tokens[i+1].type == tokenize.OP
                and raw_tokens[i+1].string == '.'
                and raw_tokens[i+2].type == tokenize.NUMBER
                and '.' not in t0.string
                and '.' not in raw_tokens[i+2].string):
            merged.append(Tok(tokenize.NUMBER, t0.string + '.' + raw_tokens[i+2].string))
            i += 3
        elif (i + 1 < len(raw_tokens)
                and t0.type == tokenize.NUMBER
                and raw_tokens[i+1].type == tokenize.NUMBER
                and raw_tokens[i+1].string.startswith('.')
                and '.' not in t0.string):
            merged.append(Tok(tokenize.NUMBER, t0.string + raw_tokens[i+1].string))
            i += 2
        else:
            merged.append(t0)
            i += 1
    return merged


def getv(s: str) -> list:
    found  = set()
    tokens = get_clean_tokens(s)
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.type == tokenize.NAME:
            if (i + 1 < len(tokens) and
                    tokens[i+1].type == tokenize.OP and
                    tokens[i+1].string == '['):
                j = i + 2
                depth = 1
                while j < len(tokens):
                    if   tokens[j].string == '[': depth += 1
                    elif tokens[j].string == ']':
                        depth -= 1
                        if depth == 0: break
                    j += 1
                for it in tokens[i+2:j]:
                    if it.type == tokenize.NAME:
                        if (len(it.string) == 1 and it.string not in dco) or _is_longvar(it.string):
                            found.add(it.string)
                i = j + 1
                continue
            elif (len(t.string) == 1 and t.string not in dco) or _is_longvar(t.string):
                found.add(t.string)
        i += 1
    return sorted(found)

def _get_lambda_params(expr: str) -> list:
    found  = set()
    tokens = get_clean_tokens(expr)
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.type == tokenize.NAME:
            if (i + 1 < len(tokens) and
                    tokens[i+1].type == tokenize.OP and
                    tokens[i+1].string == '['):
                j = i + 2
                depth = 1
                while j < len(tokens):
                    if   tokens[j].string == '[': depth += 1
                    elif tokens[j].string == ']':
                        depth -= 1
                        if depth == 0: break
                    j += 1
                idx_toks = tokens[i+2:j]
                for it in idx_toks:
                    if it.type == tokenize.NAME:
                        if (len(it.string) == 1 and it.string not in dco) or _is_longvar(it.string):
                            found.add(it.string)
                if len(idx_toks) == 1 and idx_toks[0].type == tokenize.NUMBER:
                    found.add(f"{t.string}[{idx_toks[0].string}]")
                i = j + 1
                continue
            elif (len(t.string) == 1 and t.string not in dco) or _is_longvar(t.string):
                found.add(t.string)
        i += 1
    return sorted(found)


class Lambda:
    def __init__(self, expr: str, params: list = None):
        self.expr   = expr
        self.params = list(params) if params is not None else _get_lambda_params(expr)


    def __call__(self, *args):
        if self.params and len(args) < len(self.params):
            return _MissingArgs(self, args, self.params[len(args):])
        v = {}
        for name, val in zip(self.params, args):
            if isinstance(val, dec):
                v[name] = val
            elif isinstance(val, mpmath.mpf):
                v[name] = dec(mpmath.nstr(val, ctx.prec + 5))
            elif isinstance(val, (int, float)):
                v[name] = dec(str(val))
            else:
                v[name] = val                              
        return cal(self.expr, v)                                  


    def _arith(self, other, op: str, flipped: bool = False):
        if isinstance(other, Lambda):
            params = list(self.params)
            for p in other.params:
                if p not in params:
                    params.append(p)
            a, b = (other.expr, self.expr) if flipped else (self.expr, other.expr)
            return Lambda(f"({a}) {op} ({b})", params)
        if isinstance(other, dec):
            if flipped:
                return Lambda(f"{other} {op} ({self.expr})", self.params)
            return Lambda(f"({self.expr}) {op} {other}", self.params)
        return NotImplemented

    def __add__(self, o):      return self._arith(o, '+')
    def __radd__(self, o):     return self._arith(o, '+', True)
    def __sub__(self, o):      return self._arith(o, '-')
    def __rsub__(self, o):     return self._arith(o, '-', True)
    def __mul__(self, o):      return self._arith(o, '*')
    def __rmul__(self, o):     return self._arith(o, '*', True)
    def __truediv__(self, o):  return self._arith(o, '/')
    def __rtruediv__(self, o): return self._arith(o, '/', True)
    def __pow__(self, o):      return self._arith(o, '**')
    def __rpow__(self, o):     return self._arith(o, '**', True)
    def __neg__(self):         return Lambda(f"-({self.expr})", self.params)
    def __pos__(self):         return Lambda(self.expr, self.params)

    def __repr__(self):
        return f'{GREEN}"{self.expr}"{RST}'
    def __str__(self):
        return self.__repr__()


dco = {
    name: getattr(ctx, name)
    for name in dir(ctx)
    if not name.startswith('_') and callable(getattr(ctx, name))
}


def spdwarn():
    global threading, time
    canwrn  = False
    success = [False]
    if threading is None or time is None:
        try:
            import threading as thr, time as tim
            threading = thr; time = tim; canwrn = True
        except ImportError: pass
    else: canwrn = True
    if canwrn:
        def wrn(suc, timeout=4):
            time.sleep(timeout)
            if not suc[0]:
                print(f"{YELLOW}Speed tip: install gmpy2{RST}")
        threading.Thread(target=wrn, args=(success,), daemon=True).start()
    return success


def _make_wrapper(func):
    def wrapper(*args):
        try:
            mp_args = [a if isinstance(a, mpmath.mpc) else mpmath.mpf(str(a)) for a in args]
            result  = func(*mp_args)
            if isinstance(result, mpmath.mpc):
                return result
            result = dec(str(result))
            if abs(result) < dec("1e-49"):
                return dec(0)
            return result
        except Exception:
            raise
    return wrapper


for _name in dir(mpmath):
    if _name.startswith('_'):
        continue
    _obj = getattr(mpmath, _name)
    if isinstance(_obj, mpmath.ctx_mp_python.mpnumeric):
        try:
            _s = mpmath.nstr(_obj, 55, strip_zeros=False)
            if 'j' not in _s:
                dco[_name] = dec(_s)
                continue
        except Exception:
            pass
    if callable(_obj) and not inspect.isclass(_obj):
        dco[_name] = _make_wrapper(_obj)


def _int(x):  return dec(int(x))
def _round(x, n=dec(0)):
    return x.quantize(dec(10) ** -int(n), rounding=decimal.ROUND_HALF_EVEN)

dco['int']    = _int
dco['round']  = _round
dco['rad']    = dco['radians']
dco['deg']    = dco['degrees']
dco['repeat'] = lambda *_: _fmt_error("repeat() must be a top-level call: repeat(expr, n)")
dco['true']   = True
dco['false']  = False

if IMG:
    dco['j'] = mpmath.mpc(0, 1)


def _to_dec(v):
    return dec(mpmath.nstr(v, mpmath.mp.dps))

def _repin_constants():
    dco['e']     = _to_dec(mpmath.exp(1))
    dco['pi']    = _to_dec(mpmath.pi)
    dco['phi']   = _to_dec(mpmath.phi)
    dco['euler'] = _to_dec(mpmath.euler)
    dco['hbar']  = dec('1')

_repin_constants()
dco.pop('inf', None)
dco.pop('nan', None)


def _hydrogen_e(n):
    n = int(n)
    if n < 1: return _fmt_error("hydrogen_e: n must be ≥ 1")
    return _to_dec(mpmath.mpf('-1') / (2 * n * n))
dco['hydrogen_e'] = _hydrogen_e


def _solve_anharmonic(n, c):
    n = int(n); c = mpmath.mpf(str(c))
    N = max(60, n + 50)
    A = mpmath.matrix(N, N)
    for i in range(N):
        A[i, i] = (i + mpmath.mpf('0.5')) + c * (6*i*i + 6*i + 3) / 4
        if i + 2 < N:
            v2 = c * (2*i + 3) * mpmath.sqrt((i+1)*(i+2)) / 2
            A[i, i+2] = v2; A[i+2, i] = v2
        if i + 4 < N:
            v4 = c * mpmath.sqrt((i+1)*(i+2)*(i+3)*(i+4)) / 4
            A[i, i+4] = v4; A[i+4, i] = v4
    E, _ = mpmath.eigsy(A)
    vals  = sorted([E[i] for i in range(N)], key=lambda v: float(mpmath.re(v)))
    return dec(mpmath.nstr(vals[n], mpmath.mp.dps))
dco['anharmonic'] = _solve_anharmonic


def _solve_schrodinger(V_expr, n, xmin, xmax, Npts=100):
    n = int(n); Npts = int(Npts)
    xmin_m = mpmath.mpf(str(xmin)); xmax_m = mpmath.mpf(str(xmax))
    dx      = (xmax_m - xmin_m) / (Npts + 1)
    inv_dx2 = 1 / dx**2
    H = mpmath.matrix(Npts, Npts)
    for i in range(Npts):
        xi = xmin_m + (i + 1) * dx
        vi = cal(V_expr, {'x': dec(mpmath.nstr(xi, 30))}, nodisplay=True)
        Vi = mpmath.mpf(str(vi)) if isinstance(vi, dec) else mpmath.mpf('0')
        H[i, i] = inv_dx2 + Vi
        if i + 1 < Npts:
            H[i, i+1] = -inv_dx2 / 2; H[i+1, i] = -inv_dx2 / 2
    E, _ = mpmath.eigsy(H)
    vals  = sorted([E[i] for i in range(Npts)], key=lambda v: float(mpmath.re(v)))
    if n >= len(vals): return _fmt_error(f"n={n} out of range (max {len(vals)-1})")
    return dec(mpmath.nstr(vals[n], mpmath.mp.dps))


def _simp(node):
    if isinstance(node, ast.BinOp):
        L, R = _simp(node.left), _simp(node.right)
        op   = node.op
        lz = isinstance(L, ast.Constant) and L.value == 0
        rz = isinstance(R, ast.Constant) and R.value == 0
        lo = isinstance(L, ast.Constant) and L.value == 1
        ro = isinstance(R, ast.Constant) and R.value == 1

        if isinstance(op, ast.Add):
            if lz: return R
            if rz: return L
        elif isinstance(op, ast.Sub):
            if rz: return L
            if lz: return ast.UnaryOp(ast.USub(), R)
        elif isinstance(op, ast.Mult):
            if lz or rz: return ast.Constant(value=0)
            if lo: return R
            if ro: return L
        elif isinstance(op, ast.Div):
            if lz: return ast.Constant(value=0)
            if ro: return L
        elif isinstance(op, ast.Pow):
            if rz: return ast.Constant(value=1)
            if ro: return L
            if lz: return ast.Constant(value=0)


        if isinstance(L, ast.Constant) and isinstance(R, ast.Constant):
            try:
                v = eval(ast.unparse(ast.BinOp(L, op, R)))                      
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return ast.Constant(value=v)
            except Exception:
                pass

        node.left, node.right = L, R
        return node

    elif isinstance(node, ast.UnaryOp):
        op  = _simp(node.operand)
        if isinstance(node.op, ast.USub):
            if isinstance(op, ast.Constant):   return ast.Constant(value=-op.value)
            if isinstance(op, ast.UnaryOp) and isinstance(op.op, ast.USub):
                return op.operand                         
        elif isinstance(node.op, ast.UAdd):
            return op
        node.operand = op
        return node

    elif isinstance(node, ast.Call):
        node.args = [_simp(a) for a in node.args]
        return node

    return node


def _C(name, *args):
    return ast.Call(ast.Name(name, ast.Load()), list(args), [])


def _diff_node(node, var: str):
    if isinstance(node, ast.Constant):
        return ast.Constant(value=0)

    if isinstance(node, ast.Name):
        return ast.Constant(value=1 if node.id == var else 0)

    if isinstance(node, ast.UnaryOp):
        d = _diff_node(node.operand, var)
        if isinstance(node.op, ast.USub):
            return _simp(ast.UnaryOp(ast.USub(), d))
        return d

    if isinstance(node, ast.BinOp):
        L, R   = node.left, node.right
        dL, dR = _diff_node(L, var), _diff_node(R, var)
        op     = node.op

        if isinstance(op, (ast.Add, ast.Sub)):
            return _simp(ast.BinOp(dL, op, dR))

        if isinstance(op, ast.Mult):                         
            return _simp(ast.BinOp(
                ast.BinOp(dL, ast.Mult(), R),
                ast.Add(),
                ast.BinOp(L, ast.Mult(), dR)))

        if isinstance(op, ast.Div):                           
            return _simp(ast.BinOp(
                ast.BinOp(
                    ast.BinOp(dL, ast.Mult(), R),
                    ast.Sub(),
                    ast.BinOp(L, ast.Mult(), dR)),
                ast.Div(),
                ast.BinOp(R, ast.Pow(), ast.Constant(value=2))))

        if isinstance(op, ast.Pow):
            dR_s = _simp(dR)
            if isinstance(dR_s, ast.Constant) and dR_s.value == 0:

                return _simp(ast.BinOp(
                    ast.BinOp(R, ast.Mult(),
                        ast.BinOp(L, ast.Pow(),
                            _simp(ast.BinOp(R, ast.Sub(), ast.Constant(value=1))))),
                    ast.Mult(), _simp(dL)))

            dL_s = _simp(dL)
            inner = _simp(ast.BinOp(
                ast.BinOp(dR_s, ast.Mult(), _C('log', L)),
                ast.Add(),
                ast.BinOp(ast.BinOp(R, ast.Mult(), dL_s), ast.Div(), L)))
            return _simp(ast.BinOp(node, ast.Mult(), inner))

    if isinstance(node, ast.Call):
        fn = node.func.id if isinstance(node.func, ast.Name) else None
        if fn and len(node.args) == 1:
            f  = node.args[0]
            df = _simp(_diff_node(f, var))
            if isinstance(df, ast.Constant) and df.value == 0:
                return ast.Constant(value=0)
            one_df = isinstance(df, ast.Constant) and df.value == 1

            def chain(d_out):
                return _simp(d_out if one_df else
                             ast.BinOp(d_out, ast.Mult(), df))

            sq   = lambda e: ast.BinOp(e, ast.Pow(), ast.Constant(value=2))
            inv  = lambda e: ast.BinOp(ast.Constant(value=1), ast.Div(), e)
            rule = {
                'sin':   lambda: chain(_C('cos', f)),
                'cos':   lambda: chain(ast.UnaryOp(ast.USub(), _C('sin', f))),
                'tan':   lambda: chain(inv(sq(_C('cos', f)))),
                'exp':   lambda: chain(_C('exp', f)),
                'log':   lambda: chain(inv(f)),
                'sqrt':  lambda: chain(inv(ast.BinOp(
                             ast.Constant(value=2), ast.Mult(), _C('sqrt', f)))),
                'asin':  lambda: chain(inv(_C('sqrt',
                             ast.BinOp(ast.Constant(1),ast.Sub(),sq(f))))),
                'acos':  lambda: chain(ast.UnaryOp(ast.USub(), inv(_C('sqrt',
                             ast.BinOp(ast.Constant(1),ast.Sub(),sq(f)))))),
                'atan':  lambda: chain(inv(
                             ast.BinOp(ast.Constant(1),ast.Add(),sq(f)))),
                'sinh':  lambda: chain(_C('cosh', f)),
                'cosh':  lambda: chain(_C('sinh', f)),
                'tanh':  lambda: chain(inv(sq(_C('cosh', f)))),
                'log10': lambda: chain(inv(ast.BinOp(f, ast.Mult(),
                             _C('log', ast.Constant(value=10))))),
                'log2':  lambda: chain(inv(ast.BinOp(f, ast.Mult(),
                             _C('log', ast.Constant(value=2))))),
            }
            if fn in rule:
                return rule[fn]()

    if isinstance(node, ast.Subscript):
        try:
            return ast.Constant(value=1 if ast.unparse(node) == var else 0)
        except Exception:
            return ast.Constant(value=0)

    return ast.Constant(value=0)


def _symbolic_diff(expr_str: str, var: str, order: int = 1) -> str:
    try:
        tree = ast.parse(expr_str, mode='eval')
        node = tree.body
        for _ in range(order):
            node = _diff_node(node, var)
            node = _simp(node)
        ast.fix_missing_locations(node)
        return ast.unparse(node)
    except Exception as err:
        return f"\x1b[38;2;255;0;0mSymbolic diff error: {err}\x1b[0m"


def _diff_lambda(f, order=None):
    if not isinstance(f, Lambda):
        return _fmt_error("diff() expects a Lambda (quoted expression).  "
                          "Example:  f=\"sin(x)\"  then  diff(f)")
    if not f.params:
        return Lambda("0", [])
    var    = f.params[0]
    n      = int(order) if isinstance(order, dec) else 1
    d_expr = _symbolic_diff(f.expr, var, n)
    if d_expr.startswith('\x1b'):
        return d_expr                                     
    return Lambda(d_expr, f.params)

dco['diff'] = _diff_lambda


def _cal_mpf(expr: str, var: str, t):
    _env = {}
    for _n in dir(mpmath):
        if _n.startswith('_'): continue
        _o = getattr(mpmath, _n)
        if callable(_o) and not inspect.isclass(_o):
            _env[_n] = _o
        elif isinstance(_o, mpmath.ctx_mp_python.mpnumeric):
            _env[_n] = _o
    _env.update({'pi': mpmath.pi, 'e': mpmath.exp(1), 'phi': mpmath.phi,
                 'euler': mpmath.euler, 'mpmath': mpmath})
    _env[var] = t

    _tokens = get_clean_tokens(expr)
    _parts  = []
    for _idx, _tok in enumerate(_tokens):
        if _idx > 0:
            _pv = _tokens[_idx-1]
            _pm = (_pv.type in (tokenize.NUMBER,) or _pv.string == ')')
            _pn = _pv.type == tokenize.NAME
            _cm = _tok.type == tokenize.NUMBER or _tok.string == '('
            _cn = _tok.type == tokenize.NAME
            _mul = (_pm and _cn) or (_pn and _cm) or (_pn and _cn)
            if _mul and _tok.string == '(' and _pn:
                if callable(_env.get(_pv.string)):
                    _mul = False
            if _mul: _parts.append('*')
        if _tok.type == tokenize.NUMBER:
            _parts.append(f'mpmath.mpf("{_tok.string}")')
        else:
            _parts.append(_tok.string)
    try:
        _r = eval(''.join(_parts), {'__builtins__': {}}, _env)
        return _r if isinstance(_r, (mpmath.mpf, mpmath.mpc)) else mpmath.mpf(str(_r))
    except Exception:
        return mpmath.mpf('0')


_user_vars:   dict  = {}                                           
_last_lambda: list  = [None]                                       


def _fmt_error(msg: str) -> str:
    return f"{RED}{msg}{RST}"


print(f"""Arbitrary-precision mathematical expression REPL.
{GRAY}Commands: help / new / toggle / img (activates constant j) / prec <n> / clear
Operators: + − * / **
Variables: single letters / word in underscores
Subscript: e.g. x[1] / _work_[0]
Inline: e.g. x=0 (when setting a variable) / f=\"sin(x)\"; f(rad(x)){RST}\n""")


def _display(result: dec) -> dec:
    if result == 0:
        return _DisplayDec(0)

    sign, digits, exponent = result.as_tuple()
    num_digits = len(digits)
    order = exponent + num_digits - 1

    quantizer_exp = order - (DISPLAY_PREC - 1)
    try:
        rounded = result.quantize(dec(10) ** quantizer_exp, rounding=decimal.ROUND_HALF_EVEN)
    except (decimal.InvalidOperation, decimal.Overflow):
        rounded = result

    if rounded == 0:
        return _DisplayDec(0)

    normalized = rounded.normalize()
    sign2, digits2, exponent2 = normalized.as_tuple()
    order2 = exponent2 + len(digits2) - 1

    if exponent2 >= 0 and abs(order2) < DISPLAY_PREC:
        return _DisplayDec(int(normalized))

    return _DisplayDec(normalized)


def _display_complex(result: mpmath.mpc) -> str:
    re     = _display(dec(mpmath.nstr(result.real, mpmath.mp.dps)))
    im_raw = dec(mpmath.nstr(result.imag, mpmath.mp.dps))
    im     = _display(abs(im_raw))
    if re == 0:
        return f"-{im}j" if im_raw < 0 else f"{im}j"
    sign = '+' if im_raw >= 0 else '-'
    return f"{re}{sign}{im}j"


def cal(expr: str, v_dict: dict = None, chk: bool = False, nodisplay: bool = False):
    if v_dict is None:
        v_dict = {}

    if expr.strip().startswith('repeat(') and expr.strip().endswith(')'):
        return _eval_repeat(expr.strip(), v_dict, chk)

    try:
        tokens = get_clean_tokens(expr)
        if not tokens and expr.strip():
            return _fmt_error("The given expression has invalid syntax.")

        env = {**dco, **v_dict, 'dec': dec, 'mpmath': mpmath, 'Lambda': Lambda}

        for idx in range(len(tokens) - 2):
            t0, t1, t2 = tokens[idx], tokens[idx+1], tokens[idx+2]
            if (t0.type == tokenize.NAME and t1.type == tokenize.OP and t1.string == '('
                    and t2.type == tokenize.OP and t2.string == ')'):
                target = env.get(t0.string)
                if target is not None and not callable(target):
                    if chk: return dec(1)
                    disp = _longvar_inner(t0.string) if _is_longvar(t0.string) else t0.string
                    return _fmt_error(f"'{disp}' is not a function.")

        parts = []
        for idx, t in enumerate(tokens):
            if idx > 0:
                prev = tokens[idx - 1]
                prev_is_value = prev.type in (tokenize.NUMBER, _TOK_STRING) or prev.string == ')'
                prev_is_name  = prev.type == tokenize.NAME
                curr_is_value = t.type in (tokenize.NUMBER, _TOK_STRING) or t.string == '('
                curr_is_name  = t.type == tokenize.NAME

                insert_mul = (
                    (prev_is_value and curr_is_name) or
                    (prev_is_name  and curr_is_value) or
                    (prev_is_name  and curr_is_name)
                )

                if insert_mul and t.string == '(' and prev_is_name:

                    if callable(dco.get(prev.string)):
                        insert_mul = False
                    elif isinstance(v_dict.get(prev.string), Lambda):
                        insert_mul = False                                       

                if insert_mul:
                    parts.append('*')


            if t.type == tokenize.NUMBER:
                if t.string.lower().endswith('j'):
                    coeff = t.string[:-1] or '1'
                    parts.append(f'mpmath.mpc(0, mpmath.mpf("{coeff}"))')
                else:
                    parts.append(f'dec("{t.string}")')
            elif t.type == _TOK_STRING:

                safe = t.string.replace('\\', '\\\\').replace('"', '\\"')
                parts.append(f'Lambda("{safe}")')
            else:
                parts.append(t.string)

        fin = "".join(parts)

        sub_bases = set()
        for k in v_dict:
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\[\d+\]$', str(k))
            if m:
                sub_bases.add(m.group(1))
        for base in sub_bases:
            env[base] = SubProxy(base, env)

        try:
            raw = eval(fin, {"__builtins__": {}}, env)


            if isinstance(raw, Lambda):
                return raw

            if isinstance(raw, _MissingArgs):
                return raw


            if isinstance(raw, mpmath.mpc):
                im = dec(mpmath.nstr(raw.imag, mpmath.mp.dps))
                if abs(im) < dec('1e-' + str(ctx.prec - 2)):
                    return _display(dec(mpmath.nstr(raw.real, mpmath.mp.dps)))
                if chk:
                    return dec(1)
                if not IMG:
                    return _fmt_error("No real solutions.")
                return _display_complex(raw)


            if isinstance(raw, mpmath.mpf):
                raw = dec(mpmath.nstr(raw, mpmath.mp.dps))
            elif not isinstance(raw, dec):
                raw = dec(str(raw))
            return raw if nodisplay else _display(raw)

        except SyntaxError:
            return _fmt_error("The given expression has invalid syntax.")
        except NameError as ne:
            if chk: return dec(1)
            name = getattr(ne, 'name', None) or (str(ne).split("'")[1] if "'" in str(ne) else "?")
            return _fmt_error(f"'{name}' is not defined.")
        except TypeError as te:
            if chk: return dec(1)
            return _fmt_error(f"Type error: {str(te).splitlines()[0]}.")
        except ZeroDivisionError:
            if chk: return dec(1)
            return _fmt_error("Division by zero.")
        except decimal.Overflow:
            if chk: return dec(1)
            return _fmt_error("Result too large.")
        except (decimal.InvalidOperation, ValueError, OverflowError):
            if chk: return dec(1)
            return _fmt_error("No real solutions.")
        except Exception:
            if chk: return dec(1)
            raise

    except Exception as e:
        return _fmt_error(f"Calculation problem: {e}.")


def _parse_repeat(expr: str):
    s = expr.strip()
    if not (s.startswith('repeat(') and s.endswith(')')):
        return None
    body = s[7:-1]
    depth, split = 0, -1
    for i in range(len(body) - 1, -1, -1):
        if   body[i] == ')': depth += 1
        elif body[i] == '(': depth -= 1
        elif body[i] == ',' and depth == 0:
            split = i; break
    if split == -1: return None
    return body[:split].strip(), body[split + 1:].strip()


def _eval_repeat(expr: str, v_dict: dict, chk: bool = False):
    parsed = _parse_repeat(expr)
    if parsed is None:
        return _fmt_error("repeat() syntax: repeat(expression, count)")
    inner_expr, n_str = parsed
    if chk: return cal(inner_expr, v_dict, chk=True)
    n_val = cal(n_str, v_dict, chk)
    if not isinstance(n_val, dec): return n_val
    try:
        n = int(n_val)
    except Exception:
        return _fmt_error("repeat() count must be a whole number.")
    if n <= 0: return _fmt_error("repeat() count must be positive.")
    vars_in = getv(inner_expr)
    target  = vars_in[0] if vars_in else None
    result  = dec(0)
    work    = v_dict
    for _ in range(n):
        result = cal(inner_expr, work, chk)
        if not isinstance(result, dec): return result
        if target is not None: work[target] = result
    return result


def hlp():
    avf = ", ".join(sorted([
        k + (('(' + ', '.join(str(p) for p in inspect.signature(v).parameters.values()) + ')')
             if callable(v) else '')
        for k, v in dco.items() if callable(v)
    ]))
    avc = ", ".join(sorted([
        k + (('(' + ', '.join(str(p) for p in inspect.signature(v).parameters.values()) + ')')
             if callable(v) else '')
        for k, v in dco.items() if not callable(v)
    ]))
    print(f"\n{BOLD}Available functions:{RST}\n  {BRBL}{avf}{RST}\n")
    print(f"{BOLD}Available constants and other:{RST}\n  {BRBL}{avc}{RST}")
    print(f"""
{BOLD}Lambda functions:{RST}
  {GREEN}f="expr"       {RST}  store a symbolic function (quoted expression).
                   Params are the free variables in the expression.
                   Example:  f="sin(x)"
  {GREEN}f(val)         {RST}  evaluate Lambda f at val.  f(pi/2) → 1
  {GREEN}run val [val2…]{RST}  evaluate ALL stored Lambdas with the given values (in definition order)

{BOLD}Symbolic differentiation:{RST}
  {GREEN}diff(f)        {RST}  symbolic derivative of Lambda f → returns Lambda
  {GREEN}diff(f, n)     {RST}  n-th order derivative
  {GREEN}1 + diff(f)    {RST}  arithmetic on Lambdas produces new Lambdas: "1 + cos(x)"
  {GREEN}g=diff(f)      {RST}  store derivative as Lambda g

{BOLD}Quantum / physics:{RST}
  {GREEN}anharmonic(n, c){RST} anharmonic oscillator  H=p²/2+x²/2+c·x⁴, n-th eigenvalue
  {GREEN}hydrogen_e(n)  {RST}  hydrogen E_n = −1/(2n²) in atomic units (Hartree)
  {GREEN}schrodinger <V> <n> <xmin> <xmax> [Npts=100]{RST}
                   FD solution of [−½∂²/∂x²+V(x)]ψ=Eψ, n-th eigenvalue
                   V is an expression in x.
                   Example:  schrodinger x**2/2 0 -8 8    →  ~0.5 (HO ground)

{BOLD}Numerical integration:{RST}
  {GREEN}integrate <expr> <var> <a> <b>{RST}
                   ∫_a^b expr d<var>  (Gauss-Legendre, arbitrary precision)
                   Example:  integrate sin(x) x 0 pi      → 2
                   Example:  integrate exp(-x**2) x -inf inf   → √π

{BOLD}Special forms:{RST}
  {GREEN}repeat(expr, n){RST}  evaluate expr n times, threading the first variable
""")


def _do_schrodinger(raw: str) -> bool:
    parts = raw.strip().split()
    if len(parts) < 5:
        print(_fmt_error("Usage: schrodinger <V_expr> <n> <xmin> <xmax> [Npts=100]"))
        return True
    V_expr = parts[1]
    try:
        n_v = cal(parts[2], {}); xmin_v = cal(parts[3], {}); xmax_v = cal(parts[4], {})
    except Exception as err:
        print(_fmt_error(f"Argument error: {err}")); return True
    for lbl, v in [('n', n_v), ('xmin', xmin_v), ('xmax', xmax_v)]:
        if not isinstance(v, dec): print(v); return True
    Npts = int(cal(parts[5], {})) if len(parts) >= 6 else 100
    success = spdwarn()
    print(_solve_schrodinger(V_expr, int(n_v), xmin_v, xmax_v, Npts))
    success[0] = True
    return True


def _do_integrate(raw: str) -> bool:
    parts = raw.strip().split()
    if len(parts) < 5:
        print(_fmt_error("Usage: integrate <expr> <var> <a> <b>"))
        return True
    expr_str, var, a_str, b_str = parts[1], parts[2], parts[3], parts[4]

    def _lim(s):
        sl = s.lower()
        if sl in ('inf', '+inf'):  return  mpmath.inf
        if sl == '-inf':           return -mpmath.inf
        v = cal(s, {})
        return mpmath.mpf(str(v)) if isinstance(v, dec) else None

    a_mp, b_mp = _lim(a_str), _lim(b_str)
    if a_mp is None or b_mp is None:
        print(_fmt_error("Could not parse integration limits.")); return True

    def integrand(t): return _cal_mpf(expr_str, var, t)

    success = spdwarn()
    try:
        result     = mpmath.quad(integrand, [a_mp, b_mp])
        success[0] = True
        result_dec = dec(mpmath.nstr(result, mpmath.mp.dps))
        if abs(result_dec) < dec('1e-' + str(ctx.prec - 2)):
            result_dec = dec(0)
        print(_display(result_dec))
    except Exception as err:
        success[0] = True
        print(_fmt_error(f"Integration failed: {err}"))
    return True


def _do_run(raw: str) -> bool:
    args_str = raw.strip().split()[1:]               

    lam = _last_lambda[0]
    if not isinstance(lam, Lambda):
        print(_fmt_error("No unassigned Lambda in current output. "
                         "Evaluate an expression that returns a function first."))
        return True


    if not lam.params:
        result = lam()
        if isinstance(result, dec):
            print(_display(result))
        elif isinstance(result, Lambda):
            _last_lambda[0] = result
            print(result)
        else:
            print(result)
        return True


    if not args_str:
        p = ', '.join(lam.params)
        print(_fmt_error(f"Usage: run <{p}>"))
        return True

    args_vals = []
    for a in args_str:
        v = cal(a, _user_vars)
        if not isinstance(v, dec):
            print(v); return True
        args_vals.append(v)

    call_args = [args_vals[i % len(args_vals)] for i in range(len(lam.params))]
    result    = lam(*call_args)

    if isinstance(result, dec):
        print(_display(result))
    elif isinstance(result, Lambda):
        _last_lambda[0] = result
        print(result)
    else:
        print(result)
    return True


def actions(s: str) -> bool:
    global ISO_INLINE, DISPLAY_PREC, IMG
    cmd = s.strip().lower()
    raw = s.strip()

    if cmd == 'help':
        hlp(); return True

    if cmd == 'toggle':
        ISO_INLINE = not ISO_INLINE
        print(f"\x1b[32mInline isolation: {'ON' if ISO_INLINE else 'OFF'}{RST}")
        return True

    if cmd == 'clear':
        _user_vars.clear()
        print(f"\x1b[32mPersistent variables cleared.{RST}")
        return True

    if cmd == 'img':
        IMG = not IMG
        if IMG: dco['j'] = mpmath.mpc(0, 1)
        else:   dco.pop('j', None)
        print(f"\x1b[32mImaginary mode: {'ON' if IMG else 'OFF'}{RST}")
        return True

    if cmd.startswith('prec'):
        parts = cmd.split()
        if len(parts) == 1:
            print(f"\x1b[32mDisplay: {DISPLAY_PREC} digits  (internal: {ctx.prec}){RST}")
            return True
        if len(parts) == 2:
            try: n = int(parts[1])
            except ValueError:
                print(_fmt_error("prec: integer required")); return True
            if n < 1:
                print(_fmt_error("prec: must be ≥ 1")); return True
            DISPLAY_PREC  = n
            ctx.prec      = n + GUARD_DIGITS
            mpmath.mp.dps = n + GUARD_DIGITS + 5
            success = spdwarn(); _repin_constants(); success[0] = True
            print(f"\x1b[32mPrecision → {DISPLAY_PREC} display  ({ctx.prec} internal){RST}")
            return True
        print(_fmt_error("Usage: prec  or  prec <n>")); return True

    if cmd.startswith('schrodinger ') or cmd.startswith('sch '):
        return _do_schrodinger(raw)

    if cmd.startswith('integrate '):
        return _do_integrate(raw)

    if cmd.startswith('run'):
        return _do_run(raw)

    return False


def _split_top_level(s: str, sep: str) -> list:
    parts, current, depth = [], '', 0
    in_str = False; str_char = ''
    for ch in s:
        if in_str:
            current += ch
            if ch == str_char: in_str = False
        elif ch in ('"', "'"):
            in_str = True; str_char = ch; current += ch
        elif ch in ('(', '['):
            depth += 1; current += ch
        elif ch in (')', ']'):
            depth -= 1; current += ch
        elif ch == sep and depth == 0:
            parts.append(current); current = ''
        else:
            current += ch
    parts.append(current)
    return parts


def _is_assign_target(lhs: str) -> bool:
    return ((len(lhs) == 1 and lhs.isalpha()) or
            _is_longvar(lhs) or
            bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*\[\d+\]$', lhs)))


def _parse_assignment(seg: str):
    eq = seg.find('=')
    if eq == -1 or (eq + 1 < len(seg) and seg[eq + 1] == '='):
        return None
    lhs, rhs = seg[:eq].strip(), seg[eq + 1:].strip()
    if _is_assign_target(lhs):
        return lhs, rhs
    return None


def _assign_targets(inline_str: str) -> set:
    if ';' in inline_str:
        segs = [seg for seg in _split_top_level(inline_str, ';') if '=' in seg]
        return {seg.split('=', 1)[0].strip() for seg in segs}
    return {p.split('=', 1)[0].strip() for p in inline_str.split() if '=' in p}


def sorta(s: str, allowed: list) -> list:
    if ';' in s:
        tokens = [seg for seg in _split_top_level(s, ';') if seg]
    else:
        tokens, current, depth = [], '', 0
        in_str = False; str_char = ''
        for ch in s:
            if in_str:
                current += ch
                if ch == str_char: in_str = False
            elif ch in ('"', "'"):
                in_str = True; str_char = ch; current += ch
            elif ch == '(':
                depth += 1; current += ch
            elif ch == ')':
                depth -= 1; current += ch
            elif ch == ' ' and depth == 0:
                if current: tokens.append(current)
                current = ''
            else:
                current += ch
        if current: tokens.append(current)

    pairs = []
    for p in tokens:
        if '=' in p:
            tgt, val = p.split('=', 1)
            tgt = tgt.strip()
            if tgt in allowed or re.match(r'^[A-Za-z_][A-Za-z0-9_]*\[\d+\]$', tgt):
                deps = [x for x in allowed if x in val]
                pairs.append((tgt, val, deps))

    res, vis, active = [], set(), set()
    def visit(node):
        tgt, val, deps = node
        if tgt in vis or tgt in active: return
        active.add(tgt)
        for d in deps:
            dep = next((x for x in pairs if x[0] == d), None)
            if dep: visit(dep)
        active.discard(tgt); vis.add(tgt); res.append((tgt, val))
    for p in pairs: visit(p)
    return res


def split_inline(s: str):
    top = _split_top_level(s, ';')
    if len(top) > 1:
        segments = [seg.strip() for seg in top if seg.strip()]
        if len(segments) == 1:
            parsed = _parse_assignment(segments[0])
            if parsed:
                tgt, val = parsed
                return f"{tgt}={val};", ""
            return "", segments[0]
        if len(segments) >= 2:
            *assign_segs, expr_seg = segments
            parsed = [_parse_assignment(seg) for seg in assign_segs]
            if all(parsed):
                inline_str = ";".join(f"{t}={v}" for t, v in parsed) + ";"
                return inline_str, expr_seg
            return "", s.strip().replace(';', ' ')

    s_stripped = s.strip()
    if ' ' not in s_stripped:
        parsed = _parse_assignment(s_stripped)
        if parsed:
            tgt, val = parsed
            return f"{tgt}={val};", ""

    return "", s_stripped


def apply_inline(inline_str: str, all_vars: list, base: dict, isolate: bool, report: bool = False, protect: set = None, fixed: set = None, track_resolved: list = None, base_vals: dict = None) -> dict:
    work = base.copy() if isolate else base
    for tgt, val in sorta(inline_str, all_vars):
        if protect and tgt in protect:
            continue
        if fixed is not None and tgt in fixed:
            continue
        success = spdwarn()
        ev = cal(val, work)
        success[0] = True
        if isinstance(ev, str) and _UNDEF_RE.search(ev):
            prev_len = len(track_resolved) if track_resolved is not None else 0
            ev = _resolve(val, work, track_resolved)
            if ev is _ABORT:
                break
            if isinstance(ev, (dec, Lambda)) and fixed is not None:
                fixed.add(tgt)
            if base_vals is not None and track_resolved is not None:
                for var in track_resolved[prev_len:]:
                    if var in work:
                        base_vals[var] = work[var]
        if isinstance(ev, (dec, Lambda)):
            work[tgt] = ev
            if isinstance(ev, Lambda):
                _user_vars[tgt] = ev
        elif report:
            print(ev)
    return work if isolate else base


def _strip_spaces(s: str) -> str:
    buf = []
    in_str = False; str_char = ''
    i = 0
    while i < len(s):
        ch = s[i]
        if in_str:
            buf.append(ch)
            if ch == str_char: in_str = False
            i += 1
        elif ch in ('"', "'"):
            in_str = True; str_char = ch; buf.append(ch)
            i += 1
        elif ch == '_':
            j = s.find('_', i + 1)
            if j > i:
                buf.append(_register_longvar(s[i+1:j]))
                i = j + 1
            else:
                buf.append('_')
                i += 1
        elif ch != ' ':
            buf.append(ch)
            i += 1
        else:
            i += 1
    return re.sub(r'(XLONGx\d+x)(\d)', r'\1*\2', ''.join(buf))


_ABORT    = object()
_UNDEF_RE = re.compile(r"'([^']+)' is not defined")


def _ask_value(name, cur_vars):
    while True:
        disp = _longvar_inner(name) if _is_longvar(name) else name
        inp = input(f"{BOLD}{disp}:{RST} ").strip()
        if not inp: continue
        if actions(inp): continue
        if inp.lower() == 'new': return _ABORT
        r = _resolve(inp, cur_vars)
        if r is _ABORT or isinstance(r, (dec, Lambda)):
            return r
        print(r)


def _resolve(expr_str, cur_vars, resolved=None):
    success = spdwarn()
    ev = cal(expr_str, cur_vars)
    success[0] = True
    for _ in range(20):
        if isinstance(ev, _MissingArgs):
            answers = []
            for param in ev.missing:
                if param in cur_vars and isinstance(cur_vars[param], (dec, Lambda)):
                    val = cur_vars[param]
                else:
                    val = _ask_value(param, cur_vars)
                    if val is _ABORT: return _ABORT
                    cur_vars[param] = val
                    if resolved is not None and param not in resolved:
                        resolved.append(param)
                answers.append(val)
            success = spdwarn()
            ev = ev.lam(*ev.provided, *answers)
            success[0] = True
            continue
        if isinstance(ev, str):
            m = _UNDEF_RE.search(ev)
            if m:
                val = _ask_value(m.group(1), cur_vars)
                if val is _ABORT: return _ABORT
                cur_vars[m.group(1)] = val
                if resolved is not None and m.group(1) not in resolved:
                    resolved.append(m.group(1))
                success = spdwarn()
                ev = cal(expr_str, cur_vars)
                success[0] = True
                continue
        break
    return ev

_pending_expr: list = [None]                                                               

try:
    while True:
        if _pending_expr[0] is not None:
            raw = _pending_expr[0]
            _pending_expr[0] = None
        else:
            raw = input(f"{BOLD}>{RST} ").strip()
        if actions(raw): continue
        if not raw or raw.lower() == 'new': continue

        raw = _strip_spaces(raw)
        inline_str, exp = split_inline(raw)
        if not exp:
            if inline_str:
                all_vars = getv(raw)
                prev_lambda_keys = {k for k, v in _user_vars.items() if isinstance(v, Lambda)}
                tmp = _user_vars.copy()
                for tgt, val in sorta(inline_str, all_vars):
                    ev = cal(val, tmp)
                    if isinstance(ev, Lambda):
                        _user_vars[tgt] = ev
                        tmp[tgt] = ev
                new_lambdas = [(k, v) for k, v in _user_vars.items()
                               if k not in prev_lambda_keys and isinstance(v, Lambda)]
                for k, v in new_lambdas:
                    disp_k = _longvar_inner(k) if _is_longvar(k) else k
                    print(f"  {disp_k} = {v}")
                if not new_lambdas:
                    print(_fmt_error("No expression found after assignments."))
            else:
                print(_fmt_error("No expression found after assignments."))
            continue

        all_vars     = getv(raw)
        assigned_set = _assign_targets(inline_str)

        already_set  = set(_user_vars.keys())
        det_vars     = sorted(set(all_vars) - assigned_set - already_set)

        cur_vars = _user_vars.copy()

        probe = cal(exp, {v: dec(0) for v in getv(exp)}, chk=True)
        if not isinstance(probe, dec):
            res = _resolve(exp, cur_vars)
            if res is _ABORT: continue
            if isinstance(res, Lambda) and not assigned_set: _last_lambda[0] = res
            print(res)
            continue


        cur_vars = _user_vars.copy()

        resolved_names = []
        resolved_base_vals = {}
        fixed_inline = set()
        if inline_str:
            cur_vars = apply_inline(inline_str, all_vars, cur_vars, ISO_INLINE, fixed=fixed_inline, track_resolved=resolved_names, base_vals=resolved_base_vals)

        broken = False
        if det_vars:
            for v in det_vars:
                while True:
                    v_disp = _longvar_inner(v) if _is_longvar(v) else v
                    v_inp = input(f"{BOLD}{v_disp}:{RST} ").strip()
                    if not v_inp: continue
                    if actions(v_inp): continue
                    if v_inp.lower() == 'new': broken = True; break
                    ev = _resolve(v_inp, cur_vars)
                    if ev is _ABORT: broken = True; break
                    if isinstance(ev, Lambda):
                        cur_vars[v] = ev
                        _user_vars[v] = ev
                    elif isinstance(ev, dec):
                        cur_vars[v] = ev
                    else:
                        print(ev)
                        continue
                    if inline_str:
                        cur_vars = apply_inline(inline_str, all_vars, cur_vars, ISO_INLINE, fixed=fixed_inline, track_resolved=resolved_names)
                    break
                if broken: break
            if broken: continue

        if inline_str:
            cur_vars = apply_inline(inline_str, all_vars, cur_vars, ISO_INLINE, fixed=fixed_inline, track_resolved=resolved_names)

        asked_sub_keys = []
        seen_sub = set()
        for base, index_expr in get_sub_specs(exp):
            idx_v = cal(index_expr, cur_vars)
            if not isinstance(idx_v, dec):
                continue
            idx = int(idx_v)
            key = f"{base}[{idx}]"
            if key in seen_sub or key in cur_vars:
                seen_sub.add(key); continue
            if key in _user_vars:
                cur_vars[key] = _user_vars[key]; seen_sub.add(key); continue
            seen_sub.add(key)
            asked_sub_keys.append(key)
            while True:
                disp = _longvar_inner(base) if _is_longvar(base) else base
                v_inp = input(f"{BOLD}{disp}[{idx}]:{RST} ").strip()
                if not v_inp: continue
                if actions(v_inp): continue
                if v_inp.lower() == 'new': broken = True; break
                ev = _resolve(v_inp, cur_vars)
                if ev is _ABORT: broken = True; break
                cur_vars[key] = ev if isinstance(ev, dec) else dec(0)
                break
            if broken: break
        if broken: continue

        if inline_str:
            cur_vars = apply_inline(inline_str, all_vars, cur_vars, ISO_INLINE, fixed=fixed_inline, track_resolved=resolved_names)

        res = _resolve(exp, cur_vars, resolved_names)
        if res is _ABORT: continue
        if isinstance(res, Lambda) and not assigned_set: _last_lambda[0] = res
        print(res)


        if not det_vars and not resolved_names and not asked_sub_keys:
            continue
        
        user_pinned = set()
        while True:
            inp = input().strip()
            if actions(inp): continue
            if inp.lower() == 'new': break
            if not inp:
                res = _resolve(exp, cur_vars, resolved_names)
                if res is _ABORT: break
                if isinstance(res, Lambda) and not assigned_set: _last_lambda[0] = res
                print(res); continue

            inp = _strip_spaces(inp)
            just_set = set()
            user_updated = set()
            if '=' in inp:
                assigns = sorta(inp, list(dict.fromkeys(all_vars + resolved_names)))
                if not assigns: continue
                err = False; abort = False; tmp = cur_vars.copy()
                for tgt, val in assigns:
                    ev = _resolve(val, tmp, resolved_names)
                    if ev is _ABORT:
                        abort = True; break
                    if isinstance(ev, (dec, Lambda)):
                        tmp[tgt] = ev
                        if isinstance(ev, Lambda): _user_vars[tgt] = ev
                    else:
                        print(ev); err = True; break
                if abort: break
                if err: continue
                just_set = {tgt for tgt, _ in assigns}
                user_updated = just_set.copy()
                user_pinned |= just_set
                cur_vars = tmp
            else:
                ev = _resolve(inp, cur_vars, resolved_names)
                if ev is _ABORT: break
                if isinstance(ev, Lambda):
                    print(ev)
                    continue
                target_list = det_vars if det_vars else (asked_sub_keys + resolved_names) if (asked_sub_keys or resolved_names) else sorted(set(all_vars) - already_set - assigned_set)
                if isinstance(ev, dec) and target_list:
                    cur_vars[target_list[-1]] = ev
                    user_updated = {target_list[-1]}
                elif isinstance(ev, dec):
                    print(ev)
                    continue
                elif isinstance(ev, str):
                    print(ev)
                    continue
                else:
                    _pending_expr[0] = inp
                    break

            if inline_str:
                for k, v in resolved_base_vals.items():
                    if k not in user_updated and k not in user_pinned:
                        cur_vars[k] = v
                cur_vars = apply_inline(inline_str, all_vars, cur_vars, ISO_INLINE, protect=just_set | user_pinned)

            res = _resolve(exp, cur_vars, resolved_names)
            if res is _ABORT: break
            if isinstance(res, Lambda) and not assigned_set: _last_lambda[0] = res
            print(res)
except EOFError:
    print("(Quit)")
    exit()
except KeyboardInterrupt:
    print("(Interrupt)")
