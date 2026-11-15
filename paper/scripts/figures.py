"""Figures 1 and 2 of the paper, from the aggregate files data/runs/sprint/analysis_describe.json and
data/runs/sprint/analysis_score.json only.

Figure 1, panel (a), shows D on the half of the items sent without the self-report fields and on the half
sent with them. Panel (b) shows the weight given to a market price and to the same number offered as the
asker's own estimate. Figure 2 shows the CORP reliability diagram of the turn-1 forecasts of every setting and
of the market price on the resolved retro questions (PLAN 6.6), drawn from the block summaries that the
frozen analysis code writes (forecast range, number of forecasts and estimated event probability of each
block). Black and white, Times, sized for a two-column figure* in the ACL template.

Run from the project folder with  python3 -I paper/scripts/figures.py
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
D = json.loads((ROOT / "data/runs/sprint/analysis_describe.json").read_text(encoding="utf-8"))
S = json.loads((ROOT / "data/runs/sprint/analysis_score.json").read_text(encoding="utf-8"))
OUT = ROOT / "paper/figures"

SET = ["haiku_off", "haiku_medium", "sonnet_off", "gpt6luna", "gemini_flash_lite", "mistral_small",
       "deepseek_flash", "qwen_flash", "glm_flash", "gpt_oss_120b", "llama4_scout"]
MARGIN = 0.03          # the equivalence margin of H2 (PLAN 7.2)
OFFSET = 0.17          # vertical offset of the two markers in a row
INK, GRID, BAND = "black", "0.85", "0.88"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times"], "mathtext.fontset": "stix",
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8.5, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "legend.fontsize": 7, "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.0,
    "xtick.major.size": 2.5, "ytick.major.size": 0, "pdf.fonttype": 42, "ps.fonttype": 42,
})


def G(o, path):
    for k in path.split("/"):
        o = o[k]
    return o


def est(o):
    return o["estimate"], o["ci95"][0], o["ci95"][1]


def row(s):
    t = G(D, f"settings/{s}/turn_2")
    return {"label": D["settings"][s]["label"],
            "d_nf": est(G(t, "without_fields/pooled/D/D")), "d_wf": est(G(t, "with_fields/pooled/D/D")),
            "w_m": est(G(t, "without_fields/pooled/weights/w_m")), "w_h": est(G(t, "without_fields/pooled/weights/w_h"))}


def dots(ax, ys, triples, filled, marker):
    for y, (e, lo, hi) in zip(ys, triples):
        ax.plot([lo, hi], [y, y], color=INK, lw=0.8, solid_capstyle="butt", zorder=2)
        ax.plot([e], [y], marker=marker, ms=4.2, mew=0.8, mec=INK, mfc=INK if filled else "white",
                ls="none", zorder=3)


def fig1(preview=None):
    rows = sorted((row(s) for s in SET), key=lambda r: -r["d_nf"][0])
    n = len(rows)
    ys = list(range(n))
    fig, (a, b) = plt.subplots(1, 2, sharey=True, figsize=(6.3, 2.75))
    fig.subplots_adjust(left=0.165, right=0.99, bottom=0.15, top=0.80, wspace=0.07)

    for ax in (a, b):
        ax.set_ylim(n - 0.45, -0.55)
        ax.set_yticks(ys)
        ax.grid(axis="x", color=GRID, lw=0.4, zorder=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.set_axisbelow(True)
    a.set_yticklabels([r["label"] for r in rows])

    # panel (a): D without and with the self-report fields
    a.axvspan(-MARGIN, MARGIN, color=BAND, lw=0, zorder=1)
    a.axvline(0, color=INK, lw=0.5, zorder=1)
    dots(a, [y - OFFSET for y in ys], [r["d_nf"] for r in rows], True, "o")
    dots(a, [y + OFFSET for y in ys], [r["d_wf"] for r in rows], False, "o")
    a.set_xlim(-0.045, 0.335)
    a.set_xticks([0, 0.1, 0.2, 0.3])
    a.set_xticklabels(["0", "0.1", "0.2", "0.3"])
    a.set_xlabel(r"$D$, mean of $p_2$(enthusiast) $-$ $p_2$(sceptic)")
    a.set_title("(a) Change toward the asker", loc="left", pad=25)
    filled = Line2D([], [], marker="o", ms=4.2, mew=0.8, mec=INK, mfc=INK, color=INK, lw=0.8, label="Without the fields")
    hollow = Line2D([], [], marker="o", ms=4.2, mew=0.8, mec=INK, mfc="white", color=INK, lw=0.8, label="With the fields")
    band = Patch(facecolor=BAND, edgecolor="none", label=r"Equivalence margin of $\pm$0.03")
    a.legend(handles=[filled, band, hollow], loc="lower left", bbox_to_anchor=(0.0, 1.02), ncol=2, frameon=False,
             borderaxespad=0, handlelength=1.6, columnspacing=1.0, handletextpad=0.5)

    # panel (b): weight on a market price and on the asker's own estimate
    for x in (0, 1):
        b.axvline(x, color=INK, lw=0.6, ls=(0, (1, 1.6)), zorder=1)
    dots(b, [y - OFFSET for y in ys], [r["w_m"] for r in rows], True, "s")
    dots(b, [y + OFFSET for y in ys], [r["w_h"] for r in rows], False, "s")
    b.set_xlim(-0.08, 1.12)
    b.set_xticks([0, 0.25, 0.5, 0.75, 1])
    b.set_xticklabels(["0", "0.25", "0.5", "0.75", "1"])
    b.set_xlabel("Weight on the number shown")
    b.set_title("(b) Market price against the asker's own estimate", loc="left", pad=25)
    b.legend(handles=[Line2D([], [], marker="s", ms=4.2, mew=0.8, mec=INK, mfc=INK, color=INK, lw=0.8,
                             label=r"Market price, $w_m$"),
                      Line2D([], [], marker="s", ms=4.2, mew=0.8, mec=INK, mfc="white", color=INK, lw=0.8,
                             label=r"Asker's own estimate, $w_h$")],
             loc="lower left", bbox_to_anchor=(0.0, 1.02), ncol=1, frameon=False, borderaxespad=0,
             handlelength=1.6, columnspacing=1.0, handletextpad=0.5)

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "fig1.pdf")
    if preview:  # a PNG for checking the layout, written outside the project folder
        fig.savefig(preview, dpi=300)
    print("rows top to bottom:", [r["label"] for r in rows])
    print("wrote", OUT / "fig1.pdf")


def fig2(preview=None):
    """CORP reliability diagrams (Dimitriadis, Gneiting and Jordan 2021), one panel per setting plus the market.

    Each block of forecasts that receives one estimated event probability is drawn flat over its forecast
    range, and neighbouring blocks are joined by straight lines. The circle at the middle of each block has an
    area proportional to the number of forecasts in the block. Only block summaries are drawn, never items.
    """
    panels = [(D["settings"][s]["label"], G(S, f"settings/{s}/retro/turn_1_accuracy/corp")) for s in SET]
    panels.append(("Market price", G(S, "market_price_accuracy/retro/corp")))
    fig, axes = plt.subplots(3, 4, sharex=True, sharey=True, figsize=(6.3, 5.2))
    fig.subplots_adjust(left=0.085, right=0.99, bottom=0.085, top=0.965, wspace=0.10, hspace=0.30)
    for ax, (label, corp) in zip(axes.flat, panels):
        xs, ys, mx, my, area = [], [], [], [], []
        for blk in corp["diagram"]:
            xs += [blk["x_lo"], blk["x_hi"]]
            ys += [blk["cep"], blk["cep"]]
            mx.append((blk["x_lo"] + blk["x_hi"]) / 2)
            my.append(blk["cep"])
            area.append(0.45 * blk["n"])
        ax.plot([0, 1], [0, 1], color=INK, lw=0.6, ls=(0, (1, 1.6)), zorder=1)
        ax.plot(xs, ys, color=INK, lw=1.0, zorder=3, solid_joinstyle="miter")
        ax.scatter(mx, my, s=area, facecolors="white", edgecolors=INK, linewidths=0.5, zorder=4)
        ax.set_xlim(-0.03, 1.03)
        ax.set_ylim(-0.03, 1.03)
        ax.set_aspect("equal")
        ax.set_xticks([0, 0.5, 1])
        ax.set_yticks([0, 0.5, 1])
        ax.set_xticklabels(["0", "0.5", "1"])
        ax.set_yticklabels(["0", "0.5", "1"])
        ax.tick_params(axis="y", which="major", width=0.6, length=2.5)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.set_title(label, loc="left", pad=3)
        ax.text(0.98, 0.03, f"MCB {corp['mcb']['estimate']:.3f}\nDSC {corp['dsc']['estimate']:.3f}",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=6.5, linespacing=1.2)
    fig.supxlabel("First forecast probability", y=0.012, fontsize=8)
    fig.supylabel("Estimated probability of a Yes outcome", x=0.012, fontsize=8)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "fig2.pdf")
    if preview:
        fig.savefig(preview, dpi=300)
    print("panels:", [p[0] for p in panels])
    print("wrote", OUT / "fig2.pdf")


def main():
    pre = sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else None
    fig1(pre.replace(".png", "_fig1.png") if pre else None)
    fig2(pre.replace(".png", "_fig2.png") if pre else None)


if __name__ == "__main__":
    main()
