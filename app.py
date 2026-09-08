import os
import json
import ollama
from flask import Flask, render_template, request, Response, stream_with_context

# Reuse the existing hybrid_search function directly — no duplicated retrieval logic.
from test_search import hybrid_search

# --- Configuration ---
CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3.1")  # Ollama model used to generate answers
TOP_K = int(os.getenv("RAG_TOP_K", "5"))

app = Flask(__name__)


def build_context_block(results):
    """
    Turn hybrid_search() rows into a single context string for the LLM prompt,
    and a parallel list of source dicts for the UI's citation panel.
    results: list of (file_path, header_context, content, rrf_score)
    """
    context_parts = []
    sources = []

    for i, (file_path, header, content, score) in enumerate(results, 1):
        context_parts.append(
            f"[Source {i}] File: {file_path} | Section: {header}\n{content}"
        )
        sources.append({
            "index": i,
            "file_path": file_path,
            "header": header,
            "snippet": content[:220] + ("..." if len(content) > 220 else ""),
            "score": round(float(score), 4),
        })

    context_block = "\n\n---\n\n".join(context_parts)
    return context_block, sources


SYSTEM_PROMPT = (
    "You are a helpful assistant answering questions using the user's personal "
    "notes (their 'second brain'). You are given retrieved note excerpts as context. "
    "Answer using only the provided context. If the context doesn't contain the "
    "answer, say so clearly instead of guessing. When you use a fact from a source, "
    "reference it inline like [Source 1]. Keep answers concise and direct."
)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Evaluates query intent. If 'GENERAL', bypasses retrieval and chats normally.
    If 'RAG', retrieves relevant note chunks via hybrid_search() from test_search.py, 
    then streams an LLM-generated answer grounded in those chunks.
    """
    data = request.get_json(force=True)
    user_message = (data.get("message") or "").strip()
    history = data.get("history", [])  # list of {role, content}

    if not user_message:
        return {"error": "Empty message"}, 400

    def generate():
        # --- 1. INTENT CLASSIFICATION ---
        classifier_prompt = (
            "Classify this query. If it requires searching personal notes, markdown files, "
            "or code context, output ONLY 'RAG'. If it is a greeting, math problem, or general "
            f"knowledge question, output ONLY 'GENERAL'. Query: {user_message}"
        )
        
        try:
            intent_response = ollama.chat(
                model=CHAT_MODEL, 
                messages=[{'role': 'user', 'content': classifier_prompt}]
            )
            intent = intent_response.get("message", {}).get("content", "").strip().upper()
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Classification failed: {e}'})}\n\n"
            return

        # --- 2. GENERAL CHAT BYPASS ---
        if "GENERAL" in intent:
            # Send empty sources so UI citations panel remains clean
            yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
            
            messages = [{"role": "system", "content": "You are a helpful assistant."}]
            for turn in history[-6:]:
                if turn.get("role") in ("user", "assistant") and turn.get("content"):
                    messages.append({"role": turn["role"], "content": turn["content"]})
            
            messages.append({"role": "user", "content": user_message})
            
            try:
                stream = ollama.chat(model=CHAT_MODEL, messages=messages, stream=True)
                for chunk in stream:
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': f'Generation failed: {e}'})}\n\n"
                return
                
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # --- 3. RAG PIPELINE (ORIGINAL LOGIC) ---
        try:
            results = hybrid_search(user_message, top_k=TOP_K)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Retrieval failed: {e}'})}\n\n"
            return

        context_block, sources = build_context_block(results)

        # Send sources to the client first so the UI can render citations immediately
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

        # Build the message list for the chat model
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for turn in history[-6:]:  # keep last few turns for lightweight continuity
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})

        messages.append({
            "role": "user",
            "content": f"Context from my notes:\n\n{context_block}\n\nQuestion: {user_message}"
        })

        # Stream the generation
        try:
            stream = ollama.chat(model=CHAT_MODEL, messages=messages, stream=True)
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Generation failed: {e}'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
