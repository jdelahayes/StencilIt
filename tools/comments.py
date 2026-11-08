"""Extract or replace code comments (Python comments/docstrings, JS/CSS comments).

    python tools/comments.py extract          -> tools/comments_src.json  (unique comment texts)
    python tools/comments.py apply MAP.json   -> replaces each comment text by its translation

Only comment spans are touched, never code or UI strings:
  - Python: COMMENT tokens and docstrings (located with tokenize / ast);
  - .js / .html: `// …` comments preceded by whitespace (so "http://" inside strings is left
    alone) and `/* … */` blocks that do not cross HTML markup.
"""
import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ["app.py", "stencilit/pipeline.py", "stencilit/svg_export.py", "stencilit/__init__.py", "tools/extract_strings.py"]
WEB = ["static/index.html", "static/i18n.js"]
JS_LINE = re.compile(r"(?:(?<=\s)|^)//\s?(.*)$")
BLOCK = re.compile(r"/\*(.*?)\*/", re.S)
FRENCH = re.compile(r"[éèêàçùôîûœ]|\b(le|la|les|des|du|une|un|et|ou|de|pour|sur|par|dans|sans|avec|est|si|en|au|aux)\b", re.I)


def _offsets(src):
    starts, pos = [0], 0
    for line in src.splitlines(keepends=True):
        pos += len(line)
        starts.append(pos)
    return lambda row, col: starts[row - 1] + col


def py_spans(src):
    """(start, end, text) of every comment text and docstring body in a Python source."""
    off = _offsets(src)
    spans = []
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            a = off(*tok.start)
            body = tok.string.lstrip("#")
            lead = len(tok.string) - len(body) + (len(body) - len(body.lstrip()))
            spans.append((a + lead, off(*tok.end), body.strip()))
    doc_lines = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                doc_lines.add(first.lineno)
    for tok in toks:
        if tok.type == tokenize.STRING and tok.start[0] in doc_lines:
            a, b = off(*tok.start), off(*tok.end)
            q = 3 if tok.string[:3] in ('"""', "'''") else 1
            spans.append((a + q, b - q, tok.string[q:-q]))
    return spans


def web_spans(src):
    spans, pos = [], 0
    for line in src.splitlines(keepends=True):
        m = JS_LINE.search(line.rstrip("\r\n"))
        if m:
            spans.append((pos + m.start(1), pos + m.end(1), m.group(1)))
        pos += len(line)
    for m in BLOCK.finditer(src):
        if "<" not in m.group(1):
            spans.append((m.start(1), m.end(1), m.group(1)))
    return spans


def spans_of(f, src):
    return py_spans(src) if f.endswith(".py") else web_spans(src)


def extract():
    seen = []
    for f in PY + WEB:
        src = (ROOT / f).read_text(encoding="utf-8")
        for _a, _b, t in spans_of(f, src):
            t = t.strip()
            if t and FRENCH.search(t) and t not in seen:
                seen.append(t)
    (ROOT / "tools" / "comments_src.json").write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(seen), "comments")


def apply(mapping_file):
    mp = json.loads(Path(mapping_file).read_text(encoding="utf-8"))
    for f in PY + WEB:
        p = ROOT / f
        src = p.read_text(encoding="utf-8")
        out, n = src, 0
        for a, b, t in sorted(spans_of(f, src), key=lambda s: -s[0]):   # from the end: offsets stay valid
            seg = out[a:b]
            key = seg.strip()
            if key in mp:
                lead = seg[:len(seg) - len(seg.lstrip())]
                trail = seg[len(seg.rstrip()):]
                out = out[:a] + lead + mp[key] + trail + out[b:]
                n += 1
        if out != src:
            if f.endswith(".py"):
                ast.parse(out)        # still valid Python
            p.write_text(out, encoding="utf-8")
        print(f, n, "comments replaced")


if __name__ == "__main__":
    extract() if sys.argv[1] == "extract" else apply(sys.argv[2])
