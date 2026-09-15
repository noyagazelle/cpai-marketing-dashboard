"""
Recommendations + written-analysis engine.

Two responsibilities, both grounded in numbers the app already computed:

1. `recommendations(...)` — deterministic, prioritized, specific actions derived
   from the same findings that power the executive summary.
2. `write_analysis(...)` — a written narrative for leadership. If an Anthropic
   key is present it uses Claude to *phrase* the verified facts (it is explicitly
   forbidden from inventing numbers); otherwise it composes a solid rule-based
   narrative from the same facts. Either way the underlying numbers are shown
   alongside, so nothing is unverifiable.
"""
from __future__ import annotations

import re

import pandas as pd

import config
from analysis import linkedin as L
from analysis import ga4 as G
from analysis import cross_channel as CC

_LI_ER_BENCH = (0.02, 0.04)


# --------------------------------------------------------------------------- #
# Recommendations
# --------------------------------------------------------------------------- #
def _assign_tiers(recs: list[dict]) -> list[dict]:
    """Assign RELATIVE priority by rank so there's always a clear spread:
    top third = High (tackle first), middle = Medium, bottom third = Low."""
    recs.sort(key=lambda r: r["score"], reverse=True)
    n = len(recs)
    if n == 0:
        return recs
    high_cut = max(1, round(n / 3))          # at least one High
    med_cut = max(high_cut + 1, round(2 * n / 3)) if n > 2 else n
    for i, r in enumerate(recs):
        r["priority"] = "High" if i < high_cut else ("Medium" if i < med_cut else "Low")
    return recs


