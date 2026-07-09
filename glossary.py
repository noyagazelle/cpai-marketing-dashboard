"""
Plain-English definitions for every metric shown in the dashboard.

Kept in one place so the little "what this means" hints stay consistent across
tabs. Views pull hints from HINTS[...] and pass them to ui.kpi(hint=...).
"""

HINTS = {
    # --- LinkedIn: followers ---
    "new_followers": "People who newly followed the CyberproAI LinkedIn page in this period.",
    "avg_followers_day": "Average number of new followers gained per day.",
    "total_followers": "Total people who follow the page, taken from the number shown on your "
                       "LinkedIn page. Update it each period on the Upload & connect tab.",
    "est_audience": "Approximate total followers, estimated from the demographic breakdowns. "
                    "This UNDERCOUNTS (it only counts followers whose attribute is filled in) — "
                    "enter the real number on the Upload & connect tab for an exact figure.",
    "period_growth": "New followers this period as a share of your total follower base.",

    # --- LinkedIn: content ---
    "impressions": "Number of times our LinkedIn posts were shown in people's feeds.",
    "engagements": "Total interactions on our posts: clicks + reactions + comments + reposts.",
    "engagement_rate": "Share of impressions that led to an interaction (click, reaction, comment or repost). "
                       "2–4% is a typical LinkedIn range.",
    "reactions_comments_reposts": "The three main interaction types, shown as reactions / comments / reposts.",

    # --- LinkedIn: page visitors ---
    "page_views": "Times the LinkedIn page itself was viewed (not the posts — the page).",
    "unique_visitors": "Distinct people who viewed the LinkedIn page.",
    "mobile_share": "Share of LinkedIn page views that came from a phone rather than a computer.",
    "top_section": "Which part of the page (Overview / Jobs / Life) got the most views.",

    # --- Website (GA4) ---
    "ga4_users": "People who visited the CyberproAI website.",
    "ga4_new_users": "First-time visitors to the website.",
    "ga4_sessions": "Visits to the website — one person can have several sessions.",
    "ga4_engaged_sessions": "Visits that were 'engaged' — lasted 10s+, caused a key event, or viewed 2+ pages.",
    "ga4_engagement_rate": "Share of visits that were 'engaged' — lasted 10+ seconds, triggered a key "
                           "event, or viewed 2+ pages.",
    "ga4_avg_time": "Average time a visitor actively spent on the site per visit.",
    "ga4_key_events": "Conversions / important actions on the site (e.g. form fills, sign-ups) — if configured in GA4.",
    "ga4_page_views": "Total number of pages viewed across the whole website.",

    # --- Cross-channel ---
    "post_day_avg": "Average on days when we published at least one LinkedIn post.",
    "quiet_day_avg": "Average on days when we published nothing.",
    "post_lift": "How much higher (or lower) the metric runs on posting days versus quiet days.",
    "correlation": "How closely two things move together, on a scale of -1 to +1. "
                   "Near +1 = they rise and fall together; near 0 = no relationship; "
                   "negative = one rises as the other falls. Association, not proof of cause.",
}

# GA4 metric name -> glossary key
GA4_HINT_KEY = {
    "totalUsers": "ga4_users", "newUsers": "ga4_new_users", "sessions": "ga4_sessions",
    "engagedSessions": "ga4_engaged_sessions", "engagementRate": "ga4_engagement_rate",
    "averageSessionDuration": "ga4_avg_time", "keyEvents": "ga4_key_events",
    "screenPageViews": "ga4_page_views",
}


def hint(key: str) -> str:
    return HINTS.get(key, "")


def ga4_hint(metric: str) -> str:
    return HINTS.get(GA4_HINT_KEY.get(metric, ""), "")
