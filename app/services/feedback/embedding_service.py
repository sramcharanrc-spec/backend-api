import numpy as np

def simple_embedding(text: str):
    return [ord(c) % 50 for c in text[:50]]


def cosine_similarity(v1, v2):
    dot = sum(a*b for a, b in zip(v1, v2))
    norm1 = sum(a*a for a in v1) ** 0.5
    norm2 = sum(b*b for b in v2) ** 0.5

    return dot / (norm1 * norm2) if norm1 and norm2 else 0