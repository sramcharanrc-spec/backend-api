from .feedback_store import get_all_feedback
from .embedding_service import simple_embedding, cosine_similarity


def find_similar_feedback(query_text, top_k=3):

    query_vec = simple_embedding(query_text)

    scored = []

    for f in get_all_feedback():

        if not f.get("embedding"):
            f["embedding"] = simple_embedding(
                f"{f['field']} {f['original']} {f['corrected']}"
            )

        score = cosine_similarity(query_vec, f["embedding"])

        scored.append((score, f))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [f for _, f in scored[:top_k]]