# app/agents/validation/rule_engine.py

def validate_claim(data, rules):
    results = []

    for rule in rules:
        field = rule["field"]
        value = data.get(field)

        passed = rule["rule"](value)

        results.append({
            "field": field,
            "passed": passed,
            "message": rule["message"]
        })

    return results