"""Streamlit what-if app (scripts/app.py), run headless with Streamlit's own test runner.

The app must give exactly the same answers as the command-line tools (same engines)."""
import pandas as pd
import pytest

from src import config

APP = str(config.ROOT / "scripts" / "app.py")


@pytest.fixture
def app():
    if not (config.MODELS_DIR / "popularity_model.joblib").exists():
        pytest.skip("Run `python run_pipeline.py` first")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception
    return at


def test_app_loads_with_two_tabs(app):
    assert [t.label for t in app.tabs] == ["Predict", "Recommend"]


def test_predict_tab_matches_predict_script(app):
    from src.scoring import new_restaurant_raw, predict_raw
    app.button(key="p_go").click().run()
    assert not app.exception
    row, _ = new_restaurant_raw(city="New Delhi", cuisines=["North Indian"], price_range=2, cost_for_two=600.0,
                                online_delivery=True, table_booking=False)
    expected = predict_raw(row).iloc[0]["predicted_class"]
    assert app.subheader[0].value == f"Predicted popularity: {expected}"


def test_recommend_tab_matches_engine(app):
    from src.recommender import Request, recommend
    app.button(key="r_go").click().run()
    assert not app.exception
    clean = pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv", encoding="utf-8")
    exp = recommend(clean, Request(city="New Delhi", cuisines=["North Indian"], budget=800.0, min_rating=3.5,
                                   delivery="required", top_n=10))
    shown = app.dataframe[0].value
    assert list(shown["Restaurant"]) == list(exp["restaurant_name"])
    assert shown["SCORE"].tolist() == pytest.approx(exp["total_score"].tolist())


def test_recommend_tab_reports_no_match(app):
    """Minimum rating 5.0 with delivery required: the engine finds nothing, the app says so (no empty table)."""
    from src.recommender import Request, recommend
    clean = pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv", encoding="utf-8")
    assert recommend(clean, Request(city="New Delhi", cuisines=["North Indian"], budget=800.0, min_rating=5.0,
                                    delivery="required")).empty
    app.slider(key="r_min_rating").set_value(5.0)
    app.button(key="r_go").click().run()
    assert not app.exception
    assert "No restaurants match" in app.warning[0].value and not app.dataframe


def test_probability_chart_order_and_percent_labels():
    src = open(APP, encoding="utf-8").read()
    assert 'CLASS_ORDER = ["Low", "Medium", "High"]' in src
    ns = {"__file__": APP}
    exec(src.split("\ndef predict_tab")[0], ns)          # helpers only (no Streamlit page code)
    spec_ = ns["probability_chart"](pd.DataFrame({"Class": ["Low", "Medium", "High"],
                                                  "Probability": [0.2, 0.3, 0.5]})).to_dict()
    x = spec_["layer"][0]["encoding"]["x"]
    assert x["sort"] == ["Low", "Medium", "High"]
    assert spec_["layer"][0]["encoding"]["y"]["axis"]["format"] == "%"
    assert spec_["layer"][1]["encoding"]["text"]["format"] == ".1%"


@pytest.mark.parametrize("city,note", [("Agra", True), ("New Delhi", False), ("London", False)])
def test_note_only_for_indian_cities_outside_ncr(app, city, note):
    """Outside Delhi NCR (India) predictions lean towards High (sampling); not shown for NCR or other countries."""
    app.selectbox(key="p_city").set_value(city).run()
    cuisine = "North Indian" if city != "London" else "British"
    app.multiselect(key="p_cuisines").set_value([cuisine]).run()
    app.button(key="p_go").click().run()
    assert not app.exception and not app.error
    assert bool([i for i in app.info if "lean towards High" in i.value]) is note


def test_money_inputs_are_whole_numbers(app):
    for key in ("p_cost", "r_budget"):
        w = app.number_input(key=key)
        assert isinstance(w.value, int)


def test_probability_labels_readable_on_both_themes():
    """% labels: white above the bars on the dark theme (dark text was almost invisible), near-black on light."""
    src = open(APP, encoding="utf-8").read()
    ns = {"__file__": APP}
    exec(src.split("\ndef predict_tab")[0], ns)
    probs = pd.DataFrame({"Class": ["Low", "Medium", "High"], "Probability": [0.05, 0.35, 0.60]})
    dark = ns["probability_chart"](probs, dark=True).to_dict()["layer"][1]["mark"]
    light = ns["probability_chart"](probs, dark=False).to_dict()["layer"][1]["mark"]
    assert dark["color"] == "#FFFFFF" and light["color"] == "#18181B"
    assert dark["fontSize"] >= 14 and dark["fontWeight"] == "bold" and dark["dy"] < 0   # above the bar