def recommendations(data: dict, ga4=None, merged: pd.DataFrame | None = None,
                    corrs: list[dict] | None = None) -> list[dict]:
    """Return prioritized recs: {title, detail, priority, category, score}."""
    recs: list[dict] = []

    def add(score, title, detail, category, theme):
        # `theme` groups overlapping advice so we never show two recs that say
        # essentially the same thing (only the strongest per theme survives).
        recs.append({"score": score, "priority": None, "title": title,
                     "detail": detail, "category": category, "theme": theme})

    followers = data.get("followers")
    content = data.get("content")

    # --- Followers ---
    if followers:
        f = L.followers_summary(followers)
        if f:
            if f.get("sponsored") in (0, None) and f["new_total"] > 0:
                add(60, "Test paid amplification on your best organic posts",
                    f"All {f['new_total']:,} new followers this period came in organically — "
                    "efficient, but you're leaving reach on the table. Boost your 2–3 highest-"
                    "engagement posts to lookalike audiences and measure follower cost.",
                    "Followers", "paid")
            sp = f["split"]
            if sp.get("available") and sp.get("delta") is not None and sp["delta"] <= -0.15:
                add(72, "Reverse the follower-growth slowdown",
                    f"New-follower pace fell {abs(sp['delta']):.0%} in the recent half. Revisit "
                    "the topics/formats that drove the strong earlier days and repeat them.",
                    "Followers", "followers_slowdown")

    # --- Content ---
    if content:
        c = L.content_summary(content)
        perf = L.content_type_perf(content)
        cad = L.cadence(content)
        if perf is not None and "EngRate" in perf and len(perf) >= 2:
            best = perf.iloc[0]
            rest = perf.iloc[1:]["EngRate"].mean()
            if rest and best["EngRate"] >= rest * 1.25:
                mult = best["EngRate"] / rest
                add(82, f"Publish more {str(best['ContentType']).lower()} content",
                    f"{best['ContentType']} posts engage ~{mult:.1f}× the rest "
                    f"({best['EngRate']:.1%} vs {rest:.1%}). Shift the content mix toward this "
                    "format for the next few weeks and watch engagement rate.", "Content", "content_type")
        if cad:
            wd = cad["by_weekday"].dropna(subset=["Avg engagement rate"])
            if len(wd) >= 2:
                bestrow = wd.loc[wd["Avg engagement rate"].idxmax()]
                add(58, f"Concentrate posting around {bestrow['Weekday']}",
                    f"{bestrow['Weekday']} shows the highest average engagement "
                    f"({bestrow['Avg engagement rate']:.1%}). Schedule priority posts then.",
                    "Content", "cadence_day")
            if cad["per_week"] < 3:
                add(64, "Increase posting cadence",
                    f"Cadence is ~{cad['per_week']}/week. Lifting to 3–5 quality posts/week "
                    "is the most direct lever on total reach while engagement holds.", "Content", "post_more")
        if c and c["agg_engagement_rate"] is not None:
            er = c["agg_engagement_rate"]
            if er >= _LI_ER_BENCH[1]:
                add(66, "Scale reach while engagement is strong",
                    f"Engagement rate is {er:.1%}, above the {_LI_ER_BENCH[0]:.0%}–"
                    f"{_LI_ER_BENCH[1]:.0%} benchmark — a green light to increase volume and "
                    "test paid amplification without diluting quality.", "Content", "reach")
            elif er < _LI_ER_BENCH[0]:
                add(70, "Fix content resonance before scaling volume",
                    f"Engagement rate is {er:.1%}, below the {_LI_ER_BENCH[0]:.0%}–"
                    f"{_LI_ER_BENCH[1]:.0%} benchmark. Prioritise message clarity and format "
                    "quality over posting more.", "Content", "engagement")
        if c and c["split_impressions"].get("available"):
            d = c["split_impressions"].get("delta")
            if d is not None and d <= -0.2:
                add(68, "Refresh topics to arrest the reach decline",
                    f"Impressions fell {abs(d):.0%} in the recent half. Rotate in new angles/"
                    "formats and re-test your previously top-performing themes.", "Content", "reach")

    # --- GA4 ---
    if ga4 is not None and ga4.by_channel is not None and "sessions" in getattr(ga4.by_channel, "columns", []):
        ch = ga4.by_channel.copy()
        ch["sessions"] = pd.to_numeric(ch["sessions"], errors="coerce")
        ch = ch.sort_values("sessions", ascending=False)
        if not ch.empty:
            total = ch["sessions"].sum()
            top = ch.iloc[0]
            share = top["sessions"] / total if total else 0
            name = str(top.iloc[0])
            if "social" in name.lower():
                add(74, "Sustain and instrument your LinkedIn/social pipeline",
                    f"{name} is your top traffic source ({share:.0%} of sessions). Keep "
                    "investing, and add UTM tags to LinkedIn links so conversions are "
                    "attributable end-to-end.", "Website", "channel")
            else:
                add(56, f"Grow the underused social channel",
                    f"{name} leads traffic ({share:.0%}); social is comparatively small. "
                    "There's headroom to convert LinkedIn reach into site visits.", "Website", "channel")

    # --- Cross-channel ---
    if corrs:
        best = corrs[0]
        if abs(best["r"]) >= 0.4 and best["r"] > 0:
            add(70, "Time site campaigns to your LinkedIn pushes",
                f"{best['x_label']} and {best['y_label'].lower()} move together "
                f"(r={best['r']:.2f}). Align landing-page pushes and offers with your "
                "highest-reach LinkedIn days.", "Cross-channel", "crosschannel")
    if merged is not None and not merged.empty:
        for tgt in ("social_sessions", "li_page_views"):
            lift = CC.post_day_lift(merged, tgt)
            if lift and lift["lift"] is not None and lift["lift"] >= 0.15:
                add(62, "Post more often — posting days measurably outperform",
                    f"On days you post, {CC.COL_LABELS[tgt].lower()} run {lift['lift']:+.0%} vs "
                    f"quiet days ({lift['post_avg']:.0f} vs {lift['nonpost_avg']:.0f}).",
                    "Cross-channel", "post_more")
                break

    # De-duplicate: keep only the strongest recommendation per theme, so we never
    # surface two overlapping/contradictory pieces of advice.
    best_by_theme: dict = {}
    for r in recs:
        t = r["theme"]
        if t not in best_by_theme or r["score"] > best_by_theme[t]["score"]:
            best_by_theme[t] = r
    return _assign_tiers(list(best_by_theme.values()))


