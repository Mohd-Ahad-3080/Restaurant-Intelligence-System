"""What-if app (Streamlit), two tabs, on your own computer only (nothing is sent anywhere):

- Predict: describe a restaurant -> High / Medium / Low popularity with probabilities (saved model; the same
  code path as scripts/predict.py).
- Recommend: city, cuisine, budget, minimum rating, delivery -> ranked list with the score breakdown (the same
  engine as scripts/recommend.py).

Run from the project folder, with .venv active (Windows and macOS alike):
    streamlit run scripts/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import config  # noqa: E402
from src.recommender import WEIGHTS, Request, recommend  # noqa: E402
from src.scoring import known_cuisines, load_model, new_restaurant_raw, predict_raw, reference_raw  # noqa: E402
from src.target import EXCLUDED_FEATURES_NOTE, TARGET_DEFINITION  # noqa: E402

DEFAULT_CITY = "New Delhi"
NCR_CITIES = {"New Delhi", "Gurgaon", "Noida", "Faridabad", "Ghaziabad"}   # same list as src/model.py
CLASS_ORDER = ["Low", "Medium", "High"]


def probability_chart(probs: pd.DataFrame, dark: bool = True):
    """Bars in class order Low, Medium, High, values as percentages with a clearly readable % label above each
    bar: white on the dark theme, near-black on the light theme (dark text was almost invisible on dark)."""
    import altair as alt
    base = alt.Chart(probs).encode(
        x=alt.X("Class:N", sort=CLASS_ORDER, title=None, axis=alt.Axis(labelAngle=0, labelFontSize=13)),
        y=alt.Y("Probability:Q", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1.08]), title="Probability"))
    bars = base.mark_bar(color="#CB202D")
    labels = base.mark_text(dy=-10, fontSize=15, fontWeight="bold", color="#FFFFFF" if dark else "#18181B") \
        .encode(text=alt.Text("Probability:Q", format=".1%"))
    return (bars + labels).properties(height=280)


def _dark_theme() -> bool:
    try:
        return st.context.theme.type != "light"     # Streamlit reports the theme the viewer is using
    except Exception:  # noqa: BLE001 - older Streamlit or no browser context: assume the default dark theme
        return True


@st.cache_data
def clean_data() -> pd.DataFrame:
    return pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv", encoding="utf-8")


def predict_tab() -> None:
    ref = reference_raw()
    cities = sorted(ref["City"].dropna().unique())
    city = st.selectbox("City", cities, index=cities.index(DEFAULT_CITY), key="p_city")
    locs = sorted(ref.loc[ref["City"] == city, "Locality"].dropna().unique())
    locality = st.selectbox("Locality (optional)", [""] + locs, key="p_locality")
    cuisines = st.multiselect("Cuisines", sorted(known_cuisines().values()), default=["North Indian"], key="p_cuisines")
    price = st.select_slider("Price range (1 = budget, 4 = luxury)", options=[1, 2, 3, 4], value=2, key="p_price")
    currency = ref.loc[ref["City"] == city, "Currency"].mode().iloc[0]
    cost = st.number_input(f"Cost for two ({currency})", min_value=1, value=600, step=50, format="%d", key="p_cost")
    delivery = st.checkbox("Online delivery", value=True, key="p_delivery")
    booking = st.checkbox("Table booking", value=False, key="p_booking")
    if st.button("Predict", type="primary", key="p_go"):
        try:
            row, notes = new_restaurant_raw(city=city, cuisines=cuisines, price_range=price, cost_for_two=cost,
                                            online_delivery=delivery, table_booking=booking,
                                            locality=locality or None)
            r = predict_raw(row).iloc[0]
        except (ValueError, FileNotFoundError) as e:
            st.error(str(e))
            return
        st.subheader(f"Predicted popularity: {r.predicted_class}")
        probs = pd.DataFrame({"Class": ["Low", "Medium", "High"],
                              "Probability": [r.prob_low, r.prob_medium, r.prob_high]})
        st.altair_chart(probability_chart(probs, dark=_dark_theme()), use_container_width=True)
        if r.country == "India" and r.city not in NCR_CITIES:
            st.info("Outside Delhi NCR, Zomato listed mostly well-known restaurants in these cities, so predictions "
                    "there lean towards High.")
        for n in notes:
            st.caption(n)
    _, meta = load_model()
    st.caption(f"Model: {meta['best_model']}, test accuracy {meta['test_metrics']['test_accuracy']:.1%} "
               f"(random guessing about 33%). {TARGET_DEFINITION} {EXCLUDED_FEATURES_NOTE}")


def recommend_tab() -> None:
    clean = clean_data()
    cities = sorted(clean["city"].dropna().unique())
    city = st.selectbox("City", cities, index=cities.index(DEFAULT_CITY), key="r_city")
    in_city = clean[clean["city"] == city]
    names = sorted({c.strip() for s in in_city["cuisines"].dropna() for c in s.split(",") if c.strip()})
    cuisines = st.multiselect("Cuisine(s) (empty = any)", names,
                              default=["North Indian"] if "North Indian" in names else [], key="r_cuisines")
    currency = in_city["currency"].mode().iloc[0]
    budget = st.number_input(f"Budget for two ({currency}; 0 = no limit)", min_value=0, value=800, step=50,
                             format="%d", key="r_budget")
    min_rating = st.slider("Minimum rating", 0.0, 5.0, 3.5, 0.1, key="r_min_rating")
    delivery = st.checkbox("Online delivery required", value=True, key="r_delivery")
    if st.button("Recommend", type="primary", key="r_go"):
        req = Request(city=city, cuisines=cuisines, budget=budget or None, min_rating=min_rating,
                      delivery="required" if delivery else "any", top_n=10)
        try:
            out = recommend(clean, req)
        except ValueError as e:
            st.error(str(e))
            return
        if out.empty:
            st.warning("No restaurants match these filters.")
            return
        show = out[["rank", "restaurant_name", "locality", "aggregate_rating", "votes", "avg_cost_for_two",
                    "rating_points", "popularity_points", "budget_points", "cuisine_points", "total_score"]]
        st.dataframe(show.rename(columns={
            "rank": "#", "restaurant_name": "Restaurant", "locality": "Locality", "aggregate_rating": "Rating",
            "votes": "Votes", "avg_cost_for_two": f"Cost for two ({currency})", "rating_points": "Rating pts",
            "popularity_points": "Popularity pts", "budget_points": "Budget pts", "cuisine_points": "Cuisine pts",
            "total_score": "SCORE"}), hide_index=True)
    st.caption("SCORE = " + " + ".join(f"{w:.2f} x {k}" for k, w in WEIGHTS.items())
               + " (each part 0-1; the 'pts' columns add up to SCORE).")


st.set_page_config(page_title="Restaurant Intelligence", layout="wide")
st.title("Restaurant Intelligence: what-if")
tab_predict, tab_recommend = st.tabs(["Predict", "Recommend"])
with tab_predict:
    predict_tab()
with tab_recommend:
    recommend_tab()
