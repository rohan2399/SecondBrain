# SecondBrain
SecondBrain : An Extension to Markdownwala

This is a nice local-first "second brain" pipeline: it takes your Obsidian markdown notes, chunks them, embeds them locally with Ollama, stores everything in PostgreSQL (with pgvector), and then lets you search across your notes using a hybrid of semantic + keyword search. Let me break down both files and show you the flow.

What each file does

## secondbrain.py — the ingestion/sync pipeline

Resolves folder paths (input docs, Obsidian vault, attachments) relative to the script's own location, creating them if missing.
Walks the Obsidian vault directory tree (skipping hidden folders like .obsidian).
For each .md file: computes a SHA-256 hash and skips it if unchanged since last sync (cheap incremental sync).
If changed, deletes old chunks for that file, parses YAML frontmatter, and splits the body into chunks by markdown headers (#, ##, ###).
For each chunk, builds an embedding string (File: ... | Section: ...\n<text>), calls local Ollama (nomic-embed-text model) to get a vector, and inserts the row into a note_chunks table in Postgres — storing path, hash, chunk index, header, content, metadata, and embedding.

## test_search.py — the retrieval pipeline

Embeds the search query with the same Ollama model.
Runs a single SQL query doing Reciprocal Rank Fusion (RRF): it ranks results from a vector similarity search (embedding <=> query_vector) and a full-text search (ts_rank_cd / plainto_tsquery) separately, then combines their ranks with 1/(60+rank) scoring so both signals contribute.
Returns the top-K chunks with file path, header, content snippet, and combined score.

![Project Architecture](./obsidian_document_pipeline_flow.svg)
