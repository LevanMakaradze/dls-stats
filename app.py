import re
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import requests

# =============================================================================
# PAGE CONFIG & GLOBAL STYLE
# =============================================================================
st.set_page_config(page_title="DLS Stats", page_icon="🎬", layout="wide")

ACCENT = "#00e054"      # letterboxd green
ACCENT_2 = "#40bcf4"    # letterboxd blue
ACCENT_3 = "#ff8000"    # letterboxd orange
BG = "#14181c"
CARD = "#1c2228"
BAR_LINE = "#0b0f12"

st.markdown(f"""
    <style>
    .stApp {{ background-color: {BG}; }}
    html, body, [class*="css"] {{ color: #cfd8dc; }}
    h1, h2, h3 {{ color: {ACCENT} !important; font-family: 'Trebuchet MS', sans-serif; letter-spacing: 0.5px; }}
    h4, h5 {{ color: {ACCENT_2} !important; }}

    /* Metric cards */
    div[data-testid="stMetric"] {{
        background: linear-gradient(145deg, {CARD}, #232a32);
        padding: 18px 16px;
        border-radius: 14px;
        border: 1px solid #2f3944;
        box-shadow: 0 4px 14px rgba(0,0,0,0.35);
    }}
    div[data-testid="stMetricLabel"] {{ color: #8fa3ab !important; font-size: 0.85rem; }}
    div[data-testid="stMetricValue"] {{ color: {ACCENT} !important; }}

    /* Tabs */
    button[data-baseweb="tab"] {{ font-size: 1rem; font-weight: 600; }}

    /* Posters */
    div[data-testid="stImage"] img {{
        border-radius: 10px;
        box-shadow: 0 6px 16px rgba(0,0,0,0.55);
        transition: transform 0.15s ease-in-out;
    }}
    div[data-testid="stImage"] img:hover {{ transform: scale(1.03); }}

    /* Poster card container */
    .poster-card {{
        background: {CARD};
        border-radius: 12px;
        padding: 10px;
        border: 1px solid #2a323b;
        text-align: center;
        margin-bottom: 14px;
    }}
    .poster-title {{ font-weight: 700; color: #e5f2ea; font-size: 0.95rem; margin-top: 8px; }}
    .poster-sub {{ color: #7d939c; font-size: 0.8rem; }}
    .rank-badge {{
        display: inline-block; background: {ACCENT}; color: #0b0f12; font-weight: 800;
        border-radius: 50%; width: 26px; height: 26px; line-height: 26px; margin-bottom: 6px;
    }}

    .stDataFrame {{ border-radius: 10px; overflow: hidden; }}
    hr {{ border-color: #2a323b; }}
    </style>
""", unsafe_allow_html=True)

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor=BG,
    plot_bgcolor=BG,
    font=dict(color="#cfd8dc"),
    margin=dict(l=10, r=10, t=50, b=10),
)


def add_bar_border(fig, width=1.5, color=BAR_LINE):
    """Adds a visible border/outline to each bar/column in a plotly bar figure."""
    fig.update_traces(marker_line_color=color, marker_line_width=width, selector=dict(type="bar"))
    return fig


def fmt2(fig_axis_update_fn, **kwargs):
    """Small helper placeholder kept for readability at call sites (no-op wrapper)."""
    return fig_axis_update_fn(**kwargs)


# =============================================================================
# DATA LOADING
# =============================================================================
@st.cache_data
def load_data():
    try:
        top_fours = pd.read_csv("letterboxd_top_fours.csv")
        ratings = pd.read_csv("letterboxd_all_ratings.csv")
        return top_fours, ratings
    except FileNotFoundError:
        return None, None


def get_tmdb_key():
    """Returns (key, mode) where mode is 'v3' or 'v4' (bearer token)."""
    key = st.secrets.get("TMDB_API_KEY", None)
    if not key:
        return None, None
    # v4 read access tokens are long JWTs starting with 'eyJ'
    if key.startswith("eyJ") or len(key) > 60:
        return key, "v4"
    return key, "v3"


