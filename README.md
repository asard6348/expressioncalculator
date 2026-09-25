# calculator.py

`calculator.py` is an interactive, arbitrary-precision mathematical REPL (Read-Eval-Print Loop) built on top of Python and `mpmath`. It scales from basic daily arithmetic to symbolic differentiation, numerical integration, and computational physics.

---

## Key Features

* **Arbitrary Precision:** Compute calculations to arbitrary decimal places, eliminating hardware-level standard floating-point limits.
* **Deterministic & Universal:** Bypasses CPU hardware Floating-Point Units (FPUs) by executing big-integer software arithmetic, ensuring identical results across different processor architectures (x86_64, ARM64, RISC-V).
* **Cross-Platform:** Works on any system capable of running Python 3 (Windows, macOS, Linux, BSD, Android/iOS environments, and WebAssembly/Pyodide).
* **Smart Variable Prompting:** Interactively prompts for undefined variables (e.g., entering `x + y` pauses to collect values for $x$ and $y$).
* **Symbolic Calculus & Physics:** Define symbolic expressions, compute $n$-th derivatives, numerical integrals, roots, and solve physical models like the Schrödinger equation.
* **Sets, Intervals, and Complex Numbers:** Native support for sets, inequalities, interval arithmetic, and toggleable imaginary/complex mode.

---

## Requirements & Dependencies

* **Python 3.x**: [https://www.python.org/downloads/](https://www.python.org/downloads/)
* **`mpmath`** *(Required)*: Core arbitrary-precision library.
  ```bash
  pip install mpmath
  ```
* **`gmpy2`** *(Optional Acceleration)*: Highly recommended C-based multi-precision library (`GMP`/`MPFR`). Automatically speeds up calculations if present.
  ```bash
  pip install gmpy2
  ```

---

## Universality, Platform Portability & Consistency

### 1. Cross-Platform Execution
`calculator.py` is **100% platform-agnostic** in its pure-Python fallback mode. If `gmpy2` binaries are unavailable or fail to compile on non-standard architectures, `mpmath` seamlessly degrades to its native Python engine without feature loss.

### 2. Hardware FPU Independence
Standard native floats rely on hardware FPUs subject to system-dependent quirks, such as 80-bit internal x86 registers or Fused Multiply-Add ($a \times b + c$) optimizations. By using software-based mantissa and exponent representations, computing $1000$ digits of $\pi$ yields exact string equivalence whether executed on an Apple M-series CPU, an Intel server, or a Raspberry Pi.

### 3. Cross-Update & Backend Consistency
To maintain numerical determinism across updates and backend switches:
* **Literal Parsing:** Input numbers are parsed as AST string tokens (e.g., `"0.1"`) to avoid implicit initial conversion to 64-bit IEEE 754 binary floats.
* **Backend Differences:** Microscopic discrepancies ($1\text{ ULP}$—Unit in the Last Place) may occasionally occur in transcendental functions when switching between the pure Python engine and the `gmpy2` C-MPFR engine due to minor algorithmic variations.
* **Reproducibility:** For bit-for-bit reproducible scientific output across different environments, lock `mpmath` versions in your environment (`mpmath==1.3.0`) and force a specific backend:
  ```python
  import mpmath
  mpmath.mp.backend = 'python'  # Guarantees identical pure-Python math engine across machines
  ```

---

## Usage

Launch the interactive REPL directly from your terminal:

```bash
python calculator.py
```

### REPL Commands
* `help` - Display available built-in mathematical functions (`sin`, `cos`, `log`, etc.) and constants ($\pi$, $e$, $\phi$).
* `prec <n>` - Adjust the operational and display precision to `<n>` decimal digits (e.g., `prec 100`).
* `img` - Toggle complex/imaginary number mode on or off (binds $i = \sqrt{-1}$).
* `clear` - Reset all user-defined variables and custom functions.
* `new` / `back` - Cancel the active calculation or step back during a multi-variable prompt.

---

## Syntax & Examples

### Basic Arithmetic & Variables
* **Expressions:** `(15.5 ** 2) / 4 + 10`
* **Inline Assignment:** `a = 10; b = a * 5; a + b`
* **Lists & Sets:** `{1, 2, 3}` or `range(5)`
* **Intervals & Inequalities:** `{>=0<20}` or `interval(0, 100)`
* **Subscript Access:** `x[0]`

### Calculus & Symbolic Operations
* **Lambda Functions:** Wrap symbolic expressions in quotes to auto-detect free variables:
  * Define function: `f = "sin(x)"`
  * Evaluate: `f(pi / 2)`
* **Symbolic Differentiation:**
  * First derivative: `diff(f)`
  * $N$-th derivative: `diff(f, 2)`
* **Numerical Integration & Root Finding:**
  * Integration: `integrate("exp(-x**2)", -inf, inf)`
  * Root finding: `findroot("x**2 - 4", 1)`
* **Physics Utilities:**
  * Finite Difference Schrödinger solver: `schrodinger("x**2 / 2", 0, -8, 8)`
  * Hydrogen atomic energy (Hartree): `hydrogen_e(1)`
  * Anharmonic oscillator eigenvalues: `anharmonic(n, c)`