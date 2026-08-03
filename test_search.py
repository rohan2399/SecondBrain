import os
import json
import psycopg2
import ollama

# Connection & Model Configuration
DB_CONN = os.getenv("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/second_brain")
EMBEDDING_MODEL = "nomic-embed-text"

def hybrid_search(query: str, top_k: int = 5):
    """Executes Reciprocal Rank Fusion (RRF) combining vector similarity & full-text search."""
    # 1. Generate local query embedding
    response = ollama.embeddings(
        model=EMBEDDING_MODEL,
        prompt=query
    )
    query_vector = json.dumps(response["embedding"])

    # 2. RRF SQL Query
    rrf_sql = """
    WITH vector_search AS (
        SELECT id,
               ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS rank
        FROM note_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT 20
    ),
    fts_search AS (
        SELECT id,
               ROW_NUMBER() OVER (
                   ORDER BY ts_rank_cd(fts, plainto_tsquery('english', %s)) DESC
               ) AS rank
        FROM note_chunks
        WHERE fts @@ plainto_tsquery('english', %s)
        ORDER BY ts_rank_cd(fts, plainto_tsquery('english', %s)) DESC
        LIMIT 20
    )
    SELECT 
        c.file_path,
        c.header_context,
        c.content,
        COALESCE(1.0 / (60 + v.rank), 0.0) + COALESCE(1.0 / (60 + f.rank), 0.0) AS rrf_score
    FROM note_chunks c
    LEFT JOIN vector_search v ON c.id = v.id
    LEFT JOIN fts_search f ON c.id = f.id
    WHERE v.id IS NOT NULL OR f.id IS NOT NULL
    ORDER BY rrf_score DESC
    LIMIT %s;
    """

    with psycopg2.connect(DB_CONN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                rrf_sql, 
                (query_vector, query_vector, query, query, query, top_k)
            )
            return cur.fetchall()

if __name__ == "__main__":
    # Test with a concept or word you know is inside your Obsidian vault
    test_query = "backend"
    print(f"\nSearching for: '{test_query}'\n" + "-"*50)
    
    results = hybrid_search(test_query, top_k=3)
    
    for i, (path, header, content, score) in enumerate(results, 1):
        print(f"\nResult {i} | Score: {score:.4f}")
        print(f"File   : {path}")
        print(f"Section: {header}")
        print(f"Snippet: {content[:150]}...")