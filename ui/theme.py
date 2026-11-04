"""Couleurs, styles et petits éléments partagés par les écrans."""
from html import escape

import plotly.graph_objects as go
import streamlit as st

# Palette validée avec le script du skill dataviz, dans cet ordre fixe. Une famille garde toujours sa couleur.
FAMILY_COLORS = {"Acier": "#2a78d6", "Aluminium": "#eb6834", "Acier électrique": "#1baf7a", "Cuivre": "#eda100", "Fonte": "#e87ba4", "Polymère": "#008300", "Magnésium": "#6250d6"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
# Maturité : échelle ordonnée à une seule teinte, plus sombre quand la pièce est plus avancée.
MATURITY_COLORS = {"PRIVATE": "#b7d3f6", "IN_WORK": "#3987e5", "FROZEN": "#1c5cab", "RELEASED": "#0d366b", "OBSOLETE": "#d03b3b"}
STATUS_COLORS = {"Prêt": "#0ca30c", "À promouvoir": "#fab219", "En retard": "#ec835a", "Bloquant": "#d03b3b", "À exclure": "#c3c2b7"}
LEVEL_COLORS = {"Critique": "#d03b3b", "Élevé": "#ec835a", "Modéré": "#fab219", "Faible": "#0ca30c"}
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#6c6b66"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#ffffff"
NEUTRAL_BAR = "#52514e"

CSS = """
<style>
.stMainBlockContainer { padding: 1rem 1.6rem 5rem; max-width: 100%; }
/* Assistant : bouton flottant, puis panneau sur le quart gauche. Le contenu de la page se décale au lieu d'être recouvert. */
.stMainBlockContainer:has(.st-key-chat_panel) { margin-left: max(25vw, 320px); width: calc(100% - max(25vw, 320px)); }
.st-key-chat_toggle { position: fixed; left: 20px; bottom: 20px; z-index: 1000; width: auto; }
.st-key-chat_toggle button { background: #0d366b; color: #fff; border: 0; border-radius: 999px; padding: 8px 18px; box-shadow: 0 2px 10px rgba(0,0,0,.25); }
.st-key-chat_toggle button:hover, .st-key-chat_toggle button:focus { background: #1c5cab; color: #fff; }
.st-key-chat_panel { position: fixed; left: 0; top: 0; bottom: 0; width: 25vw; min-width: 320px; height: 100vh; z-index: 1000000; background: #fff; border-right: 1px solid #e1e0d9; padding: 12px 14px; overflow: hidden; box-shadow: 2px 0 12px rgba(0,0,0,.08); }
.st-key-chat_panel > [data-testid="stLayoutWrapper"]:has(> .st-key-chat_history) { flex: 1 1 0 !important; height: auto !important; min-height: 0; }
.st-key-chat_history { height: 100% !important; }
.plm-table { width: 100%; border-collapse: collapse; font-size: .86rem; line-height: 1.3; margin-bottom: .6rem; }
.plm-table th { text-align: left; font-weight: 600; color: #52514e; border-bottom: 1px solid #c3c2b7; padding: 4px 8px 4px 0; }
.plm-table td { border-bottom: 1px solid #e1e0d9; padding: 4px 8px 4px 0; vertical-align: top; }
.plm-table td.num, .plm-table th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.ia-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(380px, 100%), 1fr)); gap: 12px; margin-bottom: .6rem; }
.ia-card { border: 1px solid #e1e0d9; border-radius: 8px; padding: 10px 12px; background: #fff; }
.ia-card h5 { font-size: .95rem; font-weight: 600; margin: 0 0 6px; padding: 0; color: #0b0b0b; }
.ia-group { margin-bottom: 9px; }
.ia-group:last-child { margin-bottom: 0; }
.ia-head { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; font-size: .8rem; color: #52514e; margin-bottom: 2px; }
.ia-delta { font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }
.ia-delta.good { color: #0a7f0a; }
.ia-delta.bad { color: #b52f2f; }
.ia-delta.neutral { color: #52514e; }
.ia-delta.same { color: #6c6b66; font-weight: 400; }
.ia-row { display: grid; grid-template-columns: 62px minmax(0, 1fr) 86px; align-items: center; gap: 6px; font-size: .76rem; color: #52514e; line-height: 1.25rem; }
.ia-track { display: block; height: 12px; background: #f2f1ed; border-radius: 3px; overflow: hidden; }
.ia-track i { display: block; height: 100%; border-radius: 3px; }
.ia-val { text-align: right; color: #0b0b0b; font-variant-numeric: tabular-nums; white-space: nowrap; }
.ia-foot { font-size: .78rem; color: #52514e; margin-top: 6px; }
[data-testid="stMetric"] { background: #f7f7f4; border-radius: 8px; padding: 8px 12px; }
[data-testid="stMetricValue"] { font-size: 1.18rem; font-weight: 600; line-height: 1.25; height: auto; }
[data-testid="stMetricValue"] * { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }
[data-testid="stMetricLabel"] { height: auto; }
[data-testid="stMetricLabel"] * { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }
[data-testid="stMetricLabel"] p { font-size: .76rem; color: #52514e; line-height: 1.2; }
.st-key-main_tab > div > [data-baseweb="tab-list"] button p, .st-key-main_tab [role="tablist"]:first-of-type button p { font-size: 1.05rem; font-weight: 600; }
.plm-header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px; margin-bottom: .2rem; }
.plm-header h1 { font-size: 1.45rem; font-weight: 700; margin: 0; padding: 0; }
.plm-header span { color: #52514e; font-size: .85rem; }
.plm-badges { display: flex; flex-wrap: wrap; gap: 5px; margin: 0 0 .5rem; }
.plm-badge { display: inline-block; font-size: .74rem; line-height: 1.2rem; padding: 0 7px; border-radius: 4px; background: #f0efec; color: #0b0b0b; white-space: nowrap; }
.plm-alert { display: flex; gap: 8px; padding: 6px 10px; border-radius: 6px; background: #f7f7f4; margin-bottom: 5px; font-size: .86rem; line-height: 1.3; }
.plm-alert b { white-space: nowrap; font-weight: 600; }
.plm-note { padding: 8px 12px; border-radius: 6px; background: #eef3fa; margin-bottom: .6rem; font-size: .9rem; line-height: 1.35; }
.plm-note b { font-weight: 600; }
.plm-verdict { padding: 10px 14px; border-radius: 8px; margin-bottom: .6rem; font-size: 1rem; font-weight: 600; color: #fff; }
.plm-legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: .8rem; color: #52514e; margin-bottom: .2rem; }
.plm-legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
.plm-kv { display: grid; grid-template-columns: minmax(110px, 170px) minmax(0, 1fr); gap: 3px 10px; font-size: .88rem; margin-bottom: .5rem; }
.plm-kv dt { color: #6c6b66; margin: 0; }
.plm-kv dd { margin: 0; overflow-wrap: anywhere; }
.plm-origin { font-size: .72rem; color: #6c6b66; }
.plm-source { font-size: .78rem; line-height: 1.3; margin-bottom: 4px; }
.plm-source code { font-size: .72rem; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def html(markup):
    st.markdown(markup, unsafe_allow_html=True)


def badges(items):
    """items : liste de (texte, couleur de fond ou None)."""
    spans = []
    for text, color in items:
        if color:
            ink = "#ffffff" if color in ("#0d366b", "#1c5cab", "#3987e5", "#d03b3b", "#0ca30c", "#008300", "#2a78d6") else INK
            spans.append(f'<span class="plm-badge" style="background:{color};color:{ink}">{escape(str(text))}</span>')
        else:
            spans.append(f'<span class="plm-badge">{escape(str(text))}</span>')
    html(f'<div class="plm-badges">{"".join(spans)}</div>')


def note(text):
    html(f'<div class="plm-note">{text}</div>')


def verdict(text, good):
    html(f'<div class="plm-verdict" style="background:{"#0a7f0a" if good else "#d03b3b"}">{escape(text)}</div>')


def key_values(rows):
    items = "".join(f"<dt>{escape(str(k))}</dt><dd>{v}</dd>" for k, v in rows)
    html(f'<dl class="plm-kv">{items}</dl>')


def table(headers, rows, numeric=()):
    """Petit tableau dont le texte passe à la ligne, pour les barèmes. Les cellules sont du texte, échappé ici."""
    def cell(tag, index, value):
        return f'<{tag} class="num">{escape(str(value))}</{tag}>' if index in numeric else f"<{tag}>{escape(str(value))}</{tag}>"

    head = "".join(cell("th", i, h) for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(cell("td", i, v) for i, v in enumerate(row)) + "</tr>" for row in rows)
    st.html(f'<table class="plm-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>')


def legend(colors):
    items = "".join(f'<span><i style="background:{color}"></i>{escape(label)}</span>' for label, color in colors.items())
    html(f'<div class="plm-legend">{items}</div>')


def style_figure(fig, height=320, legend_visible=True, title=None, margin=None):
    fig.update_layout(
        height=height,
        template="none",
        title=dict(text=title, font=dict(size=14, color=INK), x=0, xanchor="left", y=0.98, yanchor="top") if title else None,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family='"Source Sans Pro", "Source Sans 3", system-ui, "Segoe UI", sans-serif', size=12, color=INK2),
        margin=margin or dict(l=8, r=16, t=40 if title else 10, b=8),
        separators=", ",
        barcornerradius=3,
        hoverlabel=dict(bgcolor=SURFACE, font=dict(color=INK), bordercolor=BASELINE, align="left"),
        showlegend=legend_visible,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, xanchor="left", title_text="", font=dict(size=12)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=BASELINE, tickcolor=BASELINE, automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False, linecolor=BASELINE, automargin=True)
    return fig


def show(fig, key=None):
    st.plotly_chart(fig, width="stretch", theme=None, key=key, config={"displayModeBar": False, "locale": "fr"})


def hbar(labels, values, colors=None, texts=None, height=None, title=None, xaxis_title=None, hover=None):
    """Barres horizontales, la plus grande en haut. Fines, avec une valeur au bout."""
    labels, values = list(labels)[::-1], list(values)[::-1]
    height = height or 62 + 27 * len(labels)
    row_height = max(height - 62, 20) / max(len(labels), 1)
    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker=dict(color=list(colors)[::-1] if colors else NEUTRAL_BAR, line=dict(width=0)),
        text=list(texts)[::-1] if texts else None,
        textposition="outside",
        cliponaxis=False,
        hovertext=list(hover)[::-1] if hover else None,
        hoverinfo="text" if hover else "x+y",
        width=min(0.62, 24 / row_height),  # barres fines : 24 px au plus
    ))
    style_figure(fig, height=height, legend_visible=False, title=title)
    fig.update_yaxes(showgrid=False, type="category", ticklabelstandoff=4)
    fig.update_xaxes(showgrid=True, gridcolor=GRID, title_text=xaxis_title, zeroline=True, zerolinecolor=BASELINE)
    if values and texts:  # de la place pour la valeur écrite au bout de la barre
        low, high = min(min(values), 0), max(max(values), 0)
        span = (high - low) or 1
        fig.update_xaxes(range=[low - (0.22 * span if low < 0 else 0), high + 0.22 * span])
    return fig


def sources_expander(model, sources, label="Sources PLM utilisées"):
    """Liste les éléments PLM réellement lus par le calcul."""
    unique = {}
    for source in sources:
        unique.setdefault((source["type"], source["id"]), source)
    with st.expander(f"{label} ({len(unique)})"):
        rows = [{"Type": s["type"], "Élément": s["label"], "ID PLM": s["plm_id"], "ID XML / fournisseur": s["id"], "Champs utilisés": s.get("fields", "")} for s in unique.values()]
        st.dataframe(rows, hide_index=True, width="stretch")
        st.caption(f"Fichier : {model.data['source_file']}. Structure, masses, matériaux, révisions courantes et positions viennent de l'export d'origine ; le reste est simulé.")
