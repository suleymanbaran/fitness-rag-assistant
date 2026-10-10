# Fitness RAG Coach

An AI fitness coach that turns your daily HRV, sleep and resting heart rate into concrete training
advice, grounded in vetted recovery and nutrition protocols and citing every source it uses.

**Stack:** Python, FastAPI, PostgreSQL (SQLAlchemy, Alembic), Qdrant, OpenAI (`text-embedding-3-small`,
`gpt-4o-mini`), Streamlit, Docker, Caddy.

<!-- Add a screenshot of the chat answering a question: docs/screenshot.png
![Chat UI](docs/screenshot.png) -->

## What it does

- **Personal context:** compares today's metrics with your rolling 7-day baseline, computed in SQL
  with window functions, and puts the exact numbers in the prompt.
- **Grounded answers:** retrieves the most relevant protocols from a vector database and instructs
  the model to answer only from them, cite them by ID, and flag medical red flags.
- **Wearable and nutrition sync:** connects Fitbit data through the Google Health API (OAuth 2.0) and
  the FatSecret food diary (OAuth 1.0), with encrypted tokens, automatic refresh, retries and idempotent upserts.
- **Measured retrieval:** a labeled question set scores search with hit rate, recall and MRR at k.
- **Production basics:** per-user token auth with object-level access checks, rate limiting on the
  LLM endpoint, upstream timeouts, request IDs in logs (no health data), Docker deployment behind HTTPS.
- **Runs offline:** demo mode and the test suite need no API key.

## How it works

```mermaid
flowchart LR
  fitbit[Fitbit] --> google["Google Health API"]
  diary[FatSecret food diary] --> fatsecret[FatSecret API]
  google -->|"HRV, resting HR, sleep"| postgres
  fatsecret -->|calories| postgres
  question[Question] --> embed[Embed]
  embed --> qdrant["Qdrant: top-k protocols"]
  userId[user_id] --> postgres["Postgres: daily metrics, 7-day baselines"]
  qdrant --> prompt[Prompt]
  postgres --> prompt
  prompt --> llm[gpt-4o-mini]
  llm --> answer["Answer + cited sources"]
```

## Design decisions

- **Two stores for two kinds of data.** Protocols are unstructured text, searched by meaning in Qdrant.
  Biometrics are exact numbers, queried in Postgres. Similarity search would blur the numbers.
- **RAG instead of fine-tuning.** Metrics change daily and advice must trace back to a source.
  Updating knowledge means re-embedding a document, not retraining a model.
- **Idempotent daily upserts.** One row per user per day with a unique constraint, so re-logging or a
  sync updates the day instead of duplicating it, and only overwrites the fields that were sent.
  Google and FatSecret can therefore fill the same day without erasing each other.
- **Evaluation before tuning.** Chunking and top-k stay unchanged until the eval says retrieval is weak.

## Results

Retrieval on 26 labeled questions over 12 protocols (`python -m scripts.eval_retrieval`):

| Embeddings | Hit rate @1 | Hit rate @3 | Recall @3 | MRR |
|---|---|---|---|---|
| OpenAI `text-embedding-3-small` | 0.88 | 1.00 | 0.99 | 0.94 |
| Word-hashing baseline (offline) | 0.38 | 0.81 | 0.78 | 0.57 |

Semantic embeddings find the right protocol for questions that share no keywords with it
(for example "almost passed out at rest" retrieves the medical red-flags protocol).
The knowledge base is small, so these numbers show the method works; they will drop as protocols grow.

## Project layout

| Path | Role |
|---|---|
| `data/protocols.json` | Unstructured knowledge, searched by meaning (vector DB) |
| `data/users.json` | Two demo users, loaded into Postgres by `scripts/seed.py` |
| `app/db/models.py` | SQLAlchemy tables: `users`, `daily_biometrics` (one row per user per day) |
| `app/data_access/users.py` | Profile lookup with rolling 7-day baselines computed in SQL |
| `app/data_access/biometrics.py` | Idempotent per-day upsert of metrics |
| `app/rag/embeddings.py` | Text to vectors (OpenAI embeddings) |
| `app/rag/vector_store.py` | Qdrant collection: recreate, upsert, filtered search |
| `app/rag/prompt.py` | System rules, computed baselines, retrieved protocols |
| `app/rag/generator.py` | Chat completion call |
| `app/rag/demo.py` | Offline stand-ins for OpenAI (demo mode and tests) |
| `app/main.py` | FastAPI app: `POST /ask`, `/users` endpoints |
| `app/integrations/` | Google Health and FatSecret clients, OAuth flows, token encryption, sync |
| `ui/streamlit_app.py` | Chat UI with metrics and charts; calls the API over HTTP |
| `migrations/` | Alembic schema migrations |
| `scripts/ingest.py` | Embed protocols and load them into Qdrant |
| `scripts/cosine_playground.py` | Brute-force cosine search in NumPy |