@st.cache_data(show_spinner=False, ttl=60 * 60 * 24)
def fetch_movie_meta(movie_name):
    """
    Fetch poster + basic metadata from TMDB.
    Returns dict: poster_url, year, rating(tmdb), overview, tmdb_id, error

    Supports BOTH v3 (?api_key=) and v4 (Bearer token) TMDB credentials.

    Two fixes applied here for popular movies missing posters:
      1. Letterboxd titles often look like "Movie Name (2013)" — the trailing
         year is stripped out of the query string and instead passed as TMDB's
         `year` filter, which greatly improves match accuracy for remakes/
         sequels/common titles.
      2. Instead of blindly taking the first search result, we prefer the
         first result that actually HAS a poster_path, since TMDB sometimes
         ranks a posterless placeholder/TV listing above the real movie.
    """
    result = {
        "poster_url": None, "year": None, "tmdb_rating": None,
        "overview": None, "tmdb_id": None, "error": None,
    }
    key, mode = get_tmdb_key()
    if not key:
        result["error"] = "no_key"
        return result

    # Split "Movie Name (2013)" -> title="Movie Name", year="2013"
    m = re.match(r"^(.*?)\s*\((\d{4})\)\s*$", movie_name.strip())
    query_title = m.group(1) if m else movie_name
    query_year = m.group(2) if m else None

    search_url = "https://api.themoviedb.org/3/search/movie"
    headers = {}
    params = {"query": query_title}
    if query_year:
        params["year"] = query_year

    if mode == "v4":
        headers["Authorization"] = f"Bearer {key}"
        headers["accept"] = "application/json"
    else:
        params["api_key"] = key

    try:
        resp = requests.get(search_url, params=params, headers=headers, timeout=8)
        if resp.status_code == 401:
            result["error"] = "unauthorized"
            return result
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []

        # Retry without the year filter if the strict search found nothing
        if not results and query_year:
            params.pop("year", None)
            resp = requests.get(search_url, params=params, headers=headers, timeout=8)
            resp.raise_for_status()
            results = resp.json().get("results") or []

        if not results:
            result["error"] = "not_found"
            return result

        # Prefer the first result that actually has a poster image
        best = next((r for r in results if r.get("poster_path")), results[0])

        poster_path = best.get("poster_path")
        if poster_path:
            result["poster_url"] = f"https://image.tmdb.org/t/p/w342{poster_path}"
        release_date = best.get("release_date") or ""
        result["year"] = release_date[:4] if release_date else None
        result["tmdb_rating"] = best.get("vote_average")
        result["overview"] = best.get("overview")
        result["tmdb_id"] = best.get("id")
        if not poster_path:
            result["error"] = "no_poster_on_record"
        return result
    except requests.exceptions.RequestException as e:
        result["error"] = f"request_error: {e}"
        return result


PLACEHOLDER = "https://placehold.co/300x450/1c2228/40bcf4?text=No+Poster"


def poster_or_placeholder(meta):
    return meta["poster_url"] if meta and meta.get("poster_url") else PLACEHOLDER


# =============================================================================
# LOAD DATA
# =============================================================================
top_fours_df, ratings_df = load_data()

st.title("🎬 DLS Stats — Letterboxd Group Dashboard")
st.markdown("Deep dive into your group's ratings, taste overlap, favorites and trends.")

if top_fours_df is None or ratings_df is None:
    st.error(
        "⚠️ CSV files not found! Please run your scraper script first to generate "
        "`letterboxd_top_fours.csv` and `letterboxd_all_ratings.csv`."
    )
    st.stop()

# TMDB key diagnostics banner (helps debug the "posters don't work" issue)
tmdb_key, tmdb_mode = get_tmdb_key()
with st.sidebar:
    st.header("⚙️ Settings")
    if not tmdb_key:
        st.error("No TMDB_API_KEY found in secrets — posters disabled.")
    else:
        st.success(f"TMDB key detected ({tmdb_mode.upper()} auth mode)")
        test = fetch_movie_meta("Inception")
        if test["error"] == "unauthorized":
            st.error(
                "TMDB rejected the key (401 Unauthorized).\n\n"
                "This usually means a v4 Read Access Token was pasted where a v3 "
                "API Key was expected, or vice versa. Double-check the key type "
                "on your TMDB account page under Settings → API."
            )
        elif test["error"] and test["error"].startswith("request_error"):
            st.warning(f"Network issue reaching TMDB: {test['error']}")
        else:
            st.caption("✅ Test lookup for 'Inception' succeeded.")
    st.divider()
    show_posters_everywhere = st.toggle("Show posters in tables", value=True)

