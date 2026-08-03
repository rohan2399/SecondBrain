import os
import hashlib
import json
import psycopg2
import frontmatter  # pip install python-frontmatter
import ollama       # pip install ollama

# --- Dynamic Folder Configuration ---
# 1. Get the absolute path of the directory where THIS script lives
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Fetch the relative paths from the .env file
rel_input = os.getenv("INPUT_FOLDER", "NormalFolder")
rel_obsidian = os.getenv("OBSIDIAN_FOLDER", "ObsidianVault/ExtractedDocs")
rel_attachments = os.getenv("OBSIDIAN_ATTACHMENTS", "ObsidianVault/ExtractedDocs/Attachments")

# 3. Resolve them cleanly to absolute paths on your machine
INPUT_FOLDER = os.path.normpath(os.path.join(BASE_DIR, rel_input))
OBSIDIAN_FOLDER = os.path.normpath(os.path.join(BASE_DIR, rel_obsidian))
OBSIDIAN_ATTACHMENTS = os.path.normpath(os.path.join(BASE_DIR, rel_attachments))

# Create all necessary folders automatically if they don't exist yet
os.makedirs(INPUT_FOLDER, exist_ok=True)
os.makedirs(OBSIDIAN_FOLDER, exist_ok=True)
os.makedirs(OBSIDIAN_ATTACHMENTS, exist_ok=True)

print(f"Targeting Input Directory: {INPUT_FOLDER}")
print(f"Targeting Obsidian Directory: {OBSIDIAN_FOLDER}")

# --- Database & Model Configuration ---
DB_CONN = os.getenv("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/second_brain")

EMBEDDING_MODEL = "nomic-embed-text"


def compute_hash(text: str) -> str:
    """Compute SHA-256 hash to detect modified markdown files."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_markdown(content: str):
    """Split Markdown cleanly by headers (# / ## / ###)."""
    lines = content.split("\n")
    chunks = []
    current_header = "Root"
    current_lines = []

    for line in lines:
        if line.startswith("#"):
            if current_lines:
                text_chunk = "\n".join(current_lines).strip()
                if text_chunk:
                    chunks.append((current_header, text_chunk))
                current_lines = []
            current_header = line.lstrip("#").strip()
        else:
            current_lines.append(line)

    if current_lines:
        text_chunk = "\n".join(current_lines).strip()
        if text_chunk:
            chunks.append((current_header, text_chunk))

    return chunks


def sync_obsidian_vault():
    """Scan OBSIDIAN_FOLDER, chunk Markdown files, and sync embeddings to PostgreSQL."""
    with psycopg2.connect(DB_CONN) as conn:
        with conn.cursor() as cur:
            for root, dirs, files in os.walk(OBSIDIAN_FOLDER):
                # Prevent os.walk from entering hidden folders like .obsidian
                dirs[:] = [d for d in dirs if not d.startswith(".")]

                for file in files:
                    if not file.endswith(".md"):
                        continue

                    full_path = os.path.join(root, file)
                    
                    # Convert Windows backslashes (\) to forward slashes (/) for clean paths
                    rel_path = os.path.relpath(full_path, OBSIDIAN_FOLDER).replace("\\", "/")

                    with open(full_path, "r", encoding="utf-8") as f:
                        raw_text = f.read()

                    # Compute SHA-256 hash of the file content
                    file_hash = compute_hash(raw_text)

                    # 1. Skip unchanged files using SHA-256
                    cur.execute(
                        "SELECT file_hash FROM note_chunks WHERE file_path = %s LIMIT 1",
                        (rel_path,)
                    )
                    row = cur.fetchone()
                    if row and row[0] == file_hash:
                        continue

                    # 2. Delete outdated chunks if the file was modified
                    cur.execute("DELETE FROM note_chunks WHERE file_path = %s", (rel_path,))

                    # 3. Parse YAML frontmatter & chunk text
                    post = frontmatter.loads(raw_text)
                    meta = json.dumps(post.metadata)
                    chunks = chunk_markdown(post.content)

                    # 4. Generate embeddings via local Ollama and insert into PostgreSQL
                    for idx, (header, text) in enumerate(chunks):
                        embed_text = f"File: {rel_path} | Section: {header}\n{text}"
                        
                        response = ollama.embeddings(
                            model=EMBEDDING_MODEL,
                            prompt=embed_text
                        )
                        vector = response["embedding"]

                        cur.execute("""
                            INSERT INTO note_chunks 
                            (file_path, file_hash, chunk_index, header_context, content, metadata, embedding)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            rel_path, file_hash, idx, header, text, meta, json.dumps(vector)
                        ))

                    print(f"Synced to DB: {rel_path} ({len(chunks)} chunks)")


if __name__ == "__main__":
    sync_obsidian_vault()