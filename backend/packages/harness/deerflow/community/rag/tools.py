"""RAG Tools - Add, search, list, and delete from a ChromaDB knowledge base."""
import json
import logging
import time
from functools import lru_cache

from langchain.tools import tool

from deerflow.config.runtime_paths import runtime_home

logger = logging.getLogger(__name__)

_rag_counter = [0]  # mutable counter for unique IDs
_COLLECTION_NAME = "knowledge"


@lru_cache(maxsize=1)
def _get_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def _get_collection():
    import chromadb
    path = runtime_home() / "rag_store"
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(str(path))
    return client.get_or_create_collection(name=_COLLECTION_NAME)


@tool("rag_search", parse_docstring=True)
def rag_search_tool(query: str, n_results: int = 3) -> str:
    """Search the built-in DeerFlow knowledge base for project-specific information.

    Use this for questions about DeerFlow's own architecture, middleware chain,
    sandbox system, skill loading, memory system, tool system, and configuration.
    This knowledge base contains curated project documentation — prefer it over
    web_search when the user asks about DeerFlow internals.

    Args:
        query: The search query or question to find relevant information for.
        n_results: Number of results to return (default 3, max 10).
    """
    n_results = max(1, min(n_results, 10))

    try:
        model = _get_embedding_model()
        collection = _get_collection()

        count = collection.count()
        if count == 0:
            return json.dumps({"error": "Knowledge base is empty. No documents to search."}, ensure_ascii=False)

        query_emb = model.encode([query]).tolist()
        results = collection.query(query_embeddings=query_emb, n_results=n_results)

        hits = []
        for doc, dist, mid in zip(
            results["documents"][0],
            results["distances"][0],
            results["ids"][0],
        ):
            hits.append({
                "id": mid,
                "content": doc,
                "relevance_score": round(1.0 - dist / 2, 3),  # normalize to 0-1
            })

        return json.dumps({
            "query": query,
            "total_results": len(hits),
            "results": hits,
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"RAG search failed: {type(e).__name__}: {e}")
        return json.dumps({"error": f"Search failed: {str(e)}"}, ensure_ascii=False)


@tool("rag_add", parse_docstring=True)
def rag_add_tool(content: str) -> str:
    """Add a document to the DeerFlow knowledge base for future reference.

    Use this when you learn something noteworthy about DeerFlow that you
    want to remember and retrieve later via rag_search. For example: project
    architecture details, configuration gotchas, middleware behavior, or
    any DeerFlow-specific insight worth saving.

    Args:
        content: The text content to store in the knowledge base.
    """
    if not content or not content.strip():
        return json.dumps({"error": "Content cannot be empty."}, ensure_ascii=False)

    try:
        model = _get_embedding_model()
        collection = _get_collection()

        _rag_counter[0] += 1
        doc_id = f"rag_{int(time.time() * 1000)}_{_rag_counter[0]}"

        embedding = model.encode([content]).tolist()
        collection.add(
            documents=[content],
            embeddings=embedding,
            ids=[doc_id],
        )

        return json.dumps({
            "success": True,
            "id": doc_id,
            "content_preview": content[:100],
            "total_documents": collection.count(),
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"RAG add failed: {type(e).__name__}: {e}")
        return json.dumps({"error": f"Add failed: {str(e)}"}, ensure_ascii=False)


@tool("rag_delete", parse_docstring=True)
def rag_delete_tool(ids: str) -> str:
    """Remove documents from the DeerFlow knowledge base by ID.

    Use this to delete outdated or incorrect entries. Get the IDs first
    by searching with rag_search, then pass the IDs to this tool.

    Args:
        ids: Comma-separated document IDs to delete (e.g. "rag_123_1,rag_123_2").
    """
    if not ids or not ids.strip():
        return json.dumps({"error": "IDs cannot be empty."}, ensure_ascii=False)

    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    if not id_list:
        return json.dumps({"error": "No valid IDs provided."}, ensure_ascii=False)

    try:
        collection = _get_collection()

        # Verify which IDs actually exist
        existing = collection.get(ids=id_list)
        existing_ids = existing["ids"]
        missing = [i for i in id_list if i not in existing_ids]

        if not existing_ids:
            return json.dumps({"error": "None of the provided IDs exist in the knowledge base.", "requested_ids": id_list}, ensure_ascii=False)

        collection.delete(ids=existing_ids)

        result = {
            "success": True,
            "deleted_count": len(existing_ids),
            "deleted_ids": existing_ids,
            "total_documents": collection.count(),
        }
        if missing:
            result["warning"] = f"IDs not found: {', '.join(missing)}"

        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"RAG delete failed: {type(e).__name__}: {e}")
        return json.dumps({"error": f"Delete failed: {str(e)}"}, ensure_ascii=False)


@tool("rag_list", parse_docstring=True)
def rag_list_tool() -> str:
    """List all documents currently in the DeerFlow knowledge base.

    Shows each document's ID and a preview of its content.
    Use this to see what's stored before deciding what to search or delete.

    Args:
        This tool takes no arguments.
    """
    try:
        collection = _get_collection()

        count = collection.count()
        if count == 0:
            return json.dumps({"total_documents": 0, "documents": []}, indent=2, ensure_ascii=False)

        all_docs = collection.get()
        docs = [
            {
                "id": doc_id,
                "content_preview": doc[:150] + ("..." if len(doc) > 150 else ""),
            }
            for doc_id, doc in zip(all_docs["ids"], all_docs["documents"])
        ]

        return json.dumps({
            "total_documents": count,
            "documents": docs,
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"RAG list failed: {type(e).__name__}: {e}")
        return json.dumps({"error": f"List failed: {str(e)}"}, ensure_ascii=False)
