from .feedback_store import get_all_feedback


def get_field_patterns(field):

    values = [
        f["corrected"]
        for f in get_all_feedback()
        if f["field"] == field
    ]

    freq = {}

    for v in values:
        freq[v] = freq.get(v, 0) + 1

    return sorted(freq.items(), key=lambda x: x[1], reverse=True)