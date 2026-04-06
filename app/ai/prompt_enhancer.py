from app.services.feedback.similarity_engine import find_similar_feedback

def enhance_prompt(base_prompt, claim):

    query = str(claim)

    similar = find_similar_feedback(query)

    examples = ""

    for f in similar:
        examples += f"""
Field: {f['field']}
Wrong: {f['original']}
Correct: {f['corrected']}
"""

    return f"""
You are a healthcare AI that learns from past corrections.

Previous corrections:
{examples}

-----------------------------------

{base_prompt}
"""