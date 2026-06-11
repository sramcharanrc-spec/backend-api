# import json
# import time
# from typing import Any, Dict

# from app.ai.llm_service import invoke_llm
# from app.agents.denial_ai.appeal_generator import AppealGenerator
# from app.agents.denial_ai.denial_classifier import DenialClassifier
# from app.agents.denial_ai.denial_suggester import DenialSuggester
# from app.websocket.manager import manager
# from ehr_pipeline.app.agents import denial


# class LLMDenialAgent:
#     def __init__(self):
#         self.classifier = DenialClassifier()
#         self.suggester = DenialSuggester()
#         self.appeal_generator = AppealGenerator()

#     async def run(self, claim: Dict[str, Any], denial: Dict[str, Any] | None = None) -> Dict[str, Any]:
#         claim = claim or {}
#         claim_id = claim.get("claim_id", "UNKNOWN")
#         denial = denial or claim.get("denial") or claim.get("denial_risk") or {}

#         await manager.send_event("denial_ai", "running", {
#             "agent": "DENIAL_AI",
#             "claim_id": claim_id,
#         })

#         classification = self.classifier.classify(claim, denial)
#         fallback = self._fallback_analysis(claim, classification)
#         llm_analysis = await self._llm_analysis(claim, classification, fallback)
#         analysis = {**fallback, **(llm_analysis or {})}
#         appeal = self.appeal_generator.generate(claim, analysis)
#         analysis["appeal_summary"] = appeal["appeal_summary"]
#         analysis["appeal_text"] = appeal["appeal_text"]

#         claim["denial_ai"] = analysis

#         start_time = time.time()

#         print("\n" + "=" * 80)
#         print("🧠 [LLMDenialAgent] STARTED")
#         print(f"🧾 Claim ID: {claim_id}")
#         print(f"📌 Denial input: {denial}")
#         print("=" * 80)

#         await manager.send_event("denial_ai", "completed", {
#             "agent": "DENIAL_AI",
#             "claim_id": claim_id,
#             "analysis": analysis,
#         })

#         return {
#             "claim": claim,
#             "denial_ai": analysis,
#             "appeal": appeal,
#             "pipeline": {"steps": {"denial_ai_analyzed": True, "appeal_generated": True}},
#             "stage": "denial_ai_completed",
#         }

#     def auto_fix(self, claim: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
#         corrected = {**claim}
#         services = [dict(item) for item in corrected.get("services", [])]

#         for suggestion in analysis.get("modifier_suggestions", []):
#             modifier = suggestion.get("modifier") or suggestion.get("suggested")
#             if modifier and services:
#                 services[0]["modifier"] = str(modifier).split(",")[0].strip().replace("modifier", "").strip()[:2]

#         for suggestion in analysis.get("icd_suggestions", []):
#             suggested = suggestion.get("code") or suggestion.get("suggested")
#             if suggested and isinstance(suggested, str) and suggested[:1].isalpha():
#                 corrected["icd_codes"] = [suggested.upper()]

#         corrected["services"] = services
#         corrected["denial_ai_auto_fixed"] = True
#         corrected["resubmission_strategy"] = analysis.get("resubmission_strategy")
#         return corrected

#     def _fallback_analysis(self, claim: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
#         suggestions = self.suggester.suggest(claim, classification)
#         return {
#             **classification,
#             "root_cause": classification.get("root_cause"),
#             "suggested_corrections": suggestions["suggested_corrections"],
#             "modifier_suggestions": suggestions["modifier_suggestions"],
#             "icd_suggestions": suggestions["icd_suggestions"],
#             "cpt_corrections": [],
#             "documentation_gaps": classification.get("focus", []),
#             "payer_rule_findings": [f"Review payer policy for {classification.get('category')}"],
#             "medical_necessity": "Review diagnosis support and documentation for billed CPTs",
#             "resubmission_strategy": "Correct claim data, attach supporting documentation, and resubmit as corrected claim",
#             "denial_prevention_tips": suggestions["prevention_tips"],
#             "retry_probability": classification.get("retry_probability", 0.45),
#         }

