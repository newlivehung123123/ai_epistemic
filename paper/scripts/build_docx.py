"""Build an editable .docx copy of paper.tex for Google Docs.

Run from any folder after a LaTeX compile, so that paper.aux holds current numbers:
    python3 -I paper/scripts/build_docx.py [build_dir]

The script inlines the tables, replaces every \\ref with the number LaTeX assigned,
numbers the headings by hand, renders the PDF figures to PNG, converts with pandoc
and citeproc, then restyles the result to A4, Times New Roman and black text.
Output: paper/paper_for_google_docs.docx
"""
import pathlib
import re
import subprocess
import sys

import pdfplumber
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

PAPER = pathlib.Path(__file__).resolve().parents[1]
BUILD = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else PAPER / "docx_build"
BUILD.mkdir(parents=True, exist_ok=True)
PANDOC = "/opt/anaconda3/bin/pandoc"
OUT = PAPER / "paper_for_google_docs.docx"


def balanced(s, i):
    """Return the index just after the brace group that opens at s[i]."""
    assert s[i] == "{", s[i:i + 30]
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{" and s[j - 1] != "\\":
            depth += 1
        elif s[j] == "}" and s[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return j + 1
    raise ValueError("unbalanced braces")


# labels and numbers from the last LaTeX compile
aux = (PAPER / "paper.aux").read_text(errors="ignore")
labels = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", aux))

t = (PAPER / "paper.tex").read_text()
t = re.sub(r"\\input\{(tables/[^}]+)\}",
           lambda m: (PAPER / (m.group(1) if m.group(1).endswith(".tex") else m.group(1) + ".tex")).read_text(), t)

# float captions get their number as text, as in the Sentient Futures copy
out, pos = [], 0
for m in re.finditer(r"\\begin\{(table|figure)\*?\}", t):
    if m.start() < pos:
        continue
    kind = m.group(1)
    end = t.index("\\end{" + kind, m.end())
    body = t[m.start():end]
    lab = re.search(r"\\label\{([^}]+)\}", body)
    c = body.find("\\caption{")
    if lab and c >= 0:
        num = labels[lab.group(1)]
        word = "Table" if kind == "table" else "Figure"
        k = c + len("\\caption")
        body = body[:k + 1] + f"{word} {num}. " + body[k + 1:]
    out.append(t[pos:m.start()])
    out.append(body)
    pos = end
out.append(t[pos:])
t = "".join(out)
t = re.sub(r"\\(begin|end)\{(table|figure)\*\}", r"\\\1{\2}", t)

# cross-references
t = re.sub(r"\\ref\{([^}]+)\}", lambda m: labels[m.group(1)], t)

# header cells written as nested tabulars become one line
t = re.sub(r"\\begin\{tabular\}\[b\]\{@\{\}[lcr]@\{\}\}(.*?)\\end\{tabular\}",
           lambda m: re.sub(r"\\\\(\\relax)?\s*", " ", m.group(1)), t, flags=re.S)
t = re.sub(r"P\{([0-9.]+)\}", r"p{\1\\textwidth}", t)
t = re.sub(r"\\begin\{adjustbox\}\{[^}]*\}|\\end\{adjustbox\}", "", t)
t = re.sub(r"\\setlength\{[^}]*\}\{[^}]*\}", "", t)
t = re.sub(r"\\(footnotesize|scriptsize|small|clearpage|allowbreak|relax)\b", "", t)
t = re.sub(r"\\newcolumntype\{P\}.*\n", "", t)
t = re.sub(r"\\begin\{Verbatim\}\[[^\]]*\]", r"\\begin{verbatim}", t)
t = t.replace("\\end{Verbatim}", "\\end{verbatim}")

# inline maths becomes text with italic variables, so the copy edits as ordinary text
# in Google Docs; the two displayed equations stay as equations
GREEK = {"delta": "δ"}
SYM = {"geq": "≥", "leq": "≤", "in": "∈"}


def math_text(s):
    out, i, prev = [], 0, None

    def group(i):
        if s[i] == "{":
            j = balanced(s, i)
            return s[i + 1:j - 1], j
        if s[i] == "\\":
            m = re.match(r"\\[A-Za-z]+", s[i:])
            return m.group(0), i + len(m.group(0))
        return s[i], i + 1

    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
        elif c in "_^":
            g, i = group(i + 1)
            tag = "textsubscript" if c == "_" else "textsuperscript"
            out.append("\\" + tag + "{" + math_text(g) + "}")
            prev = "operand"
        elif c == "\\" and s[i + 1] in ",;! ":
            out.append(" ")
            i += 2
        elif c == "\\" and s[i + 1] in "{}":
            out.append("\\" + s[i + 1])
            prev = "operand" if s[i + 1] == "}" else None
            i += 2
        elif c == "\\":
            name = re.match(r"\\([A-Za-z]+)", s[i:]).group(1)
            i += len(name) + 1
            if name == "mathrm":
                g, i = group(i)
                out.append(g)
                prev = "operand"
            elif name == "sqrt":
                g, i = group(i)
                out.append("√(" + math_text(g) + ")")
                prev = "operand"
            elif name in GREEK:
                out.append("\\emph{" + GREEK[name] + "}")
                prev = "operand"
            elif name == "pm":
                out.append("±")
                prev = None
            elif name in SYM:
                out.append(" " + SYM[name] + " ")
                prev = None
            else:
                raise ValueError("no text form for \\" + name)
        elif c in "=<>":
            out.append(" " + c + " " if prev else c)
            prev = None
            i += 1
        elif c in "+-":
            ch = "−" if c == "-" else "+"
            out.append(" " + ch + " " if prev == "operand" else ch)
            prev = None
            i += 1
        elif c.isalpha():
            out.append("\\emph{" + c + "}")
            prev = "operand"
            i += 1
        elif c == "'":
            out.append("′")
            i += 1
        elif c == "|":
            out.append("|")
            prev = "operand" if prev == "operand" else None
            i += 1
        elif c == "(":
            out.append(c)
            prev = None
            i += 1
        elif c == "/":
            out.append(c)
            prev = None
            i += 1
        elif c.isdigit() or c in ".,)*":
            out.append(c)
            prev = "operand"
            i += 1
        else:
            raise ValueError("no text form for " + c + " in " + s)
    return "".join(out)


keep = r"(\\begin\{(verbatim|equation\*)\}.*?\\end\{\2\})"
pieces = re.split(keep, t, flags=re.S)
for k in range(0, len(pieces), 3):
    pieces[k] = re.sub(r"(?<!\\)\$(.+?)(?<!\\)\$", lambda m: math_text(m.group(1)),
                       pieces[k], flags=re.S)
t = "".join(p for k, p in enumerate(pieces) if k % 3 != 2)

# figures as PNG
for f in ("fig1", "fig2"):
    png = BUILD / f"{f}.png"
    with pdfplumber.open(PAPER / "figures" / f"{f}.pdf") as pdf:
        pdf.pages[0].to_image(resolution=220).save(png)
    t = t.replace(f"figures/{f}.pdf", str(png))

# hand-numbered headings
doc0 = t.index("\\begin{document}")
head, body = t[:doc0], t[doc0:]
sec = sub = 0
appendix = False
parts, pos = [], 0
for m in re.finditer(r"\\appendix\b|\\(section|subsection)(\*?)\{", body):
    if m.group(0).startswith("\\appendix"):
        appendix, sec = True, 0
        continue
    level, star = m.group(1), m.group(2)
    close = balanced(body, m.end() - 1)
    title = body[m.end():close - 1]
    if star:
        continue
    if level == "section":
        sec += 1
        sub = 0
        num = chr(64 + sec) if appendix else str(sec)
        new = f"\\section*{{{num}~{title}}}"
    else:
        sub += 1
        num = (chr(64 + sec) if appendix else str(sec)) + f".{sub}"
        new = f"\\subsection*{{{num}~{title}}}"
    parts.append(body[pos:m.start()])
    parts.append(new)
    pos = close
parts.append(body[pos:])
body = "".join(parts)
body = body.replace("\\bibliography{references}", "\\section*{References}\n\nREFSHERE\n")
t = head + body
left = sorted(set(re.findall(r"\\(?:input|ref|cite)\{", t)))
assert not left, left
(BUILD / "paper_docx.tex").write_text(t)

# pandoc runs in the build folder, because in paper/ the LaTeX reader parses acl.sty
# and runs out of memory
subprocess.run([PANDOC, "paper_docx.tex", "-s", "-t", "native", "-o", "paper.native"],
               check=True, cwd=BUILD, timeout=300)
subprocess.run([PANDOC, "paper.native", "-f", "native", "--citeproc",
                "--bibliography", str(PAPER / "references.bib"),
                "-o", "paper_raw.docx"], check=True, cwd=BUILD, timeout=300)

# restyle, following scripts/post.py of the Sentient Futures paper
d = Document(str(BUILD / "paper_raw.docx"))
ph = [p for p in d.paragraphs if p.text.strip() == "REFSHERE"][0]
bib = [p for p in d.paragraphs if p.style.name == "Bibliography"]
anchor = ph._p
for b in bib:
    anchor.addnext(b._p)
    anchor = b._p
ph._p.getparent().remove(ph._p)
SD = {s.name: s for s in d.styles}
for s in d.sections:
    s.page_width, s.page_height = Cm(21.0), Cm(29.7)
    for a in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(s, a, Cm(2.5))


def font(name, size=None, bold=None):
    if name not in SD:
        return
    st = SD[name]
    f = st.font
    f.name = "Times New Roman"
    f.color.rgb = RGBColor(0, 0, 0)
    rpr = st.element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.append(rf)
    for k in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        if rf.get(qn(k)) is not None:
            del rf.attrib[qn(k)]
    for k in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(k), "Times New Roman")
    if size:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if name.startswith("Heading") or name == "Title":
        f.italic = False


for n, sz, b in [("Normal", 11, None), ("Body Text", 11, None), ("First Paragraph", 11, None),
                 ("Compact", 10, None), ("Title", 16, True), ("Author", 12, None), ("Abstract", 10, None),
                 ("Heading 1", 13, True), ("Heading 2", 11.5, True), ("Heading 3", 11, True),
                 ("Heading 4", 11, True), ("Bibliography", 10, None), ("Caption", 10, None),
                 ("Table Caption", 10, None), ("Image Caption", 10, None)]:
    font(n, sz, b)
for p in d.paragraphs:
    if p.style.name in ("Body Text", "First Paragraph", "Abstract"):
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.15
    if p.style.name == "Image Caption":
        for r in p.runs:
            r.font.italic = False


def border(el, tag, sides):
    pr = el.find(qn(tag))
    if pr is None:
        pr = OxmlElement(tag)
        el.insert(0, pr)
    name = "w:tblBorders" if tag == "w:tblPr" else "w:tcBorders"
    old = pr.find(qn(name))
    if old is not None:
        pr.remove(old)
    b = OxmlElement(name)
    for side, sz in sides.items():
        e = OxmlElement("w:" + side)
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), str(sz))
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "000000")
        b.append(e)
    pr.append(b)


for tb in d.tables:
    border(tb._tbl, "w:tblPr", {"top": 12, "bottom": 12})
    for c in tb.rows[0].cells:
        border(c._tc, "w:tcPr", {"bottom": 6})
    for r in tb.rows:
        for c in r.cells:
            for p in c.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)
                    run.font.name = "Times New Roman"
ab = [p for p in d.paragraphs if p.style.name == "Abstract"][0]
h = ab.insert_paragraph_before("Abstract")
h.alignment = 1
for r in h.runs:
    r.font.bold = True
    r.font.size = Pt(12)
    r.font.name = "Times New Roman"
d.save(str(OUT))
print(OUT, len(d.tables), "tables", len(bib), "references",
      len(d.inline_shapes), "figures")
