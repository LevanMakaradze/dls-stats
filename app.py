import pandas as pd
import streamlit as st
import plotly.express as px
import requests

# -------------------------------------------------------------------------
# Page Configuration & Styling
# -------------------------------------------------------------------------
st.set_page_config(
    page_title="dls stats", 
    page_icon="🎬", 
    layout="wide"
)

# Modern UI Styling
st.markdown("""
    <style>
    .main { background-color: #14181c; color: #9ab; }
    h1, h2, h3 { color: #00e054 !important; font-family: sans-serif; }
    .stMetric { background-color: #2c3440; padding: 15px; border-radius: 8px; border: 1px solid #456; }
    div[data-testid="stImage"] img { border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.5); }
    </style>
""", unsafe_allow_html=True)


# -------------------------------------------------------------------------
# Data Loading & API Functions
# -------------------------------------------------------------------------
@st.cache_data
def load_data():
    try:
        top_fours = pd.read_csv("letterboxd_top_fours.csv")
        ratings = pd.read_csv("letterboxd_all_ratings.csv")
        return top_fours, ratings
    except FileNotFoundError:
        return None, None

@st.cache_data(show_spinner=False)
def fetch_poster(movie_name):
    """Fetches movie poster URL from TMDB."""
    # To make this work, add TMDB_API_KEY to your Streamlit Secrets!
    api_key = st.secrets.get("TMDB_API_KEY", None)
    
    if not api_key:
        return "https://via.placeholder.com/200x300.png?text=No+API+Key"
        
    search_url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={movie_name}"
    try:
        response = requests.get(search_url).json()
        if response.get('results'):
            poster_path = response['results'][0].get('poster_path')
            if poster_path:
                return f"https://image.tmdb.org/t/p/w300{poster_path}"
    except Exception as e:
        pass
    
    return "https://via.placeholder.com/200x300.png?text=Poster+Not+Found"

top_fours_df, ratings_df = load_data()

# -------------------------------------------------------------------------
# App Header & Metrics
# -------------------------------------------------------------------------
st.title("🎬 Letterboxd Group Analytics Dashboard")
st.markdown("Comprehensive insights, ratings, and visual trends across your group.")

if top_fours_df is None or ratings_df is None:
    st.error(
        "⚠️ CSV files not found! Please run your scraper script first to generate"
        " `letterboxd_top_fours.csv` and `letterboxd_all_ratings.csv`."
    )
