"""Print tag-stripped text around each regex match in an HTML file.

Run with python3 -I. Usage: python3 -I html_ctx.py <file> <regex> [before_chars] [after_chars] [max_hits]
"""
import html
import re
import sys


def main():
    p, rx = sys.argv[1], sys.argv[2]
    b = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    a = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    k = int(sys.argv[5]) if len(sys.argv) > 5 else 20
    raw = open(p, encoding="utf-8", errors="replace").read()
    raw = re.sub(r"<script.*?</script>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<style.*?</style>", " ", raw, flags=re.S | re.I)
    txt = html.unescape(re.sub(r"<[^>]+>", " | ", raw))
    txt = re.sub(r"(\s*\|\s*)+", " | ", txt)
    txt = re.sub(r"\s+", " ", txt)
    for i, m in enumerate(re.finditer(rx, txt, flags=re.I)):
        if i >= k:
            break
        print("...", txt[max(0, m.start() - b):m.end() + a], "...")


if __name__ == "__main__":
    main()