## Run locally

One-time setup:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                # set OPENAI_API_KEY (or DEMO_MODE=true)
docker compose up -d                # Postgres on :5432, Qdrant on :6333
alembic upgrade head                # create the tables
python -m scripts.seed              # optional: the two demo users
python -m scripts.ingest            # embed protocols into Qdrant (needs the OpenAI key)
```

Every time, in two terminals:

```bash
uvicorn app.main:app --reload       # terminal 1: the API, docs at http://127.0.0.1:8000/docs
streamlit run ui/streamlit_app.py   # terminal 2: the chat UI at http://localhost:8501
```

```bash
curl -X POST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"user_id": "u1", "question": "My HRV dropped and my CNS feels fried. How should I adjust leg day?"}'
```

### Demo mode (no OpenAI key)

`DEMO_MODE=true uvicorn app.main:app --reload` skips `scripts.ingest`: protocols are embedded at
startup with a word-hashing stand-in, and the answer shows the prompt that would be sent to GPT.
Postgres still has to be running. Nothing is sent to OpenAI.

## Make it yours

In the UI sidebar, open **New profile** to create yourself. Then either connect Fitbit and FatSecret
(next section) or type a day under **Log a day** (HRV, sleep score, time asleep, resting HR, calories;
any subset). Re-logging a day only overwrites the fields you fill in.
The coach compares your latest day with the previous 7 days, and the UI warns when today is not logged yet.

The same over HTTP:

```bash
curl -X PUT localhost:8000/users/me -H 'Content-Type: application/json' \
  -d '{"name": "Suleyman", "age": 30, "weight_kg": 78.5, "goal": "strength"}'
curl -X PUT localhost:8000/users/me/days/2026-10-10 -H 'Content-Type: application/json' \
  -d '{"hrv_ms": 58, "sleep_score": 71, "resting_hr_bpm": 56}'
```

## Connect your data (Google Health API and FatSecret)

Fitbit does not have its own API anymore. Its data is read through the
[Google Health API](https://developers.google.com/health), the successor of the Fitbit Web API.
Calories come from the [FatSecret Platform API](https://platform.fatsecret.com).
Typing a day still works, and a later sync only overwrites the fields that provider owns.

| | Google Health API | FatSecret Platform API |
|---|---|---|
| What we read | `daily-heart-rate-variability` (RMSSD, ms), `daily-resting-heart-rate` (bpm), `sleep` (`minutesAsleep` of the main sleep) | `food_entries.get.v2`: the day's diary entries, summed to kcal |
| Where it lands | `hrv_ms`, `resting_hr_bpm`, `sleep_minutes` | `calories_kcal` |
| Login | Google OAuth 2.0, read-only scopes, refresh token | 3-legged OAuth 1.0 (HMAC-SHA1). FatSecret's OAuth 2.0 cannot act for a user |
| Endpoint | `GET https://health.googleapis.com/v4/users/me/dataTypes/{type}/dataPoints` | `GET https://platform.fatsecret.com/rest/food-entries/v2` |
| Code | `app/integrations/google_health.py` | `app/integrations/fatsecret.py` |

Google has no Fitbit sleep *score*, so synced sleep is stored as hours asleep. A day with a nap and a
night's sleep keeps the session Google marks as the main sleep. A FatSecret day with no diary entries
is skipped, so "not logged" is never stored as 0 kcal.

Both logins are Fernet-encrypted in `integration_accounts` and never written to logs. Google access
tokens last about an hour and are refreshed automatically; if Google or FatSecret rejects the stored
login, sync reports it and the UI asks you to connect again.

**1. Encryption key.** Run `python -m scripts.generate_key` and put the output in `.env` as
`TOKEN_ENCRYPTION_KEY`. Losing this key means reconnecting both providers.

