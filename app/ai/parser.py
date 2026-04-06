import json

def parse_llm_json(text: str):
    try:
        return json.loads(text)
    except:
        return {
            "risk_score": 0.5,
            "reason": "Parsing failed",
            "suggestion": text
        }