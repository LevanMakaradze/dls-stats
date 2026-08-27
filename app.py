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
    Supports BOTH v3 (?api_key=) and v4 (Bearer token) TMDB credentials,
    which is the most common reason posters silently fail to load.
    """
    result = {
        "poster_url": None, "year": None, "tmdb_rating": None,
        "overview": None, "tmdb_id": None, "error": None,
    }
    key, mode = get_tmdb_key()
    if not key:
        result["error"] = "no_key"
        return result

    search_url = "https://api.themoviedb.org/3/search/movie"
    headers = {}
    params = {"query": movie_name}

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
        if not results:
            result["error"] = "not_found"
            return result

        best = results[0]
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
# CORE METRICS
# =============================================================================
total_users = top_fours_df["username"].nunique()
ratings_df["rating"] = pd.to_numeric(ratings_df["rating"], errors="coerce")
valid_ratings = ratings_df.dropna(subset=["rating"]).copy()
total_logs = len(valid_ratings)
unique_films = valid_ratings["film_name"].nunique()
avg_group_rating = valid_ratings["rating"].mean()

# Optional watch-date based stats if column exists
has_dates = "watched_date" in valid_ratings.columns or "date" in valid_ratings.columns
date_col = "watched_date" if "watched_date" in valid_ratings.columns else (
    "date" if "date" in valid_ratings.columns else None
)
if date_col:
    valid_ratings["_parsed_date"] = pd.to_datetime(valid_ratings[date_col], errors="coerce")
    has_dates = valid_ratings["_parsed_date"].notna().any()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("👥 Members", total_users)
col2.metric("📝 Total Ratings", f"{total_logs:,}")
col3.metric("🎞️ Unique Films", f"{unique_films:,}")
col4.metric("⭐ Group Avg Rating", f"{avg_group_rating:.2f} / 5")
col5.metric("🔥 Logs per Member", f"{total_logs / max(total_users,1):.1f}")

st.divider()

# Pre-compute film-level stats
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
film_stats["Std_Dev"] = film_stats["Std_Dev"].fillna(0).round(2)

# Per-user stats
user_stats = (
    valid_ratings.groupby("username")
    .agg(
        Films_Logged=("film_name", "count"),
        Avg_Rating_Given=("rating", "mean"),
        Harshness=("rating", "mean"),
    )
    .reset_index()
    .sort_values("Films_Logged", ascending=False)
)

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
        st.plotly_chart(fig_hist, use_container_width=True)

    with c2:
        user_activity = valid_ratings["username"].value_counts().reset_index()
        user_activity.columns = ["Username", "Movies Logged"]
        fig_bar = px.bar(
            user_activity.head(15), x="Username", y="Movies Logged",
            title="Most Active Members",
            color="Movies Logged",
            color_continuous_scale=[ACCENT_2, ACCENT],
        )
        fig_bar.update_layout(**PLOTLY_LAYOUT)
        st.plotly_chart(fig_bar, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        # Average rating given per user (who's harsh vs generous)
        fig_avg = px.bar(
            user_stats.sort_values("Avg_Rating_Given"),
            x="Avg_Rating_Given", y="username", orientation="h",
            title="Average Rating Given, Per Member (Harsh → Generous)",
            color="Avg_Rating_Given",
            color_continuous_scale=[ACCENT_3, ACCENT_2, ACCENT],
        )
        fig_avg.update_layout(**PLOTLY_LAYOUT, xaxis_title="Avg Rating", yaxis_title="")
        st.plotly_chart(fig_avg, use_container_width=True)

    with c4:
        if has_dates:
            timeline = (
                valid_ratings.dropna(subset=["_parsed_date"])
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
            # Fallback: rating count distribution per film (popularity curve)
            pop_curve = film_stats["Rating_Count"].value_counts().sort_index().reset_index()
            pop_curve.columns = ["Times Rated By N People", "Number of Films"]
            fig_pop = px.bar(
                pop_curve, x="Times Rated By N People", y="Number of Films",
                title="Consensus Spread: How Many Films Are Shared?",
                color_discrete_sequence=[ACCENT_2],
            )
            fig_pop.update_layout(**PLOTLY_LAYOUT)
            st.plotly_chart(fig_pop, use_container_width=True)

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
                        st.caption(f"TMDB: {meta['tmdb_rating']:.1f}/10")
                    if meta.get("error") == "unauthorized":
                        st.caption("⚠️ Poster fetch failed: invalid TMDB key")
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
    eligible["Std_Dev"] = eligible["Std_Dev"].round(2)
    eligible["Average_Rating"] = eligible["Average_Rating"].round(2)

    c_div, c_agree = st.columns(2)

    with c_div:
        st.subheader("😤 Most Divisive Films (Highest Disagreement)")
        st.caption("Films with the biggest spread in ratings among people who watched them.")
        divisive = eligible.sort_values("Std_Dev", ascending=False).head(10)
        fig_div = px.bar(
            divisive, x="Std_Dev", y="film_name", orientation="h",
            title="Standard Deviation of Ratings (Higher = More Disagreement)",
            color="Std_Dev", color_continuous_scale=[ACCENT_2, ACCENT_3],
        )
        fig_div.update_layout(**PLOTLY_LAYOUT, yaxis_title="", xaxis_title="Std Dev")
        fig_div.update_traces(hovertemplate="%{y}<br>Std Dev: %{x:.2f}<extra></extra>")
        fig_div.update_xaxes(tickformat=".2f")
        div_event = st.plotly_chart(
            fig_div, use_container_width=True,
            on_select="rerun", selection_mode="points", key="divisive_chart",
        )

    with c_agree:
        st.subheader("🤗 Most Agreed-On Films (Lowest Disagreement)")
        st.caption("Films the group is most in sync on — smallest spread in ratings.")
        consensus = eligible.sort_values("Std_Dev", ascending=True).head(10)
        fig_con = px.bar(
            consensus, x="Std_Dev", y="film_name", orientation="h",
            title="Standard Deviation of Ratings (Lower = More Agreement)",
            color="Std_Dev", color_continuous_scale=[ACCENT, ACCENT_2],
        )
        fig_con.update_layout(**PLOTLY_LAYOUT, yaxis_title="", xaxis_title="Std Dev")
        fig_con.update_traces(hovertemplate="%{y}<br>Std Dev: %{x:.2f}<extra></extra>")
        fig_con.update_xaxes(tickformat=".2f")
        con_event = st.plotly_chart(
            fig_con, use_container_width=True,
            on_select="rerun", selection_mode="points", key="consensus_chart",
        )

    # ---- Selected-movie rating breakdown (from either chart) ----
    selected_film = None
    for event, df_src in [(div_event, divisive), (con_event, consensus)]:
        if event and event.get("selection", {}).get("points"):
            point_index = event["selection"]["points"][0].get("point_index")
            if point_index is not None and point_index < len(df_src):
                selected_film = df_src.iloc[point_index]["film_name"]
                break

    st.divider()
    if selected_film:
        st.subheader(f"🎯 Ratings for: {selected_film}")
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
            st.plotly_chart(fig_person, use_container_width=True)
        with c_table:
            st.dataframe(film_ratings, use_container_width=True, hide_index=True)
    else:
        st.caption("👆 Click a bar in either chart above to see how each member rated that film.")

    st.divider()
    st.subheader("🤝 Member Taste Similarity")
    st.caption("Correlation between members' ratings on films they've both watched (needs overlapping films).")
    pivot = valid_ratings.pivot_table(index="film_name", columns="username", values="rating", aggfunc="mean")
    if pivot.shape[1] >= 2:
        corr = pivot.corr(min_periods=2).round(2)
        fig_heat = px.imshow(
            corr, text_auto=".2f", aspect="auto",
            color_continuous_scale=[ACCENT_3, BG, ACCENT],
            zmin=-1, zmax=1,
            title="Rating Correlation Between Members",
        )
        fig_heat.update_layout(**PLOTLY_LAYOUT)
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info("Need at least 2 members with overlapping ratings to compute similarity.")
        
# -----------------------------------------------------------------------
# TAB 5 — MEMBERS
# -----------------------------------------------------------------------
with tab5:
    st.header("Member Profiles")
    selected_user = st.selectbox("Choose a member", sorted(top_fours_df["username"].unique()))

    user_ratings = valid_ratings[valid_ratings["username"] == selected_user]
    u_row = user_stats[user_stats["username"] == selected_user].iloc[0] if not user_stats[user_stats["username"] == selected_user].empty else None

    m1, m2, m3 = st.columns(3)
    m1.metric("Films Logged", len(user_ratings))
    m2.metric("Avg Rating Given", f"{user_ratings['rating'].mean():.2f}" if len(user_ratings) else "—")
    rank = (user_stats["username"] == selected_user).idxmax() + 1 if not user_stats.empty else "—"
    m3.metric("Activity Rank", f"#{list(user_stats['username']).index(selected_user)+1 if selected_user in list(user_stats['username']) else '—'}")

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
    if len(user_ratings):
        fig_u = px.histogram(
            user_ratings, x="rating", nbins=10,
            color_discrete_sequence=[ACCENT_2],
            title=f"{selected_user}'s Rating Habits",
        )
        fig_u.update_layout(**PLOTLY_LAYOUT)
        st.plotly_chart(fig_u, use_container_width=True)

    st.subheader("🎞️ All Their Logged Films")
    st.dataframe(
        user_ratings[["film_name", "rating"]].sort_values("rating", ascending=False),
        use_container_width=True, hide_index=True,
    )

# -----------------------------------------------------------------------
# TAB 6 — SEARCH
# -----------------------------------------------------------------------
with tab6:
    st.header("Search Any Film or Member")
    search_query = st.text_input("🔍 Type a film title or username:")

    search_df = film_stats.copy()
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
        elif search_query:
            st.warning("No matches found.")