#     async def _llm_analysis(self, claim: Dict[str, Any], classification: Dict[str, Any], fallback: Dict[str, Any]):
#         prompt = f"""
# You are a healthcare RCM denial specialist. Analyze this denied claim.

# Claim:
# {json.dumps(claim, indent=2)}

# Denial classification:
# {json.dumps(classification, indent=2)}

# Return structured JSON with:
# root_cause, suggested_corrections, cpt_corrections, icd_suggestions,
# modifier_suggestions, payer_rule_findings, documentation_gaps,
# medical_necessity, appeal_summary, denial_prevention_tips,
# resubmission_strategy, retry_probability.
# """
#         try:
#             response = await invoke_llm(prompt, expect_json=True)
#             return response if isinstance(response, dict) else {}
#         except Exception as exc:
#             return {
#                 "llm_status": "fallback",
#                 "llm_error": str(exc),
#                 "appeal_summary": (
#                     f"Claim {claim.get('claim_id')} was denied for {fallback.get('root_cause')}. "
#                     "Corrected claim data and supporting documentation should be reviewed for resubmission."
#                 ),
#             }

import json
import time
from typing import Any, Dict

from app.ai.llm_service import invoke_llm
from app.agents.denial_ai.appeal_generator import AppealGenerator
from app.agents.denial_ai.denial_classifier import DenialClassifier
from app.agents.denial_ai.denial_suggester import DenialSuggester
from app.intake.db_service import clean_nan
from app.utils.pipeline_events import apply_pipeline_patch, send_pipeline_event
from app.websocket.manager import manager

def clean_llm_json_response(raw: str) -> str:
    raw = str(raw or "").strip()

    if "```json" in raw:
        raw = raw.split("```json", 1)[1]
        raw = raw.split("```", 1)[0]
        return raw.strip()

    if "```" in raw:
        raw = raw.split("```", 1)[1]
        raw = raw.split("```", 1)[0]
        return raw.strip()

    return raw

