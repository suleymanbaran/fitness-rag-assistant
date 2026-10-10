"""Chat interface for the coach. Talks to the FastAPI backend over HTTP, like any other client.

Run (with the API already running): streamlit run ui/streamlit_app.py
"""

import os
from datetime import date
from statistics import mean

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
CATEGORIES = ["all", "recovery", "training", "sleep", "nutrition", "safety"]
GOALS = ["strength", "muscle_gain", "fat_loss", "endurance", "general_fitness"]
EXAMPLES = [
    "My HRV dropped and my CNS feels fried. How should I adjust today's heavy leg day?",
    "I'm losing energy in my workouts lately. Why, and what should I change?",
    "How much protein should I eat per day?",
]

st.set_page_config(page_title="AI Fitness Coach", layout="wide")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


# The token is part of every cache key, so one browser session never sees another's cached data.
@st.cache_data(ttl=60)
def fetch_users(token: str) -> list[dict]:
    response = httpx.get(f"{API_URL}/users", headers=auth_headers(token), timeout=10)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=60)
def fetch_user(user_id: str, token: str) -> dict:
    response = httpx.get(f"{API_URL}/users/{user_id}", headers=auth_headers(token), timeout=10)
    response.raise_for_status()
    return response.json()


def ask_coach(user_id: str, question: str, category: str) -> dict:
    payload = {"user_id": user_id, "question": question}
    if category != "all":
        payload["category"] = category
    response = httpx.post(f"{API_URL}/ask", json=payload, headers=auth_headers(token()), timeout=60)
    response.raise_for_status()
    return response.json()


def token() -> str:
    return st.session_state.get("token", "")


def sign_in_form(failed: bool) -> None:
    st.title("AI Fitness Coach")
    if failed:
        st.error("That token was not accepted.")
    with st.form("sign_in"):
        entered = st.text_input("Access token", type="password", help="Issued with: python -m scripts.issue_token")
        if st.form_submit_button("Sign in"):
            st.session_state["token"] = entered.strip()
            st.rerun()


def error_detail(response: httpx.Response) -> str:
    detail = response.json().get("detail")
    if isinstance(detail, list):  # FastAPI validation errors
        return "; ".join(f"{'.'.join(map(str, e['loc'][1:]))}: {e['msg']}" for e in detail)
    return str(detail)


def save(path: str, payload: dict, success: str) -> None:
    """PUT to the API; on success refresh cached data and rerun so the page shows the new state."""
    response = httpx.put(f"{API_URL}{path}", json=payload, headers=auth_headers(token()), timeout=10)
    if response.is_error:
        st.error(f"Not saved ({response.status_code}): {error_detail(response)}")
        return
    fetch_users.clear()
    fetch_user.clear()
    st.session_state["flash"] = success
    st.rerun()


def profile_form(existing: dict | None) -> None:
    key = existing["user_id"] if existing else "new"
    with st.form(f"profile_{key}"):
        user_id = existing["user_id"] if existing else st.text_input("User ID", help="Lowercase letters, digits, - or _")
        name = st.text_input("Name", value=existing["name"] if existing else "")
        age = st.number_input("Age", min_value=10, max_value=110, value=existing["age"] if existing else None)
        weight = st.number_input(
            "Weight (kg)", min_value=20.0, max_value=400.0, step=0.5, value=existing["weight_kg"] if existing else None
        )
        goal = st.selectbox(
            "Goal",
            GOALS,
            index=GOALS.index(existing["goal"]) if existing and existing["goal"] in GOALS else 0,
            format_func=lambda g: g.replace("_", " "),
        )
        if st.form_submit_button("Save profile"):
            if not user_id.strip():
                st.error("Choose a user ID.")
                return
            payload = {"name": name, "age": age, "weight_kg": weight, "goal": goal}
            save(f"/users/{user_id.strip()}", payload, f"Profile {name} saved")


def log_day_form(user_id: str) -> None:
    with st.form(f"log_day_{user_id}", clear_on_submit=True):
        day = st.date_input("Date", value=date.today(), max_value=date.today())
        hrv = st.number_input("HRV (ms)", min_value=1.0, max_value=399.0, step=1.0, value=None)
        sleep = st.number_input("Sleep score (0-100)", min_value=0, max_value=100, value=None)
        rhr = st.number_input("Resting HR (bpm)", min_value=20, max_value=250, value=None)
        kcal = st.number_input("Calories (kcal)", min_value=0, max_value=20000, step=50, value=None)
        st.caption("Leave a field empty to keep its stored value.")
        if st.form_submit_button("Save day"):
            metrics = {"hrv_ms": hrv, "sleep_score": sleep, "resting_hr_bpm": rhr, "calories_kcal": kcal}
            payload = {k: v for k, v in metrics.items() if v is not None}
            if not payload:
                st.error("Enter at least one metric.")
            else:
                save(f"/users/{user_id}/days/{day}", payload, f"Metrics for {day} saved")


