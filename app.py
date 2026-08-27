import pandas as pd
import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="Letterboxd Group Analytics", page_icon="🎬", layout="wide"
)

# Custom Clean Styling
st.markdown("""
    <style>
    .main { background-color: #14181c; color: #9ab; }
    h1, h2, h3 { color: #00e054 !important; font-family: sans-serif; }
    .stMetric { background-color: #2c3440; padding: 15px; border-radius: 8px; border: 1px solid #456; }
    </style>
""", unsafe_allow_html=True)


# Load Data Caching
@st.cache_data
def load_data():
  try:
    top_fours = pd.read_csv("letterboxd_top_fours.csv")
    ratings = pd.read_csv("letterboxd_all_ratings.csv")
    return top_fours, ratings
  except FileNotFoundError:
    return None, None


top_fours_df, ratings_df = load_data()

# App Header
st.title("🎬 Letterboxd Group Analytics Dashboard")
st.markdown("Comprehensive insights, ratings, and trends across your group.")

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

  # Layout Tabs for Clean Organization
  tab1, tab2, tab3, tab4 = st.tabs([
      "🏆 Top Four Consensus",
      "⭐ Group Ratings Leaderboard",
      "👥 Most Watched by Group",
      "🔍 Complete Master Dataset",
  ])

  # -------------------------------------------------------------------------
  # TAB 1: Top Four Analysis
  # -------------------------------------------------------------------------
  with tab1:
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

      # Full interactive table instead of truncated list
      st.dataframe(top_counts, use_container_width=True, hide_index=True)
    else:
      st.info("No Top Four records found.")

  # -------------------------------------------------------------------------
  # TAB 2: Ratings Leaderboard (Highest & Lowest Average)
  # -------------------------------------------------------------------------
  with tab2:
    st.header("Group Average Ratings Leaderboard")

    film_stats = (
        valid_ratings.groupby("film_name")
        .agg(
            Average_Rating=("rating", "mean"),
            Rating_Count=("rating", "count"),
            Rated_By=("username", lambda x: ", ".join(x.unique())),
        )
        .reset_index()
    )

    # Filter selector for minimum reviews to avoid single-person bias
    min_reviews = st.slider(
        "Minimum group reviews required for ranking:",
        1,
        max(2, total_users),
        min(2, total_users),
    )
    filtered = film_stats[film_stats["Rating_Count"] >= min_reviews]

    col_a, col_b = st.columns(2)

    with col_a:
      st.subheader("🔥 Highest Rated")
      highest = filtered.sort_values(
          by=["Average_Rating", "Rating_Count"], ascending=[False, False]
      )
      st.dataframe(
          highest[["film_name", "Average_Rating", "Rating_Count"]],
          use_container_width=True,
          hide_index=True,
      )

    with col_b:
      st.subheader("❄️ Lowest Rated")
      lowest = filtered.sort_values(
          by=["Average_Rating", "Rating_Count"], ascending=[True, False]
      )
      st.dataframe(
          lowest[["film_name", "Average_Rating", "Rating_Count"]],
          use_container_width=True,
          hide_index=True,
      )

  # -------------------------------------------------------------------------
  # TAB 3: Most Watched / Group Consensus
  # -------------------------------------------------------------------------
  with tab3:
    st.header("Most Watched Films Across the Group")
    most_watched = film_stats.sort_values(
        by=["Rating_Count", "Average_Rating"], ascending=[False, False]
    )
    st.dataframe(
        most_watched[
            ["film_name", "Rating_Count", "Average_Rating", "Rated_By"]
        ],
        use_container_width=True,
        hide_index=True,
    )

  # -------------------------------------------------------------------------
  # TAB 4: Complete Searchable Master List
  # -------------------------------------------------------------------------
  with tab4:
    st.header("Complete Filterable Master List")
    search_query = st.text_input(
        "🔍 Search for any film or user in the database:"
    )

    search_df = film_stats.copy()
    if search_query:
      search_df = search_df[
          search_df["film_name"]
          .str.contains(search_query, case=False, na=False)
          | search_df["Rated_By"]
          .str.contains(search_query, case=False, na=False)
      ]

    st.dataframe(
        search_df.sort_values(by="Average_Rating", ascending=False),
        use_container_width=True,
        hide_index=True,
    )