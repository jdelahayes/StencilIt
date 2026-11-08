"""Inventory of the texts to translate (static HTML, JavaScript strings, Python messages).

Usage: python tools/extract_strings.py  -> writes tools/strings_fr.json
"""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORD = re.compile(r"[A-Za-zÀ-ÿ]{2}")
FRENCH = re.compile(r"[éèêàçùôîûœ]|\b(le|la|les|des|du|une|un|et|ou|de|à|pour|sur|par|dans|sans|avec)\b", re.I)


def norm(t):
    return " ".join(t.split())


def html_strings(src):
    body = re.sub(r"<script>.*?</script>|<style>.*?</style>", "", src, flags=re.S)
    texts, attrs = set(), set()

    class P(HTMLParser):
        def handle_data(self, d):
            t = norm(d)
            if WORD.search(t):
                texts.add(t)

        def handle_starttag(self, tag, a):
            for k, v in a:
                if k in ("title", "placeholder", "aria-label", "alt", "label") and v and WORD.search(v):
                    attrs.add(norm(v))

    P().feed(body)
    return sorted(texts), sorted(attrs)


def js_strings(src):
    js = "\n".join(re.findall(r"<script>(.*?)</script>", src, flags=re.S))
    out = set()
    for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`', js):
        v = m.group(1) if m.group(1) is not None else m.group(2)
        if WORD.search(v) and FRENCH.search(v) and " " in v:
            out.add(norm(v))
    return sorted(out)


def py_strings():
    out = set()
    for f in ("app.py", "stencilit/pipeline.py"):
        src = (ROOT / f).read_text(encoding="utf-8")
        for m in re.finditer(r'f?"((?:[^"\\\n]|\\.)*)"', src):
            v = m.group(1)
            if WORD.search(v) and FRENCH.search(v) and " " in v and not v.startswith(("%", "#")):
                out.add(v)
    return sorted(out)


if __name__ == "__main__":
    src = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    texts, attrs = html_strings(src)
    data = {"html_text": texts, "html_attr": attrs, "js": js_strings(src), "python": py_strings()}
    (ROOT / "tools" / "strings_fr.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print({k: len(v) for k, v in data.items()})