# =============================================================================
# CORE DATA MODEL — LOGGED vs RATED
# =============================================================================
# Every row in letterboxd_all_ratings.csv is a LOG. Some logs carry a numeric
# star rating; others are the literal string "Unrated". Per project decision:
#   LOGGED = every row (the primary / more important count — includes Unrated)
#   RATED  = subset of logged rows where rating is a numeric value
# This distinction is applied globally, everywhere counts are shown.
ratings_df["rating"] = pd.to_numeric(ratings_df["rating"], errors="coerce")

logged_df = ratings_df.copy()                       # LOGGED — all rows
valid_ratings = ratings_df.dropna(subset=["rating"]).copy()  # RATED — numeric only

total_users = top_fours_df["username"].nunique()
total_logged = len(logged_df)
total_rated = len(valid_ratings)
unique_films_logged = logged_df["film_name"].nunique()
unique_films_rated = valid_ratings["film_name"].nunique()
avg_group_rating = valid_ratings["rating"].mean()

# Optional watch-date based stats if column exists
has_dates = "watched_date" in logged_df.columns or "date" in logged_df.columns
date_col = "watched_date" if "watched_date" in logged_df.columns else (
    "date" if "date" in logged_df.columns else None
)
if date_col:
    logged_df["_parsed_date"] = pd.to_datetime(logged_df[date_col], errors="coerce")
    has_dates = logged_df["_parsed_date"].notna().any()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("👥 Members", total_users)
col2.metric("📝 Total Logged", f"{total_logged:,}")
col3.metric("⭐ Total Rated", f"{total_rated:,}")
col4.metric("🎯 Group Avg Rating", f"{avg_group_rating:.2f} / 5")
col5.metric("🔥 Logs per Member", f"{total_logged / max(total_users, 1):.2f}")

st.divider()

# Pre-compute film-level stats (rating-based stats only ever come from RATED rows)
film_stats = (
    valid_ratings.groupby("film_name")
    .agg(
        Average_Rating=("rating", "mean"),
        Rating_Count=("rating", "count"),
        Std_Dev=("rating", "std"),
        Rated_By=("username", lambda x: ", ".join(sorted(x.unique()))),
    )
    .reset_index()
)
film_stats["Average_Rating"] = film_stats["Average_Rating"].round(2)
film_stats["Std_Dev"] = film_stats["Std_Dev"].fillna(0).round(2)

# Films-logged count per film (all logs, including Unrated)
film_logged_counts = (
    logged_df.groupby("film_name")
    .agg(Logged_Count=("username", "count"))
    .reset_index()
)

# All members list — used to make sure every user shows up in per-user tables,
# even members with zero logs or zero ratings (no filtering to "top N").
all_users_df = pd.DataFrame({"username": sorted(top_fours_df["username"].unique())})

# --- Per-user LOGGED stats (all users, unfiltered) ---
user_logged_stats = (
    logged_df.groupby("username")
    .agg(Films_Logged=("film_name", "count"))
    .reset_index()
)
user_logged_stats = all_users_df.merge(user_logged_stats, on="username", how="left")
user_logged_stats["Films_Logged"] = user_logged_stats["Films_Logged"].fillna(0).astype(int)
user_logged_stats = user_logged_stats.sort_values("Films_Logged", ascending=False).reset_index(drop=True)
user_logged_stats = user_logged_stats.rename(columns={"username": "Username"})

