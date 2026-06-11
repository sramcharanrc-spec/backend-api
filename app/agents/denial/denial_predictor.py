import json

from app.ai.llm_service import invoke_llm


class DenialPredictor:

    async def predict(self, claim):
        prompt = f"""
Predict denial risk for this claim.

Return JSON only:
{{
  "risk_score": 0.0,
  "reasons": [],
  "risk_level": "LOW|MEDIUM|HIGH",
  "recommended_action": ""
}}

Claim:
{json.dumps(claim, default=str)}
"""

        try:
            response = await invoke_llm(prompt, expect_json=True)

            if not isinstance(response, dict):
                return {
                    "risk_score": 0.0,
                    "risk_level": "UNKNOWN",
                    "reasons": ["LLM returned non-JSON response"],
                    "recommended_action": "Manual review if needed",
                }

            risk_score = float(response.get("risk_score", 0) or 0)

            if risk_score > 1:
                risk_score = risk_score / 100

            risk_score = max(0.0, min(1.0, risk_score))

            response["risk_score"] = risk_score
            response["risk_score_percent"] = round(risk_score * 100)

            if not response.get("risk_level"):
                if risk_score >= 0.75:
                    response["risk_level"] = "HIGH"
                elif risk_score >= 0.4:
                    response["risk_level"] = "MEDIUM"
                else:
                    response["risk_level"] = "LOW"

            return response

        except Exception as error:
            return {
                "risk_score": 0.0,
                "risk_score_percent": 0,
                "risk_level": "UNKNOWN",
                "reasons": [str(error)],
                "recommended_action": "Manual review if denial risk cannot be predicted",
            }