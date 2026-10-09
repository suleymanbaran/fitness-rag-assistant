"""Chat interface for the coach. Talks to the FastAPI backend over HTTP, like any other client.

Run (with the API already running): streamlit run ui/streamlit_app.py
"""

import os
from statistics import mean

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
CATEGORIES = ["all", "recovery", "training", "sleep", "nutrition", "safety"]
EXAMPLES = [
    "My HRV dropped and my CNS feels fried. How should I adjust today's heavy leg day?",
    "I'm losing energy in my workouts lately. Why, and what should I change?",
    "How much protein should I eat per day?",
]

st.set_page_config(page_title="AI Fitness Coach", layout="wide")


@st.cache_data(ttl=60)
def fetch_users() -> list[dict]:
    response = httpx.get(f"{API_URL}/users", timeout=10)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=60)
def fetch_user(user_id: str) -> dict:
    response = httpx.get(f"{API_URL}/users/{user_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def ask_coach(user_id: str, question: str, category: str) -> dict:
    payload = {"user_id": user_id, "question": question}
    if category != "all":
        payload["category"] = category
    response = httpx.post(f"{API_URL}/ask", json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


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
    users = fetch_users()
except httpx.HTTPError:
    st.error(f"Cannot reach the API at {API_URL}. Start it first with: `uvicorn app.main:app --reload`")
    st.stop()

with st.sidebar:
    st.header("Settings")
    labels = {u["user_id"]: f"{u['name']} ({u['goal'].replace('_', ' ')})" for u in users}
    user_id = st.selectbox("User", list(labels), format_func=labels.get)
    category = st.selectbox("Search protocols in", CATEGORIES)
    if st.button("Clear chat"):
        st.session_state.pop(f"messages_{user_id}", None)
    st.caption(f"API: {API_URL}")

profile = fetch_user(user_id)
days = sorted(profile["days"], key=lambda d: d["date"])

st.title("AI Fitness Coach")
st.caption(f"{profile['name']}, {profile['age']} years, {profile['weight_kg']:g} kg. Today is {days[-1]['date']}.")

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