else:
    # Compute Core Metrics
    total_users = top_fours_df["username"].nunique()
    ratings_df["rating"] = pd.to_numeric(ratings_df["rating"], errors="coerce")
    valid_ratings = ratings_df.dropna(subset=["rating"])
    total_logs = len(valid_ratings)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Members Analyzed", total_users)
    col2.metric("Total Ratings Logged", total_logs)
    col3.metric("Unique Films in Database", valid_ratings["film_name"].nunique())

    st.divider()

    # Pre-calculate main stats dataframe for reuse
    film_stats = (
        valid_ratings.groupby("film_name")
        .agg(
            Average_Rating=("rating", "mean"),
            Rating_Count=("rating", "count"),
            Rated_By=("username", lambda x: ", ".join(x.unique())),
        )
        .reset_index()
    )

    # -------------------------------------------------------------------------
    # Layout Tabs
    # -------------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Visual Analytics",
        "🏆 Top Consensus & Posters",
        "⭐ Leaderboards",
        "🔍 Master Search",
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Visual Analytics (NEW)
    # -------------------------------------------------------------------------
    with tab1:
        st.header("Group Rating Distribution")
        
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            # Distribution of all ratings given by the group
            fig_hist = px.histogram(
                valid_ratings, 
                x="rating", 
                nbins=10,
                title="How Does the Group Rate Movies?",
                color_discrete_sequence=['#00e054'],
                template="plotly_dark"
            )
            fig_hist.update_layout(xaxis_title="Rating (Out of 5)", yaxis_title="Number of Logs")
            st.plotly_chart(fig_hist, use_container_width=True)
            
        with col_chart2:
            # Most active users
            user_activity = valid_ratings['username'].value_counts().reset_index()
            user_activity.columns = ['Username', 'Movies Logged']
            fig_bar = px.bar(
                user_activity.head(10), 
                x='Username', 
                y='Movies Logged',
                title="Most Active Members",
                color_discrete_sequence=['#40bcf4'],
                template="plotly_dark"
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    # -------------------------------------------------------------------------
    # TAB 2: Top Four Analysis & Posters (UPDATED)
    # -------------------------------------------------------------------------
    with tab2:
        st.header("Most Popular Films in Members' Top Four")
        top_cols = ["top_movie_1", "top_movie_2", "top_movie_3", "top_movie_4"]
        melted = top_fours_df.melt(
            id_vars=["username"], value_vars=top_cols, value_name="film_name"
        )
        melted = melted.dropna(subset=["film_name"])
        melted = melted[melted["film_name"] != ""]

        if not melted.empty:
            top_counts = (
                melted.groupby("film_name")
                .agg(
                    Selections=("username", "count"),
                    Users=("username", lambda x: ", ".join(x)),
                )
                .reset_index()
            )
            top_counts = top_counts.sort_values(
                by=["Selections", "film_name"], ascending=[False, True]
            )

            st.dataframe(top_counts, use_container_width=True, hide_index=True)
            
            st.subheader("Top 4 Heavyweights (Posters)")
            # Display posters for the top 4 most selected movies
            top_4_movies = top_counts.head(4)["film_name"].tolist()
            poster_cols = st.columns(4)
            for idx, movie in enumerate(top_4_movies):
                with poster_cols[idx]:
                    poster_url = fetch_poster(movie)
                    st.image(poster_url, caption=movie, use_container_width=True)
        else:
            st.info("No Top Four records found.")

    # -------------------------------------------------------------------------
    # TAB 3: Ratings Leaderboards
    # -------------------------------------------------------------------------
    with tab3:
        st.header("Group Average Ratings Leaderboard")
        min_reviews = st.slider(
            "Minimum group reviews required for ranking:",
            1, max(2, total_users), min(2, total_users),
        )
        filtered = film_stats[film_stats["Rating_Count"] >= min_reviews]

        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("🔥 Highest Rated")
            highest = filtered.sort_values(
                by=["Average_Rating", "Rating_Count"], ascending=[False, False]
            )
            st.dataframe(
                highest[["film_name", "Average_Rating", "Rating_Count", "Rated_By"]],
                use_container_width=True, hide_index=True,
            )

        with col_b:
            st.subheader("❄️ Lowest Rated")
            lowest = filtered.sort_values(
                by=["Average_Rating", "Rating_Count"], ascending=[True, False]
            )
            st.dataframe(
                lowest[["film_name", "Average_Rating", "Rating_Count", "Rated_By"]],
                use_container_width=True, hide_index=True,
            )

    # -------------------------------------------------------------------------
    # TAB 4: Searchable Master List & Live Poster
    # -------------------------------------------------------------------------
    with tab4:
        st.header("Complete Filterable Master List")
        search_query = st.text_input("🔍 Search for any film or user in the database:")

        search_df = film_stats.copy()
        if search_query:
            search_df = search_df[
                search_df["film_name"].str.contains(search_query, case=False, na=False) | 
                search_df["Rated_By"].str.contains(search_query, case=False, na=False)
            ]

        col_table, col_poster = st.columns([3, 1])
        
        with col_table:
            st.dataframe(
                search_df.sort_values(by="Average_Rating", ascending=False),
                use_container_width=True,
                hide_index=True,
            )
            
        with col_poster:
            if search_query and len(search_df) > 0:
                # Show poster of the first match in the search results
                top_match = search_df.iloc[0]["film_name"]
                st.write(f"**{top_match}**")
                poster_url = fetch_poster(top_match)
                st.image(poster_url, use_container_width=True)
            elif search_query:
                st.warning("No matches found.")