# --- Per-user RATED stats (all users, unfiltered) ---
user_rated_stats = (
    valid_ratings.groupby("username")
    .agg(Films_Rated=("film_name", "count"), Avg_Rating_Given=("rating", "mean"))
    .reset_index()
)
user_rated_stats = all_users_df.merge(user_rated_stats, on="username", how="left")
user_rated_stats["Films_Rated"] = user_rated_stats["Films_Rated"].fillna(0).astype(int)
user_rated_stats["Avg_Rating_Given"] = user_rated_stats["Avg_Rating_Given"].round(2)
user_rated_stats = user_rated_stats.sort_values("Films_Rated", ascending=False).reset_index(drop=True)
user_rated_stats = user_rated_stats.rename(columns={"username": "Username"})

# Kept for the "harsh vs generous" chart, which is inherently rating-specific
user_stats = user_rated_stats.rename(columns={"Films_Rated": "Films_Logged"}).copy()
user_stats["Avg_Rating_Given"] = user_stats["Avg_Rating_Given"].fillna(0)

# =============================================================================
# TABS
# =============================================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Overview",
    "🏆 Top Four Posters",
    "⭐ Leaderboards",
    "🎭 Taste & Controversy",
    "👤 Members",
    "🔍 Search",
])

# -----------------------------------------------------------------------
# TAB 1 — OVERVIEW
# -----------------------------------------------------------------------
with tab1:
    st.header("Group Rating Distribution & Activity")

    c1, c2 = st.columns(2)
    with c1:
        fig_hist = px.histogram(
            valid_ratings, x="rating", nbins=10,
            title="How Does the Group Rate Movies?",
            color_discrete_sequence=[ACCENT],
        )
        fig_hist.update_layout(**PLOTLY_LAYOUT, xaxis_title="Rating (out of 5)", yaxis_title="Number of Logs")
        fig_hist.update_xaxes(tickformat=".2f")
        add_bar_border(fig_hist)  # border around each column, as requested
        st.plotly_chart(fig_hist, use_container_width=True)

    with c2:
        user_activity = logged_df["username"].value_counts().reset_index()
        user_activity.columns = ["Username", "Films Logged"]
        fig_bar = px.bar(
            user_activity, x="Username", y="Films Logged",
            title="Most Active Members (All, by Films Logged)",
            color="Films Logged",
            color_continuous_scale=[ACCENT_2, ACCENT],
        )
        fig_bar.update_layout(**PLOTLY_LAYOUT)
        add_bar_border(fig_bar)
        st.plotly_chart(fig_bar, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        # Average rating given per user (who's harsh vs generous) — rating-based, so uses RATED data
        fig_avg = px.bar(
            user_stats.sort_values("Avg_Rating_Given"),
            x="Avg_Rating_Given", y="Username", orientation="h",
            title="Average Rating Given, Per Member (Harsh → Generous)",
            color="Avg_Rating_Given",
            color_continuous_scale=[ACCENT_3, ACCENT_2, ACCENT],
        )
        fig_avg.update_layout(**PLOTLY_LAYOUT, xaxis_title="Avg Rating", yaxis_title="")
        fig_avg.update_xaxes(tickformat=".2f")
        add_bar_border(fig_avg)
        st.plotly_chart(fig_avg, use_container_width=True)

    with c4:
        if has_dates:
            timeline = (
                logged_df.dropna(subset=["_parsed_date"])
                .assign(month=lambda d: d["_parsed_date"].dt.to_period("M").astype(str))
                .groupby("month").size().reset_index(name="Logs")
            )
            fig_time = px.line(
                timeline, x="month", y="Logs", markers=True,
                title="Logging Activity Over Time",
                color_discrete_sequence=[ACCENT],
            )
            fig_time.update_layout(**PLOTLY_LAYOUT, xaxis_title="Month", yaxis_title="Logs")
            st.plotly_chart(fig_time, use_container_width=True)
        else:
            # "How Many Films Are Shared?" stat removed per request.
            st.info("No watch-date data available to show a logging timeline.")

    st.divider()

    st.subheader("📋 All Members — Logged")
    st.caption("Every logged film, whether rated or not (Unrated logs included). All members shown, unfiltered.")
    st.dataframe(user_logged_stats, use_container_width=True, hide_index=True)

    st.subheader("📋 All Members — Rated")
    st.caption("Only films given a numeric star rating. All members shown, unfiltered.")
    st.dataframe(user_rated_stats, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------
# TAB 2 — TOP FOUR + POSTERS
# -----------------------------------------------------------------------
with tab2:
    st.header("Most Popular Films in Members' Top Four")
    top_cols = ["top_movie_1", "top_movie_2", "top_movie_3", "top_movie_4"]
    melted = top_fours_df.melt(id_vars=["username"], value_vars=top_cols, value_name="film_name")
    melted = melted.dropna(subset=["film_name"])
    melted = melted[melted["film_name"] != ""]

    if melted.empty:
        st.info("No Top Four records found.")
    else:
        top_counts = (
            melted.groupby("film_name")
            .agg(Selections=("username", "count"), Users=("username", lambda x: ", ".join(x)))
            .reset_index()
            .sort_values(by=["Selections", "film_name"], ascending=[False, True])
        )

        st.subheader("🖼️ Poster Wall — Top Picks")
        n_show = st.slider("Number of posters to display", 4, min(20, len(top_counts)), min(8, len(top_counts)))

        top_n = top_counts.head(n_show).reset_index(drop=True)
        n_cols = 4
        rows = int(np.ceil(len(top_n) / n_cols))
        idx = 0
        for r in range(rows):
            cols = st.columns(n_cols)
            for c in range(n_cols):
                if idx >= len(top_n):
                    break
                row = top_n.iloc[idx]
                meta = fetch_movie_meta(row["film_name"])
                with cols[c]:
                    st.markdown(f'<div class="poster-card"><span class="rank-badge">{idx+1}</span>', unsafe_allow_html=True)
                    st.image(poster_or_placeholder(meta), use_container_width=True)
                    year_str = f" ({meta['year']})" if meta.get("year") else ""
                    st.markdown(
                        f'<div class="poster-title">{row["film_name"]}{year_str}</div>'
                        f'<div class="poster-sub">🙋 {row["Selections"]} pick(s) · {row["Users"]}</div>',
                        unsafe_allow_html=True,
                    )
                    if meta.get("tmdb_rating"):
                        st.caption(f"TMDB: {meta['tmdb_rating']:.2f}/10")
                    if meta.get("error") == "unauthorized":
                        st.caption("⚠️ Poster fetch failed: invalid TMDB key")
                    elif meta.get("error") in ("not_found", "no_poster_on_record"):
                        st.caption("⚠️ No poster found on TMDB for this title")
                    st.markdown("</div>", unsafe_allow_html=True)
                idx += 1

        st.divider()
        st.subheader("📋 Full Top Four Table")
        st.dataframe(top_counts, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------
# TAB 3 — LEADERBOARDS
# -----------------------------------------------------------------------
with tab3:
    st.header("Group Rating Leaderboards")
    min_reviews = st.slider(
        "Minimum group reviews required for ranking:",
        1, max(2, total_users), min(2, total_users), key="lb_slider",
    )
    filtered = film_stats[film_stats["Rating_Count"] >= min_reviews]

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🔥 Highest Rated")
        highest = filtered.sort_values(by=["Average_Rating", "Rating_Count"], ascending=[False, False]).head(15)
        for _, row in highest.iterrows():
            meta = fetch_movie_meta(row["film_name"]) if show_posters_everywhere else None
            c_img, c_txt = st.columns([1, 4])
            if show_posters_everywhere:
                with c_img:
                    st.image(poster_or_placeholder(meta), width=60)
            with c_txt:
                st.markdown(f"**{row['film_name']}** — ⭐ {row['Average_Rating']:.2f} ({int(row['Rating_Count'])} ratings)")
                st.caption(f"Rated by: {row['Rated_By']}")

    with col_b:
        st.subheader("❄️ Lowest Rated")
        lowest = filtered.sort_values(by=["Average_Rating", "Rating_Count"], ascending=[True, False]).head(15)
        for _, row in lowest.iterrows():
            meta = fetch_movie_meta(row["film_name"]) if show_posters_everywhere else None
            c_img, c_txt = st.columns([1, 4])
            if show_posters_everywhere:
                with c_img:
                    st.image(poster_or_placeholder(meta), width=60)
            with c_txt:
                st.markdown(f"**{row['film_name']}** — ⭐ {row['Average_Rating']:.2f} ({int(row['Rating_Count'])} ratings)")
                st.caption(f"Rated by: {row['Rated_By']}")

# -----------------------------------------------------------------------
# TAB 4 — TASTE & CONTROVERSY
# -----------------------------------------------------------------------
with tab4:
    st.header("Taste Compatibility & Most Controversial Films")

    min_group_size = max(2, min(3, total_users))
    eligible = film_stats[film_stats["Rating_Count"] >= min_group_size].copy()

    c_div, c_agree = st.columns(2)

    with c_div:
        st.subheader("😤 Most Divisive Films (Highest Disagreement)")
        st.caption("Films with the biggest spread in ratings among people who watched them.")
        divisive = eligible.sort_values("Std_Dev", ascending=False).head(100)
        fig_div = px.bar(
            divisive, x="Std_Dev", y="film_name", orientation="h",
            title="Standard Deviation of Ratings (Higher = More Disagreement)",
            color="Std_Dev", color_continuous_scale=[ACCENT_2, ACCENT_3],
            height=2000,
        )
        fig_div.update_layout(**PLOTLY_LAYOUT, yaxis_title="", xaxis_title="Std Dev")
        fig_div.update_traces(hovertemplate="%{y}<br>Std Dev: %{x:.2f}<extra></extra>")
        fig_div.update_xaxes(tickformat=".2f")
        add_bar_border(fig_div)
        div_event = st.plotly_chart(
            fig_div, use_container_width=True,
            on_select="rerun", selection_mode="points", key="divisive_chart",
        )

    with c_agree:
        st.subheader("🤗 Most Agreed-On Films (Lowest Disagreement)")
        st.caption("Films the group is most in sync on — smallest spread in ratings.")
        consensus = eligible.sort_values("Std_Dev", ascending=True).head(100)
        fig_con = px.bar(
            consensus, x="Std_Dev", y="film_name", orientation="h",
            title="Standard Deviation of Ratings (Lower = More Agreement)",
            color="Std_Dev", color_continuous_scale=[ACCENT, ACCENT_2],
            height=2000,
        )
        fig_con.update_layout(**PLOTLY_LAYOUT, yaxis_title="", xaxis_title="Std Dev")
        fig_con.update_traces(hovertemplate="%{y}<br>Std Dev: %{x:.2f}<extra></extra>")
        fig_con.update_xaxes(tickformat=".2f")
        add_bar_border(fig_con)
        con_event = st.plotly_chart(
            fig_con, use_container_width=True,
            on_select="rerun", selection_mode="points", key="consensus_chart",
        )

    # ---- Selected-movie rating breakdown (from interactive click) ----
    selected_film = None
    for event, df_src in [(div_event, divisive), (con_event, consensus)]:
        if event and event.get("selection", {}).get("points"):
            point_index = event["selection"]["points"][0].get("point_index")
            if point_index is not None and point_index < len(df_src):
                selected_film = df_src.iloc[point_index]["film_name"]
                break

    if selected_film:
        st.subheader(f"🎯 Individual Ratings for: {selected_film}")
        film_ratings = (
            valid_ratings[valid_ratings["film_name"] == selected_film]
            [["username", "rating"]]
            .sort_values("rating", ascending=False)
            .reset_index(drop=True)
        )
        film_ratings["rating"] = film_ratings["rating"].round(2)
        c_chart, c_table = st.columns([2, 1])
        with c_chart:
            fig_person = px.bar(
                film_ratings, x="username", y="rating",
                title=f"Per-Member Rating — {selected_film}",
                color="rating", color_continuous_scale=[ACCENT_3, ACCENT_2, ACCENT],
                range_y=[0, 5],
            )
            fig_person.update_layout(**PLOTLY_LAYOUT, xaxis_title="", yaxis_title="Rating")
            fig_person.update_traces(hovertemplate="%{x}<br>Rating: %{y:.2f}<extra></extra>")
            fig_person.update_yaxes(tickformat=".2f")
            add_bar_border(fig_person)
            st.plotly_chart(fig_person, use_container_width=True)
        with c_table:
            st.dataframe(film_ratings.rename(columns={"username": "Username", "rating": "Rating"}),
                         use_container_width=True, hide_index=True, height=800)

    # ---- Fixed Tables: Complete Rating Breakdown for Divisive & Agreed-On Films ----
    st.divider()
    st.subheader("📋 Rating Breakdown for Divisive & Agreed-On Films")
    
    col_div_tbl, col_con_tbl = st.columns(2)
    with col_div_tbl:
        st.markdown("**Divisive Films — Member Ratings**")
        divisive_ratings = (
            valid_ratings[valid_ratings["film_name"].isin(divisive["film_name"])]
            .groupby("film_name")
            .agg(Ratings=("username", lambda u: ", ".join(f"{usr}: {r:.1f}⭐" for usr, r in zip(u, valid_ratings.loc[u.index, "rating"]))))
            .reset_index()
        )
        divisive_merged = divisive.merge(divisive_ratings, on="film_name", how="left")
        st.dataframe(
            divisive_merged[["film_name", "Std_Dev", "Ratings"]].rename(columns={"film_name": "Film", "Std_Dev": "Spread (StdDev)"}),
            use_container_width=True, hide_index=True, height=800
        )

    with col_con_tbl:
        st.markdown("**Agreed-On Films — Member Ratings**")
        consensus_ratings = (
            valid_ratings[valid_ratings["film_name"].isin(consensus["film_name"])]
            .groupby("film_name")
            .agg(Ratings=("username", lambda u: ", ".join(f"{usr}: {r:.1f}⭐" for usr, r in zip(u, valid_ratings.loc[u.index, "rating"]))))
            .reset_index()
        )
        consensus_merged = consensus.merge(consensus_ratings, on="film_name", how="left")
        st.dataframe(
            consensus_merged[["film_name", "Std_Dev", "Ratings"]].rename(columns={"film_name": "Film", "Std_Dev": "Spread (StdDev)"}),
            use_container_width=True, hide_index=True, height=800
        )

    # ---- Member Taste Similarity ----
    st.divider()
    st.subheader("🤝 Member Taste Similarity")
    st.caption("Correlation between members' ratings on films they've both watched.")
    
    pivot = valid_ratings.pivot_table(index="film_name", columns="username", values="rating", aggfunc="mean")
    if pivot.shape[1] >= 2:
        corr = pivot.corr(min_periods=2).round(2)

        # Correlation Heatmap
        fig_heat = px.imshow(
            corr, text_auto=".2f", aspect="auto",
            color_continuous_scale=[ACCENT_3, BG, ACCENT],
            zmin=-1, zmax=1,
            title="Rating Correlation Heatmap",
        )
        fig_heat.update_layout(**PLOTLY_LAYOUT)
        st.plotly_chart(fig_heat, use_container_width=True)

        # Build Sorted Pairwise Table
        pairs = []
        members = corr.columns.tolist()
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                m1, m2 = members[i], members[j]
                val = corr.loc[m1, m2]
                if pd.notna(val):
                    # Count shared films
                    shared = pivot[[m1, m2]].dropna().shape[0]
                    pairs.append({"Member 1": m1, "Member 2": m2, "Similarity": val, "Shared Films": shared})

        pairs_df = pd.DataFrame(pairs).sort_values("Similarity", ascending=False).reset_index(drop=True)

        st.subheader("📊 All Member Pairings (Sorted by Similarity)")
        
        # User Filter Option
        all_members = ["All Members"] + sorted(top_fours_df["username"].unique().tolist())
        selected_filter_user = st.selectbox("Filter pairs by member:", all_members)

        if selected_filter_user != "All Members":
            filtered_pairs = pairs_df[
                (pairs_df["Member 1"] == selected_filter_user) | (pairs_df["Member 2"] == selected_filter_user)
            ]
        else:
            filtered_pairs = pairs_df

        st.dataframe(filtered_pairs, use_container_width=True, hide_index=True)

    else:
        st.info("Need at least 2 members with overlapping ratings to compute similarity.")
        
# -----------------------------------------------------------------------
# TAB 5 — MEMBERS
# -----------------------------------------------------------------------
with tab5:
    st.header("Member Profiles")
    selected_user = st.selectbox("Choose a member", sorted(top_fours_df["username"].unique()))

    user_logged = logged_df[logged_df["username"] == selected_user]
    user_rated = valid_ratings[valid_ratings["username"] == selected_user]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Films Logged", len(user_logged))
    m2.metric("Films Rated", len(user_rated))
    m3.metric("Avg Rating Given", f"{user_rated['rating'].mean():.2f}" if len(user_rated) else "—")
    rank_list = list(user_logged_stats["Username"])
    m4.metric("Activity Rank (Logged)", f"#{rank_list.index(selected_user) + 1}" if selected_user in rank_list else "—")

    st.subheader("🏅 Their Top Four")
    tf_row = top_fours_df[top_fours_df["username"] == selected_user]
    if not tf_row.empty:
        picks = [tf_row.iloc[0].get(c) for c in ["top_movie_1", "top_movie_2", "top_movie_3", "top_movie_4"]]
        picks = [p for p in picks if pd.notna(p) and p != ""]
        cols = st.columns(len(picks)) if picks else []
        for i, movie in enumerate(picks):
            meta = fetch_movie_meta(movie)
            with cols[i]:
                st.image(poster_or_placeholder(meta), use_container_width=True)
                st.caption(movie)

    st.subheader("📈 Their Rating Distribution")
    if len(user_rated):
        fig_u = px.histogram(
            user_rated, x="rating", nbins=10,
            color_discrete_sequence=[ACCENT_2],
            title=f"{selected_user}'s Rating Habits",
        )
        fig_u.update_layout(**PLOTLY_LAYOUT)
        fig_u.update_xaxes(tickformat=".2f")
        add_bar_border(fig_u)
        st.plotly_chart(fig_u, use_container_width=True)

    st.subheader("🎞️ All Their Logged Films")
    st.caption("Includes Unrated logs.")
    display_logged = user_logged[["film_name", "rating"]].copy()
    display_logged["rating"] = display_logged["rating"].round(2)
    display_logged = display_logged.rename(columns={"film_name": "Film", "rating": "Rating"})
    display_logged["Rating"] = display_logged["Rating"].apply(lambda x: x if pd.notna(x) else "Unrated")
    st.dataframe(
        display_logged.sort_values("Rating", ascending=False, key=lambda s: pd.to_numeric(s, errors="coerce")),
        use_container_width=True, hide_index=True,
    )

# -----------------------------------------------------------------------
# TAB 6 — SEARCH
# -----------------------------------------------------------------------
with tab6:
    st.header("Search Any Film or Member")
    search_query = st.text_input("🔍 Type a film title or username:")

    search_df = film_stats.merge(film_logged_counts, on="film_name", how="left")
    search_df["Logged_Count"] = search_df["Logged_Count"].fillna(0).astype(int)
    search_df["Average_Rating"] = search_df["Average_Rating"].round(2)
    search_df["Std_Dev"] = search_df["Std_Dev"].round(2)

    if search_query:
        search_df = search_df[
            search_df["film_name"].str.contains(search_query, case=False, na=False)
            | search_df["Rated_By"].str.contains(search_query, case=False, na=False)
        ]

    col_table, col_poster = st.columns([3, 1])
    with col_table:
        st.dataframe(
            search_df.sort_values(by="Average_Rating", ascending=False),
            use_container_width=True, hide_index=True,
        )
    with col_poster:
        if search_query and len(search_df) > 0:
            top_match = search_df.iloc[0]["film_name"]
            meta = fetch_movie_meta(top_match)
            st.markdown(f"**{top_match}**")
            st.image(poster_or_placeholder(meta), use_container_width=True)
            if meta.get("overview"):
                st.caption(meta["overview"][:280] + ("…" if len(meta["overview"]) > 280 else ""))
            if meta.get("error") == "unauthorized":
                st.error("TMDB key rejected (401). Check key type in sidebar diagnostics.")
            elif meta.get("error") in ("not_found", "no_poster_on_record"):
                st.warning("No poster found on TMDB for this title.")
        elif search_query:
            st.warning("No matches found.")