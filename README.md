# Second Brain — Chat UI

A local chat interface for your Obsidian RAG pipeline, styled after claude.ai's web interface.

## How it fits with your existing code

- `secondbrain.py` and `test_search.py` are your original files, unchanged.
- `app.py` imports `hybrid_search()` directly from `test_search.py` — retrieval logic is not duplicated anywhere.
- On each user message, `app.py`:
  1. Calls `hybrid_search(user_message, top_k=TOP_K)` (from `test_search.py`) to retrieve chunks from `note_chunks` in Postgres.
  2. Builds a context block from the returned `(file_path, header_context, content, rrf_score)` rows.
  3. Sends that context + the question to a local Ollama chat model (`CHAT_MODEL`, default `llama3.1`) and streams the answer back to the browser via Server-Sent Events.
  4. The UI shows the streamed answer plus a collapsible "N sources from your notes" panel listing each chunk's file, section, snippet, and RRF score.

## Setup

```bash
cd secondbrain_app
pip install -r requirements.txt
```

Make sure, as with your existing scripts:
- Postgres is running and `DATABASE_URL` is set (or the default `postgresql://postgres:admin@localhost:5432/second_brain` is correct).
- Ollama is running locally (`ollama serve`) with `nomic-embed-text` pulled (for embeddings, used by `test_search.py`) and a chat model pulled — default is `llama3.1`:
  ```bash
  ollama pull nomic-embed-text
  ollama pull llama3.1
  ```
- You've already run `secondbrain.py` at least once to populate `note_chunks`.

## Run

```bash
python app.py
```

Open `http://127.0.0.1:5000`.

## Configuration (env vars)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:admin@localhost:5432/second_brain` | Same as your existing scripts |
| `CHAT_MODEL` | `llama3.1` | Ollama model used to generate answers |
| `RAG_TOP_K` | `5` | Number of chunks retrieved per question |

## Files

```
app.py              Flask backend, /api/chat streaming endpoint
secondbrain.py       (unchanged) vault → Postgres sync
test_search.py        (unchanged) hybrid_search() — imported by app.py
templates/index.html   Chat page markup
static/style.css        claude.ai-styled visual design
static/chat.js            SSE streaming client, message rendering, chat history
```

## Notes

- Chat history is in-memory per browser tab (resets on page reload) — there's no chat-persistence table in your schema, so nothing is written to Postgres by this app beyond what `secondbrain.py` already does.
- If `hybrid_search()` or Ollama generation fails (e.g. Postgres/Ollama not running), the UI shows an inline error banner rather than crashing.


<img src="second_brain_pipeline_flow.svg" alt="Second Brain" width="1000" height="1000" />