# --------------------------------------------------------------------------- #
# Written analysis (AI or rule-based)
# --------------------------------------------------------------------------- #
def ai_status() -> dict:
    try:
        import anthropic  # noqa: F401
        installed = True
    except Exception:
        installed = False
    bedrock_model = config.bedrock_model()
    if bedrock_model:
        return {"available": installed, "provider": "bedrock", "installed": installed,
                "model": bedrock_model}
    key = config.anthropic_key()
    return {"available": bool(key) and installed, "provider": "anthropic", "has_key": bool(key),
            "installed": installed, "model": config.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")}


def _strip_md(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s)


def _facts_block(kpis: list[dict], takeaways: list[dict], recs: list[dict]) -> str:
    lines = ["KPIS:"]
    for k in kpis:
        d = k.get("delta")
        dtxt = f" ({d:+.0%} {k.get('context','')})" if isinstance(d, (int, float)) else ""
        lines.append(f"- {k['label']}: {k['value']}{dtxt}")
    lines.append("\nFINDINGS:")
    for t in takeaways:
        lines.append(f"- {_strip_md(t['text'])}")
    lines.append("\nRECOMMENDATIONS (prioritized):")
    for r in recs:
        lines.append(f"- [{r['priority']}] {r['title']}: {_strip_md(r['detail'])}")
    return "\n".join(lines)


_AI_SYSTEM = (
    "You are a marketing analyst writing a concise executive brief for the Head of "
    "Marketing at CyberproAI. You will be given VERIFIED facts (KPIs, findings, "
    "recommendations) computed from the company's own LinkedIn and website analytics. "
    "Write 2–3 short paragraphs in plain, confident business language. "
    "STRICT RULE: use ONLY the numbers and facts provided — never invent, estimate, or "
    "extrapolate any figure. Do not add metrics that aren't given. No bullet lists, no "
    "headings; flowing prose. End with one sentence on the single highest-priority action."
)


def _ai_narrative(facts: str, model: str, provider: str) -> str:
    if provider == "bedrock":
        from anthropic import AnthropicBedrock
        client = AnthropicBedrock(aws_region=config.get("AWS_DEFAULT_REGION", "us-east-1"))
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=config.anthropic_key())
    msg = client.messages.create(
        model=model, max_tokens=700, system=_AI_SYSTEM,
        messages=[{"role": "user", "content":
                   f"Here are the verified facts for this period:\n\n{facts}\n\n"
                   "Write the executive brief now."}],
    )
    return "".join(getattr(b, "text", "") for b in msg.content).strip()


def _rule_based(kpis: list[dict], takeaways: list[dict], recs: list[dict]) -> str:
    if not takeaways and not recs:
        return "Not enough data yet to write an analysis. Load more history to enable it."
    goods = [t["text"] for t in takeaways if t["tone"] == "good"]
    bads = [t["text"] for t in takeaways if t["tone"] == "bad"]
    neutrals = [t["text"] for t in takeaways if t["tone"] == "neutral"]

    p1 = "**This period at a glance.** "
    if goods:
        p1 += "On the upside, " + _join(goods[:2]) + " "
    if bads:
        p1 += "Areas to watch: " + _join(bads[:2]) + " "
    if neutrals and not (goods and bads):
        p1 += _join(neutrals[:1]) + " "

    p2 = ""
    if recs:
        top = recs[:3]
        p2 = "**Where to focus next.** " + _join([f"{r['title'].lower()}" for r in top]) + \
             f" The single highest priority is to **{recs[0]['title'].lower()}** — {_strip_md(recs[0]['detail'])}"
    return (p1.strip() + "\n\n" + p2.strip()).strip()


def _join(items: list[str]) -> str:
    items = [i.rstrip(".") for i in items]
    if not items:
        return ""
    if len(items) == 1:
        return items[0] + "."
    return "; ".join(items[:-1]) + "; and " + items[-1] + "."


def write_analysis(kpis: list[dict], takeaways: list[dict], recs: list[dict],
                   prefer_ai: bool = True) -> dict:
    """Return {text, mode, error}. mode is 'ai' or 'rule-based'."""
    st = ai_status()
    if prefer_ai and st["available"]:
        try:
            text = _ai_narrative(_facts_block(kpis, takeaways, recs), st["model"], st["provider"])
            if text:
                return {"text": text, "mode": "ai", "error": None, "model": st["model"]}
        except Exception as e:
            return {"text": _rule_based(kpis, takeaways, recs), "mode": "rule-based",
                    "error": f"AI generation failed ({e}); showing rule-based narrative."}
    return {"text": _rule_based(kpis, takeaways, recs), "mode": "rule-based", "error": None}