class LLMDenialAgent:
    """
    LLMDenialAgent analyzes denied claims and prepares appeal/resubmission guidance.

    Responsibilities:
    - Classify denial reason/code
    - Generate fallback denial analysis
    - Optionally enrich analysis using LLM
    - Generate appeal draft
    - Suggest corrections
    - Emit frontend WebSocket events
    """

    def __init__(self):
        self.classifier = DenialClassifier()
        self.suggester = DenialSuggester()
        self.appeal_generator = AppealGenerator()

    async def run(
        self,
        claim: Dict[str, Any],
        denial: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        start_time = time.time()

        claim = claim or {}
        claim_id = claim.get("claim_id", "UNKNOWN")
        denial = denial or claim.get("denial") or claim.get("denial_risk") or {}

        print("\n" + "=" * 80)
        print("🧠 [LLMDenialAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📌 Denial input: {denial}")
        print("=" * 80)

        await send_pipeline_event(
            manager,
            topic="denial_ai",
            action="running",
            claim_id=claim_id,
            stage="DENIAL_AI",
            status="RUNNING",
            progress=80,
            current_stage="DENIAL_AI",
            current_agent="DENIAL_AI",
            active_step="denial_ai",
            pipeline_state="DENIAL_AI_RUNNING",
            pipeline_status="RUNNING",
            message="Denial AI analysis started",
            claim=claim,
        )

        try:
            # ---------------------------------------------------
            # Step 1: Classify denial
            # ---------------------------------------------------
            print("➡️ [1] Classifying denial...")

            classification = self.classifier.classify(claim, denial)
            classification = clean_nan(classification)

            print("✅ Classification:")
            print(json.dumps(classification, indent=2, default=str))

            # ---------------------------------------------------
            # Step 2: Fallback analysis
            # ---------------------------------------------------
            print("➡️ [2] Building fallback analysis...")

            fallback = self._fallback_analysis(claim, classification)
            fallback = clean_nan(fallback)

            print("✅ Fallback analysis ready")

            # ---------------------------------------------------
            # Step 3: LLM analysis
            # ---------------------------------------------------
            print("➡️ [3] Running LLM denial analysis...")

            llm_analysis = await self._llm_analysis(
                claim,
                classification,
                fallback,
            )

            llm_analysis = clean_nan(llm_analysis or {})

            print("✅ LLM analysis received:")
            print(json.dumps(llm_analysis, indent=2, default=str))

            analysis = {
                **fallback,
                **llm_analysis,
            }

            analysis = clean_nan(analysis)

            # ---------------------------------------------------
            # Step 4: Appeal draft
            # ---------------------------------------------------
            print("➡️ [4] Generating appeal draft...")

            appeal = self.appeal_generator.generate(claim, analysis)
            appeal = clean_nan(appeal)

            analysis["appeal_summary"] = appeal.get("appeal_summary")
            analysis["appeal_text"] = appeal.get("appeal_text")
            analysis["appeal"] = appeal

            # ---------------------------------------------------
            # Step 5: Finalize result
            # ---------------------------------------------------
            duration_seconds = round(time.time() - start_time, 2)

            analysis["duration_seconds"] = duration_seconds
            analysis["source"] = (
                "llm_with_fallback"
                if llm_analysis and llm_analysis.get("llm_status") != "fallback"
                else "fallback_only"
            )

            analysis = clean_nan(analysis)

            claim["denial_ai"] = analysis
            claim["denial_ai_duration_seconds"] = duration_seconds
            claim["denial_ai_status"] = "completed"
            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage="DENIAL_AI",
                status="COMPLETED",
                progress=82,
                current_stage="DENIAL_AI",
                current_agent="DENIAL_AI",
                active_step="denial_ai",
                pipeline_state="DENIAL_AI_COMPLETED",
                pipeline_status="COMPLETED",
                message="Denial AI analysis completed",
            )
            claim["pipeline"]["steps"]["denial_ai_analyzed"] = True
            claim["pipeline"]["steps"]["appeal_generated"] = bool(appeal.get("appeal_text"))

            await send_pipeline_event(
                manager,
                topic="denial_ai",
                action="completed",
                claim_id=claim_id,
                stage="DENIAL_AI",
                status="COMPLETED",
                progress=82,
                current_stage="DENIAL_AI",
                current_agent="DENIAL_AI",
                active_step="denial_ai",
                pipeline_state="DENIAL_AI_COMPLETED",
                pipeline_status="COMPLETED",
                message="Denial AI analysis completed",
                claim=claim,
                extra=clean_nan({
                    "agent": "DENIAL_AI",
                    "analysis": analysis,
                    "appeal": appeal,
                    "duration_seconds": duration_seconds,
                    "next_agent": "Payment Agent",
                }),
            )

            print("✅ [LLMDenialAgent] COMPLETED")
            print(f"⏱️ Denial AI duration: {duration_seconds}s")
            print("=" * 80 + "\n")

            return {
                "claim": clean_nan(claim),
                "denial_ai": analysis,
                "appeal": appeal,
                "pipeline": clean_nan(claim.get("pipeline", {})),
                "stage": "denial_ai_completed",
                "status": "COMPLETED",
                "duration_seconds": duration_seconds,
            }

        except Exception as error:
            # ---------------------------------------------------
            # Technical failure: use fallback path
            # ---------------------------------------------------
            duration_seconds = round(time.time() - start_time, 2)

            print("❌ [LLMDenialAgent] FAILED")
            print(f"❌ Error: {str(error)}")
            print(f"⏱️ Duration before failure: {duration_seconds}s")
            print("=" * 80 + "\n")

            await send_pipeline_event(
                manager,
                topic="denial_ai",
                action="failed",
                claim_id=claim_id,
                stage="DENIAL_AI",
                status="FAILED",
                progress=80,
                current_stage="DENIAL_AI",
                current_agent="DENIAL_AI",
                active_step="denial_ai",
                pipeline_state="DENIAL_AI_FAILED",
                pipeline_status="FAILED",
                message=str(error),
                claim=claim,
                extra=clean_nan({
                    "agent": "DENIAL_AI",
                    "error": str(error),
                    "duration_seconds": duration_seconds,
                }),
            )

            fallback_classification = self.classifier.classify(claim, denial)
            fallback_classification = clean_nan(fallback_classification)

            fallback = self._fallback_analysis(claim, fallback_classification)
            fallback = clean_nan(fallback)

            appeal = self.appeal_generator.generate(claim, fallback)
            appeal = clean_nan(appeal)

            fallback["appeal_summary"] = appeal.get("appeal_summary")
            fallback["appeal_text"] = appeal.get("appeal_text")
            fallback["appeal"] = appeal
            fallback["llm_status"] = "failed_fallback_used"
            fallback["llm_error"] = str(error)
            fallback["duration_seconds"] = duration_seconds
            fallback["source"] = "fallback_after_error"

            fallback = clean_nan(fallback)

            claim["denial_ai"] = fallback
            claim["denial_ai_duration_seconds"] = duration_seconds
            claim["denial_ai_status"] = "completed_with_fallback"
            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage="DENIAL_AI",
                status="COMPLETED_WITH_FALLBACK",
                progress=82,
                current_stage="DENIAL_AI",
                current_agent="DENIAL_AI",
                active_step="denial_ai",
                pipeline_state="DENIAL_AI_COMPLETED",
                pipeline_status="COMPLETED_WITH_FALLBACK",
                message="Denial AI fallback analysis completed",
            )
            claim["pipeline"]["steps"]["denial_ai_analyzed"] = True
            claim["pipeline"]["steps"]["appeal_generated"] = bool(appeal.get("appeal_text"))

            await send_pipeline_event(
                manager,
                topic="denial_ai",
                action="completed",
                claim_id=claim_id,
                stage="DENIAL_AI",
                status="COMPLETED_WITH_FALLBACK",
                progress=82,
                current_stage="DENIAL_AI",
                current_agent="DENIAL_AI",
                active_step="denial_ai",
                pipeline_state="DENIAL_AI_COMPLETED",
                pipeline_status="COMPLETED_WITH_FALLBACK",
                message="Denial AI fallback analysis completed",
                claim=claim,
                extra=clean_nan({
                    "agent": "DENIAL_AI",
                    "analysis": fallback,
                    "appeal": appeal,
                    "duration_seconds": duration_seconds,
                }),
            )

            return {
                "claim": clean_nan(claim),
                "denial_ai": fallback,
                "appeal": appeal,
                "pipeline": clean_nan(claim.get("pipeline", {})),
                "stage": "denial_ai_completed_with_fallback",
                "status": "COMPLETED_WITH_FALLBACK",
                "duration_seconds": duration_seconds,
            }

    def auto_fix(
        self,
        claim: Dict[str, Any],
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Apply safe auto-fixes suggested by denial analysis.
        """

        corrected = clean_nan({**(claim or {})})
        services = [
            dict(item)
            for item in corrected.get("services", [])
            if isinstance(item, dict)
        ]

        for suggestion in analysis.get("modifier_suggestions", []) or []:
            if not isinstance(suggestion, dict):
                continue

            modifier = suggestion.get("modifier") or suggestion.get("suggested")

            if modifier and services:
                services[0]["modifier"] = (
                    str(modifier)
                    .split(",")[0]
                    .strip()
                    .replace("modifier", "")
                    .strip()[:2]
                )

        for suggestion in analysis.get("icd_suggestions", []) or []:
            if not isinstance(suggestion, dict):
                continue

            suggested = suggestion.get("code") or suggestion.get("suggested")

            if suggested and isinstance(suggested, str) and suggested[:1].isalpha():
                corrected["icd_codes"] = [suggested.upper()]
                corrected["diagnosis_codes"] = [suggested.upper()]

        corrected["services"] = services
        corrected["denial_ai_auto_fixed"] = True
        corrected["resubmission_strategy"] = analysis.get("resubmission_strategy")

        return clean_nan(corrected)

    def _fallback_analysis(
        self,
        claim: Dict[str, Any],
        classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        suggestions = self.suggester.suggest(claim, classification)

        return clean_nan({
            **classification,
            "root_cause": classification.get("root_cause"),
            "suggested_corrections": suggestions.get("suggested_corrections", []),
            "modifier_suggestions": suggestions.get("modifier_suggestions", []),
            "icd_suggestions": suggestions.get("icd_suggestions", []),
            "cpt_corrections": [],
            "documentation_gaps": classification.get("focus", []),
            "payer_rule_findings": [
                f"Review payer policy for {classification.get('category')}"
            ],
            "medical_necessity": (
                "Review diagnosis support and documentation for billed CPTs"
            ),
            "resubmission_strategy": (
                "Correct claim data, attach supporting documentation, "
                "and resubmit as corrected claim"
            ),
            "denial_prevention_tips": suggestions.get("prevention_tips", []),
            "retry_probability": classification.get("retry_probability", 0.45),
        })

    async def _llm_analysis(
        self,
        claim: Dict[str, Any],
        classification: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        compact_claim = self._compact_claim_for_llm(claim)

        prompt = f"""
You are a healthcare RCM denial specialist. Analyze this denied claim.

Claim:
{json.dumps(compact_claim, indent=2, default=str)}

Denial classification:
{json.dumps(classification, indent=2, default=str)}

Return structured JSON with:
root_cause, suggested_corrections, cpt_corrections, icd_suggestions,
modifier_suggestions, payer_rule_findings, documentation_gaps,
medical_necessity, appeal_summary, denial_prevention_tips,
resubmission_strategy, retry_probability.
"""

        try:
            response = await invoke_llm(prompt, expect_json=True)

            if isinstance(response, dict):
                if response.get("error") == "Invalid JSON" and response.get("raw"):
                    cleaned_response = clean_llm_json_response(response.get("raw"))
                    parsed_response = json.loads(cleaned_response)

                    if isinstance(parsed_response, dict):
                        return clean_nan(parsed_response)

                return clean_nan(response)

            if isinstance(response, str):
                cleaned_response = clean_llm_json_response(response)
                parsed_response = json.loads(cleaned_response)

                if isinstance(parsed_response, dict):
                    return clean_nan(parsed_response)

            return {}

        except Exception as exc:
            return clean_nan({
                "llm_status": "fallback",
                "llm_error": str(exc),
                "appeal_summary": (
                    f"Claim {claim.get('claim_id')} was denied for "
                    f"{fallback.get('root_cause')}. Corrected claim data and "
                    "supporting documentation should be reviewed for resubmission."
                ),
            })

    def _compact_claim_for_llm(self, claim: Dict[str, Any]) -> Dict[str, Any]:
        """
        Avoid sending huge generated artifacts, signed URLs, raw OCR blocks,
        and nested pipeline state to LLM.
        """

        claim = claim or {}

        return clean_nan({
            "claim_id": claim.get("claim_id"),
            "patient": claim.get("patient"),
            "provider": claim.get("provider"),
            "payer": claim.get("payer"),
            "insurance": claim.get("insurance"),
            "services": claim.get("services"),
            "icd_codes": claim.get("icd_codes") or claim.get("diagnosis_codes"),
            "cpt_codes": claim.get("cpt_codes"),
            "total_charge": claim.get("total_charge"),
            "validation": claim.get("validation"),
            "validation_status": claim.get("validation_status"),
            "validation_score": claim.get("validation_score"),
            "risk_score": claim.get("risk_score"),
            "compliance": claim.get("compliance"),
            "compliance_status": claim.get("compliance_status"),
            "submission": {
                "submission_id": (
                    claim.get("submission", {}).get("submission_id")
                    if isinstance(claim.get("submission"), dict)
                    else claim.get("submission_id")
                ),
                "status": (
                    claim.get("submission", {}).get("status")
                    if isinstance(claim.get("submission"), dict)
                    else claim.get("status")
                ),
                "denial_code": (
                    claim.get("submission", {}).get("denial_code")
                    if isinstance(claim.get("submission"), dict)
                    else claim.get("denial_code")
                ),
                "reason": (
                    claim.get("submission", {}).get("reason")
                    if isinstance(claim.get("submission"), dict)
                    else claim.get("denial_reason")
                ),
            },
            "denial": claim.get("denial"),
            "denial_reason": claim.get("denial_reason"),
            "denial_code": claim.get("denial_code"),
        })
