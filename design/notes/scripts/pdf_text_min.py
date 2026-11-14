"""Minimal stdlib PDF text extractor (FlateDecode streams + ToUnicode CMaps).

Run with python3 -I. Usage: python3 -I pdf_text_min.py <pdf> [regex]
Decodes text-showing operators (Tj/TJ) with the union of all ToUnicode CMaps.
Approximate: good enough to search for a phrase, not for layout.
"""
import re
import sys
import zlib


def streams(data):
    for m in re.finditer(rb"stream\r?\n", data):
        s = m.end()
        e = data.find(b"endstream", s)
        if e < 0:
            continue
        chunk = data[s:e]
        try:
            yield zlib.decompress(chunk)
        except Exception:
            try:
                yield zlib.decompressobj().decompress(chunk)
            except Exception:
                continue


def parse_cmap(txt, cmap):
    for blk in re.findall(rb"beginbfchar(.*?)endbfchar", txt, re.S):
        for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            try:
                cmap[(len(a) // 2, int(a, 16))] = bytes.fromhex(b.decode()).decode("utf-16-be", "replace")
            except Exception:
                pass
    for blk in re.findall(rb"beginbfrange(.*?)endbfrange", txt, re.S):
        for a, z, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            lo, hi, base = int(a, 16), int(z, 16), int(b, 16)
            for i in range(lo, min(hi, lo + 5000) + 1):
                try:
                    cmap[(len(a) // 2, i)] = chr(base + i - lo)
                except Exception:
                    pass


def dec_hex(h, cmap):
    h = re.sub(rb"\s", b"", h)
    if len(h) % 2:
        h += b"0"
    raw = bytes.fromhex(h.decode())
    out = []
    w = 2 if any((2, (raw[i] << 8) | raw[i + 1]) in cmap for i in range(0, len(raw) - 1, 2)) else 1
    for i in range(0, len(raw) - (w - 1), w):
        code = int.from_bytes(raw[i:i + w], "big")
        out.append(cmap.get((w, code), "?"))
    return "".join(out)


def main():
    data = open(sys.argv[1], "rb").read()
    ss = list(streams(data))
    cmap = {}
    for s in ss:
        if b"begincmap" in s:
            parse_cmap(s, cmap)
    lines = []
    for s in ss:
        if b"BT" not in s:
            continue
        for bt in re.findall(rb"BT(.*?)ET", s, re.S):
            parts = []
            for tok in re.finditer(rb"<([0-9A-Fa-f\s]+)>|\(((?:\\.|[^\\)])*)\)", bt):
                if tok.group(1) is not None:
                    parts.append(dec_hex(tok.group(1), cmap))
                else:
                    parts.append(tok.group(2).decode("latin-1"))
            if parts:
                lines.append("".join(parts))
    text = " ".join(lines)
    if len(sys.argv) > 2:
        for m in re.finditer(sys.argv[2], text, re.I):
            print("...", text[max(0, m.start() - 200):m.end() + 200], "...")
    else:
        print(text[:3000])


if __name__ == "__main__":
    main()