def render_sources(sources: list[dict]) -> None:
    if not sources:
        return
    with st.expander(f"Sources used ({len(sources)})"):
        for s in sources:
            st.markdown(f"- `{s['protocol_id']}` **{s['title']}** ({s['category']}), similarity {s['score']:.3f}")


def metric_vs_baseline(label: str, days: list[dict], key: str, unit: str, delta_color: str) -> None:
    """delta_color: "normal" (up is good), "inverse" (up is bad) or "off" (neutral)."""
    values = [d[key] for d in days if d.get(key) is not None]
    if not values:
        st.metric(label, "n/a")
        return
    today, baseline = values[-1], mean(values[:-1]) if len(values) > 1 else values[-1]
    st.metric(
        label,
        f"{today:g}{unit}",
        delta=f"{today - baseline:+.1f} vs baseline",
        delta_color=delta_color,
    )


try:
    users = fetch_users(token())
except httpx.HTTPStatusError as exc:
    if exc.response.status_code != 401:
        st.error(f"The API returned {exc.response.status_code}: {error_detail(exc.response)}")
        st.stop()
    sign_in_form(failed=bool(token()))
    st.stop()
except httpx.HTTPError:
    st.error(f"Cannot reach the API at {API_URL}. Start it first with: `uvicorn app.main:app --reload`")
    st.stop()

if flash := st.session_state.pop("flash", None):
    st.toast(flash)

with st.sidebar:
    st.header("Settings")
    labels = {u["user_id"]: f"{u['name']} ({u['goal'].replace('_', ' ')})" for u in users}
    user_id = st.selectbox("User", list(labels), format_func=labels.get)
    category = st.selectbox("Search protocols in", CATEGORIES)
    if user_id and st.button("Clear chat"):
        st.session_state.pop(f"messages_{user_id}", None)

if user_id is None:
    st.title("AI Fitness Coach")
    st.info("No profiles yet. Create yours to start.")
    profile_form(None)
    st.stop()

profile = fetch_user(user_id, token())
days = sorted(profile["days"], key=lambda d: d["date"])
logged_today = bool(days) and days[-1]["date"] == date.today().isoformat()

with st.sidebar:
    with st.expander("Log a day", expanded=not logged_today):
        log_day_form(user_id)
    with st.expander("Edit profile"):
        profile_form(profile)
    if not token():
        # With auth on, profiles are created by scripts.issue_token, not from the UI.
        with st.expander("New profile"):
            profile_form(None)
    elif st.button("Sign out"):
        st.session_state.clear()
        st.rerun()
    st.caption(f"API: {API_URL}")

st.title("AI Fitness Coach")
facts = [profile["name"]]
if profile["age"] is not None:
    facts.append(f"{profile['age']} years")
if profile["weight_kg"] is not None:
    facts.append(f"{profile['weight_kg']:g} kg")
st.caption(", ".join(facts) + (f". Latest metrics: {days[-1]['date']}." if days else "."))

if not days:
    st.info("No metrics yet. Log today's numbers in the sidebar so the coach can compare them with your baseline.")
else:
    if not logged_today:
        st.warning(f"Nothing logged for today yet. The coach will use your latest day ({days[-1]['date']}).")
    cols = st.columns(4)
    with cols[0]:
        metric_vs_baseline("HRV", days, "hrv_ms", " ms", delta_color="normal")
    with cols[1]:
        metric_vs_baseline("Sleep score", days, "sleep_score", "/100", delta_color="normal")
    with cols[2]:
        metric_vs_baseline("Resting HR", days, "resting_hr_bpm", " bpm", delta_color="inverse")
    with cols[3]:
        metric_vs_baseline("Calories", days, "calories_kcal", " kcal", delta_color="off")

    chart = pd.DataFrame(days).set_index("date")
    left, right = st.columns(2)
    left.line_chart(chart[["hrv_ms", "resting_hr_bpm"]], height=220)
    right.bar_chart(chart[["sleep_score"]], height=220)

st.divider()
messages = st.session_state.setdefault(f"messages_{user_id}", [])

for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        render_sources(message.get("sources", []))

pending = st.session_state.pop("pending_question", None)
if not messages and pending is None:
    st.caption("Try an example:")
    for col, example in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        if col.button(example, width="stretch"):
            # Rerun so the example buttons disappear before the conversation starts.
            st.session_state["pending_question"] = example
            st.rerun()
question = st.chat_input("Ask your coach...") or pending

if question:
    messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Retrieving protocols and thinking..."):
                result = ask_coach(user_id, question, category)
            answer, sources = result["answer"], result["sources"]
        except httpx.HTTPStatusError as exc:
            answer, sources = f"The API returned {exc.response.status_code}: {exc.response.json().get('detail')}", []
        except httpx.HTTPError as exc:
            answer, sources = f"Could not reach the API: {exc}", []
        st.markdown(answer)
        render_sources(sources)

    messages.append({"role": "assistant", "content": answer, "sources": sources})