**2. Google Health.** In the [Google Cloud console](https://console.cloud.google.com), following
Google's [get started guide](https://developers.google.com/health):

1. Create a project and enable the **Google Health API** (APIs & Services, Library).
2. OAuth consent screen: user type External, app in Testing. Add the Google account your Fitbit is
   linked to as a test user. Add these scopes:
   - `https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
   - `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
3. Create an OAuth client of type **Web application**. Authorized redirect URI:
   `http://localhost:8000/integrations/google/callback`
   (in production: `https://<your-domain>/integrations/google/callback`).
4. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

While the app stays in Testing, Google expires the refresh token after 7 days, so Connect has to be
pressed again weekly until the app is verified.

**3. FatSecret.** Register an app at [platform.fatsecret.com](https://platform.fatsecret.com) and copy
the OAuth 1.0 **Consumer Key** and **Consumer Secret** into `.env` as `FATSECRET_CONSUMER_KEY` and
`FATSECRET_CONSUMER_SECRET`. Two limits from FatSecret's side:

- The app may only accept calls from IP addresses you allowlist.
- `food_entries.get` is marked Premier-only. On a free key, sync returns FatSecret's error instead of
  calories; HRV, heart rate and sleep from Google still sync.

The connect flow is FatSecret's [3-legged OAuth](https://platform.fatsecret.com/docs/guides/authentication/oauth1/three-legged):
request token, you approve on fatsecret.com, then the callback at
`/integrations/fatsecret/callback` exchanges it for a token that does not expire.

**4. Sync.** Restart the API so it reads the new `.env`. In the sidebar open **Connected apps**,
press Connect, approve access, then **Sync now** (last 14 days). Repeat syncs are safe.

```bash
python -m scripts.sync --user-id me --days 14     # same thing from the terminal
```

The production stack runs `scripts.sync` every 3 hours. `POST /users/{id}/sync?days=14` does one sync
over HTTP and returns, per provider, how many days changed or why it failed.

## Check retrieval quality

`data/eval_questions.json` lists questions with the protocol IDs they should retrieve.

```bash
python -m scripts.eval_retrieval            # OpenAI embeddings (needs the key)
python -m scripts.eval_retrieval --demo     # offline hashing embedder, for comparison
```

It prints hit rate, recall and MRR at k = 1, 3, 5, plus every question missed at `RAG_TOP_K`.
Run it before and after changing protocols, chunking, top-k or the embedding model; change those
only when the score says retrieval is weak. Current scores are in [Results](#results).

## Going live (only when you need it off this machine)

`docker-compose.prod.yml` runs Postgres, Qdrant, the API and the UI on a private network, with
[Caddy](https://caddyserver.com) in front serving the UI over HTTPS. Only ports 80/443 are exposed.
Each deploy runs `alembic upgrade head` and `scripts.ingest` before the API starts.

On a server with Docker and a domain whose DNS points at it:

```bash
cp .env.prod.example .env.prod      # set DOMAIN, POSTGRES_PASSWORD, OPENAI_API_KEY
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api \
  python -m scripts.issue_token me --name "Suleyman"     # prints your access token once
```

Open `https://<DOMAIN>` and sign in with the token. In production:

- Register `https://<DOMAIN>/integrations/google/callback` as the Google redirect URI, and put the
  same provider credentials plus `TOKEN_ENCRYPTION_KEY` in `.env.prod`. Caddy forwards only the
  `/integrations/*/callback` paths to the API; a `sync` service pulls the last 3 days every 3 hours.
- `AUTH_ENABLED=true`: every `/users` and `/ask` call needs `Authorization: Bearer <token>` and can
  only read or change the token owner's data (401 without a valid token, 403 for someone else's).
- `/ask` is limited to `ASK_RATE_LIMIT_PER_MINUTE` per user (429 with `Retry-After`).
- OpenAI calls time out after `OPENAI_TIMEOUT_SECONDS`; failures return 502 instead of crashing.
- Request logs hold method, path, status, duration and a request ID, never bodies or metric values.
- `scripts.seed` refuses to load demo users while `AUTH_ENABLED=true`.

You can turn auth on locally too (`AUTH_ENABLED=true` in `.env`); the UI then asks for a token.

## Test

```bash
docker compose up -d
python -m pytest -q
```

Tests use a separate `fitness_coach_test` database (created automatically, every test rolled back),
an in-memory Qdrant, and fake embedder, generator and provider APIs, so they need no API key and
never call Google, FatSecret or OpenAI.
