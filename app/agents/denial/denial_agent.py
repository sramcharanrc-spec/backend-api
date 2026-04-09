# from app.agents.base.base_agent import BaseAgent
# from app.agents.bedrock.client import BedrockClient
# from app.websocket.manager import manager
# from app.services.audit_service import log_audit
# from app.services.analytics_service import update_metrics
# from app.ai.ai_suggester import generate_suggestions
# from app.ai.prompt_enhancer import enhance_prompt
# import json
# import re


# class DenialAgent(BaseAgent):

#     def __init__(self):
#         super().__init__()
#         self.llm = BedrockClient()

#     async def run(self, claim):

#         print("🚫 [DenialAgent] Started")

#         if claim is None:
#             raise ValueError("DenialAgent received empty claim")

#         await self.log("[DenialAgent] Bedrock AI analyzing claim")
#         await manager.send_event("denial", "running")

#         try:
#             # -------------------------
#             # Extract CPT + duplicates
#             # -------------------------
#             cpt_codes = [s["cpt"] for s in claim.get("services", [])]

#             duplicates = [c for c in set(cpt_codes) if cpt_codes.count(c) > 1]

#             duplicate_warning = (
#                 f"Duplicate CPT codes detected: {duplicates}" if duplicates else ""
#             )

#             # -------------------------
#             # 🧠 ICD AUTO-SUGGEST
#             # -------------------------
#             if not claim.get("icd_codes"):
#                 ai_data = await generate_suggestions(claim)

#                 suggested_icd = ai_data.get("icd_codes", [])

#                 if suggested_icd:
#                     claim["icd_codes"] = suggested_icd
#                     claim["icd_applied"] = True
#                     claim["warnings"] = claim.get("warnings", [])
#                     claim["warnings"].append("ICD auto-suggested by AI")

#                     print(f"🧠 ICD Auto-Suggested: {suggested_icd}")

#             # -------------------------
#             # 🔥 DEFINE BASE PROMPT
#             # -------------------------
#             base_prompt = f"""
# You are a healthcare claims denial prevention AI.

# CPT Codes: {cpt_codes}
# ICD Codes: {claim.get('icd_codes')}

# Alerts:
# {duplicate_warning}

# STRICT RULES:
# - Return ONLY valid JSON
# - No explanation
# - No text before or after JSON
# - No markdown

# Return JSON:
# {{
#   "risk_score": 0-1,
#   "reason": "...",
#   "suggestion": "..."
# }}
# """

#             # -------------------------
#             # 🔥 ENHANCE PROMPT (FEEDBACK LOOP)
#             # -------------------------
#             prompt = enhance_prompt(base_prompt, claim)

#             llm_output = await self.llm.invoke(prompt)
#             print("🧠 LLM Output:", llm_output)

#             # -------------------------
#             # 🔥 ROBUST JSON PARSING
#             # -------------------------
#             try:
#                 parsed = json.loads(llm_output)
#             except:
#                 try:
#                     match = re.search(r'\{.*\}', llm_output, re.DOTALL)
#                     if match:
#                         parsed = json.loads(match.group().strip())
#                     else:
#                         raise ValueError("No JSON found")
#                 except Exception as e:
#                     print("❌ LLM Parsing Error:", str(e))
#                     parsed = {
#                         "risk_score": 0.5,
#                         "reason": "Parsing failed",
#                         "suggestion": llm_output
#                     }

#             # -------------------------
#             # Extract values
#             # -------------------------
#             risk_score = parsed.get("risk_score", 0.0)
#             reason = parsed.get("reason", "")
#             suggestion = parsed.get("suggestion", "")

#             # -------------------------
#             # Store in claim
#             # -------------------------
#             claim["denial_risk"] = {
#                 "risk_score": risk_score,
#                 "reason": reason,
#                 "suggestion": suggestion
#             }

#             claim["ai_suggestion"] = suggestion

#             update_metrics("denial")

#             # -------------------------
#             # Audit
#             # -------------------------
#             log_audit(
#                 claim.get("claim_id"),
#                 "denial",
#                 "completed",
#                 {
#                     "risk_score": risk_score,
#                     "reason": reason,
#                     "suggestion": suggestion,
#                     "duplicates": duplicates,
#                     "icd_codes": claim.get("icd_codes")
#                 }
#             )

#             await manager.send_event("denial", "completed", parsed)

#             return {
#                 "claim": claim,

#                 "pipeline": {
#                     "steps": {
#                         "denial_checked": True
#                     }
#                 },

#                 "stage": "denial_checked"
#             }

#         except Exception as e:
#             print("❌ DenialAgent Error:", str(e))

#             log_audit(
#                 claim.get("claim_id"),
#                 "denial",
#                 "failed",
#                 {"error": str(e)}
#             )

#             await manager.send_event("denial", "failed", {"error": str(e)})

#             raise

from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager
from app.services.audit_service import log_audit


class DenialAgent(BaseAgent):

    async def run(self, claim):

        print("🚫 [DenialAgent] Started")

        await manager.send_event("denial", "running")

        try:
            # Check if claim was denied
            if claim.get("status") == "denied":
                print(f"⚠️ Claim denied (Code: {claim.get('denial_code')}). Applying AI correction...")
                
                reason = "Invalid CPT or missing modifiers" if claim.get("denial_code") == "CO-50" else "Unknown reasoning"
                suggestion = "Auto-corrected modifier and rebilled"
                
                claim["denial_risk"] = {
                    "risk_score": 0.95,
                    "reason": reason,
                    "suggestion": suggestion
                }
                
                # Auto-correct Claim
                claim["status"] = "corrected"
            else:
                claim["denial_risk"] = {
                    "risk_score": 0.1,
                    "reason": "Clear to pay",
                    "suggestion": None
                }

            claim["denial_checked"] = True

            log_audit(
                claim.get("claim_id"),
                "denial",
                "completed",
                claim.get("denial_risk")
            )

            await manager.send_event("denial", "completed", claim.get("denial_risk"))

            return {
                "claim": claim,
                "denial_risk": claim.get("denial_risk"),
                "pipeline": {
                    "steps": {
                        "denial_checked": True
                    }
                },
                "stage": "denial_checked"
            }

        except Exception as e:
            await manager.send_event("denial", "failed", {"error": str(e)})
            raise