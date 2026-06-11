
# import time
# import uuid
# from datetime import datetime

# from app.agents.base.base_agent import BaseAgent
# from app.websocket.manager import manager
# from app.rcm.clearinghouse_client import send_to_clearinghouse
# from app.intake.db_service import (
#     update_record_status,
#     get_record_by_id,
#     save_record,
# )

# from app.services.cms1500_service import generate_outputs
# from app.services.ub04_service import generate_ub04_form
# from app.services.edi_service import generate_ub04_edi
# from app.services.analytics_service import update_metrics
# from app.db.database import SessionLocal
# from app.services.clearinghouse_orchestration_service import (
#     ClearinghouseOrchestrationService,
#     PENDING_CLEARINGHOUSE,
# )


# class SubmissionAgent(BaseAgent):

#     async def run(self, claim):

#         start_time = time.time()

#         claim = claim or {}

#         claim_id = claim.get("claim_id", "UNKNOWN")

#         trace_id = await self.log_start(
#             "SubmissionAgent",
#             claim_id,
#         )

#         await manager.send_event(
#             "submission",
#             "running",
#             {
#                 "claim_id": claim_id,
#             },
#         )

#         try:

#             # ---------------------------------------------------
#             # Validate Claim
#             # ---------------------------------------------------

#             await self.log_step(
#                 "SubmissionAgent",
#                 "Validating claim before submission",
#                 {
#                     "service_count": len(
#                         claim.get("services", [])
#                     )
#                 },
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             if not claim.get("services"):

#                 raise ValueError(
#                     "No services to submit"
#                 )

#             # ---------------------------------------------------
#             # Generate Submission ID
#             # ---------------------------------------------------

#             submission_id = (
#                 f"SUB-{uuid.uuid4().hex[:8]}"
#             )

#             claim["submission_id"] = submission_id

#             encounter_type = (
#                 claim.get(
#                     "encounter_type",
#                     "outpatient"
#                 ).lower()
#             )

#             await self.log_step(
#                 "SubmissionAgent",
#                 "Generated submission metadata",
#                 {
#                     "submission_id": submission_id,
#                     "encounter_type": encounter_type,
#                 },
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             # ---------------------------------------------------
#             # Generate Claim Artifacts
#             # ---------------------------------------------------

#             generated_artifacts = {}

#             # ---------------------------------------
#             # CMS1500
#             # ---------------------------------------

#             if encounter_type == "outpatient":

#                 await manager.send_event(
#                     "submission",
#                     "generating_cms1500",
#                     {
#                         "claim_id": claim_id,
#                         "submission_id": submission_id,
#                     },
#                 )

#                 await self.log_step(
#                     "SubmissionAgent",
#                     "Generating CMS1500 + 837P",
#                     {},
#                     trace_id=trace_id,
#                     claim_id=claim_id,
#                 )

#                 generated_artifacts = generate_outputs(
#                     claim_data=claim,
#                     patient_id=claim_id,
#                     sessionid=submission_id,
#                     mode="both",
#                 )

#                 cms1500_result = generated_artifacts.get("form") or {}
#                 if cms1500_result.get("status") == "PARTIAL_SUCCESS":
#                     await manager.send_event(
#                         "submission",
#                         "FAILED",
#                         {
#                             "claim_id": claim_id,
#                             "agent": "SUBMISSION",
#                             "stage": "CMS1500",
#                             "status": "FAILED",
#                             "reason": cms1500_result.get("reason") or "Template missing",
#                             "warnings": [cms1500_result.get("message") or "CMS template unavailable"],
#                             "submission_id": submission_id,
#                         },
#                     )

#             # ---------------------------------------
#             # UB04
#             # ---------------------------------------

#             else:

#                 await manager.send_event(
#                     "submission",
#                     "generating_ub04",
#                     {
#                         "claim_id": claim_id,
#                         "submission_id": submission_id,
#                     },
#                 )

#                 await self.log_step(
#                     "SubmissionAgent",
#                     "Generating UB04 + 837I",
#                     {},
#                     trace_id=trace_id,
#                     claim_id=claim_id,
#                 )

#                 pdf_output = generate_ub04_form(
#                     claim_data=claim,
#                     patient_id=claim_id,
#                     sessionid=submission_id,
#                 )

#                 edi_output = generate_ub04_edi(
#                     claim_data=claim,
#                     patient_id=claim_id,
#                     sessionid=submission_id,
#                 )

#                 generated_artifacts = {
#                     "pdf": pdf_output,
#                     "edi": edi_output,
#                 }

#             await self.log_step(
#                 "SubmissionAgent",
#                 "Claim artifacts generated",
#                 generated_artifacts,
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             # ---------------------------------------------------
#             # Generate EDI Payload
#             # ---------------------------------------------------

#             edi_payload = {
#                 "claim_id": claim_id,
#                 "submission_id": submission_id,
#                 "encounter_type": encounter_type,
#                 "artifacts": generated_artifacts,
#                 "timestamp": datetime.utcnow().isoformat(),
#             }

#             await self.log_step(
#                 "SubmissionAgent",
#                 "EDI payload generated",
#                 edi_payload,
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             # ---------------------------------------------------
#             # Send To Clearinghouse
#             # ---------------------------------------------------

#             await manager.send_event(
#                 "submission",
#                 "sending_to_clearinghouse",
#                 {
#                     "claim_id": claim_id,
#                     "submission_id": submission_id,
#                 },
#             )

#             ch_response = send_to_clearinghouse(
#                 edi_payload
#             )

#             await self.log_step(
#                 "SubmissionAgent",
#                 "Clearinghouse response received",
#                 ch_response,
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             # ---------------------------------------------------
#             # Compliance Hook
#             # ---------------------------------------------------

#             claim["compliance"] = {
#                 "checked": True,
#                 "status": "COMPLIANT",
#                 "checked_at": datetime.utcnow().isoformat(),
#             }

#             await self.log_step(
#                 "SubmissionAgent",
#                 "Compliance validation completed",
#                 claim["compliance"],
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             # ---------------------------------------------------
#             # Learning Hook
#             # ---------------------------------------------------

#             claim["learning"] = {
#                 "feedback_captured": True,
#                 "confidence_score": claim.get(
#                     "confidence",
#                     0.95,
#                 ),
#                 "updated_at": datetime.utcnow().isoformat(),
#             }

#             await self.log_step(
#                 "SubmissionAgent",
#                 "Learning feedback captured",
#                 claim["learning"],
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             # ---------------------------------------------------
#             # Analytics Hook
#             # ---------------------------------------------------

#             claim["analytics"] = {
#                 "submitted": True,
#                 "submission_time": datetime.utcnow().isoformat(),
#             }

#             await self.log_step(
#                 "SubmissionAgent",
#                 "Analytics updated",
#                 claim["analytics"],
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             # ---------------------------------------------------
#             # Update DB Status
#             # ---------------------------------------------------

#             update_record_status(
#                 claim_id,
#                 PENDING_CLEARINGHOUSE,
#             )

#             await self.log_step(
#                 "SubmissionAgent",
#                 "Updated claim status in DB",
#                 {
#                     "status": PENDING_CLEARINGHOUSE
#                 },
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             # ---------------------------------------------------
#             # Update Claim
#             # ---------------------------------------------------

#             claim["status"] = PENDING_CLEARINGHOUSE

#             claim["submission"] = {
#                 **ch_response,
#                 "status": PENDING_CLEARINGHOUSE,
#                 "review_required": True,
#             }

#             claim["generated_artifacts"] = (
#                 generated_artifacts
#             )

#             # ---------------------------------------------------
#             # Persist Record
#             # ---------------------------------------------------

#             record = get_record_by_id(claim_id)

#             if record:

#                 record.setdefault(
#                     "pipeline",
#                     {"steps": {}},
#                 )

#                 record["pipeline"].setdefault(
#                     "steps",
#                     {},
#                 )

#                 record["pipeline"]["steps"][
#                     "submitted"
#                 ] = True

#                 record["pipeline"]["steps"][
#                     "compliance"
#                 ] = True

#                 record["pipeline"]["steps"][
#                     "analytics"
#                 ] = True

#                 record["status"] = PENDING_CLEARINGHOUSE

#                 record["submission_id"] = (
#                     submission_id
#                 )

#                 record["clearinghouse"] = (
#                     ch_response
#                 )

#                 record["generated_artifacts"] = (
#                     generated_artifacts
#                 )

#                 record["submitted_at"] = (
#                     datetime.utcnow().isoformat()
#                 )

#                 record["approval_required"] = True

#                 save_record(record)

#                 await self.log_step(
#                     "SubmissionAgent",
#                     "Persisted submission details",
#                     {
#                         "submission_id": submission_id,
#                         "approval_required": True,
#                     },
#                     trace_id=trace_id,
#                     claim_id=claim_id,
#                 )

#             # ---------------------------------------------------
#             # Final WebSocket Event
#             # ---------------------------------------------------

#             db = SessionLocal()
#             try:
#                 ClearinghouseOrchestrationService(db).queue_after_submission(
#                     claim_id=claim_id,
#                     claim=claim,
#                     clearinghouse_response=claim["submission"],
#                     artifacts=generated_artifacts,
#                     reviewer="SubmissionAgent",
#                 )
#             finally:
#                 db.close()

#             claim["status"] = "WAITING_FOR_APPROVAL"
#             claim["pipeline_state"] = "WAITING_FOR_APPROVAL"
#             claim["current_stage"] = "CLEARINGHOUSE"
#             claim["current_agent"] = "CLEARINGHOUSE"
#             claim["active_step"] = "clearinghouse"
#             claim["progress"] = 70

#             await manager.broadcast({
#                 "event": "clearinghouse_queued",
#                 "type": "clearinghouse_queued",
#                 "claim_id": claim_id,
#                 "submission_id": submission_id,
#                 "status": "WAITING_FOR_APPROVAL",
#                 "pipeline_state": "WAITING_FOR_APPROVAL",
#                 "current_stage": "CLEARINGHOUSE",
#                 "current_agent": "CLEARINGHOUSE",
#                 "active_step": "clearinghouse",
#                 "progress": 70,
#                 "processing_mode": claim.get("processing_mode") or claim.get("clearinghouse_processing_mode") or "MANUAL",
#                 "claim": claim,
#                 "pipeline": {
#                     "steps": {
#                         "submitted": True,
#                         "clearinghouse_queued": True,
#                     }
#                 },
#             })

#             processing_mode = str(claim.get("processing_mode") or claim.get("clearinghouse_processing_mode") or "MANUAL").upper()
#             if processing_mode == "AUTO":
#                 db = SessionLocal()
#                 try:
#                     await ClearinghouseOrchestrationService(db).auto_accept_if_qualified(
#                         claim_id,
#                         reviewer="SYSTEM_AUTO",
#                     )
#                 finally:
#                     db.close()

#             await manager.send_event(
#                 "submission",
#                 "completed",
#                 {
#                     "claim_id": claim_id,
#                     "submission_id": submission_id,
#                     "status": "WAITING_FOR_APPROVAL",
#                     "pipeline_state": "WAITING_FOR_APPROVAL",
#                     "current_stage": "CLEARINGHOUSE",
#                     "current_agent": "CLEARINGHOUSE",
#                     "active_step": "clearinghouse",
#                     "progress": 70,
#                     "artifacts": generated_artifacts,
#                     "trace_id": trace_id,
#                 },
#             )
#             update_metrics(
#                 event_type="submission_completed",
#                 claim_id=claim_id,
#                 agent="SUBMISSION",
#                 payer=claim.get("payer"),
#                 risk_score=claim.get("risk_score", 0),
#                 latency=time.time() - start_time,
#                 status="COMPLETED",
#             )

#             # ---------------------------------------------------
#             # End Logs
#             # ---------------------------------------------------

#             await self.log_end(
#                 "SubmissionAgent",
#                 PENDING_CLEARINGHOUSE,
#                 time.time() - start_time,
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             return {
#                 "claim": claim,
#                 "pipeline": {
#                     "steps": {
#                         "submitted": True,
#                         "clearinghouse_queued": True,
#                         "compliance": True,
#                         "analytics": True,
#                     }
#                 },
#                 "stage": "WAITING_FOR_APPROVAL",
#                 "trace_id": trace_id,
#             }

#         except Exception as error:

#             await self.log_error(
#                 "SubmissionAgent",
#                 error,
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             await manager.send_event(
#                 "submission",
#                 "failed",
#                 {
#                     "claim_id": claim_id,
#                     "error": str(error),
#                     "trace_id": trace_id,
#                 },
#             )
#             update_metrics(
#                 event_type="submission_failed",
#                 claim_id=claim_id,
#                 agent="SUBMISSION",
#                 payer=claim.get("payer"),
#                 risk_score=claim.get("risk_score", 0),
#                 latency=time.time() - start_time,
#                 status="FAILED",
#             )

#             await self.log_end(
#                 "SubmissionAgent",
#                 "FAILED",
#                 time.time() - start_time,
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             raise


import time
import uuid
import json
from datetime import datetime

from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager
from app.utils.security import mask_sensitive_payload
from app.rcm.clearinghouse_client import send_to_clearinghouse
from app.intake.db_service import (
    clean_nan,
    update_record_status,
    get_record_by_id,
    save_record,
)


from app.services.cms1500_service import generate_outputs
from app.services.ub04_service import generate_ub04_form
from app.services.edi_service import generate_ub04_edi
from app.services.analytics_service import update_metrics
from app.db.database import SessionLocal
from app.utils.pipeline_events import (
    apply_pipeline_patch,
    send_pipeline_event,
)
from app.services.clearinghouse_orchestration_service import (
    ClearinghouseOrchestrationService,
    PENDING_CLEARINGHOUSE,
)


def get_or_create_submission_id(claim):
    claim = claim or {}
    submission = claim.get("submission")
    if not isinstance(submission, dict):
        submission = {}
        claim["submission"] = submission

    candidates = [
        claim.get("submission_id"),
        submission.get("submission_id"),
        (claim.get("submission_payload") or {}).get("submission_id")
        if isinstance(claim.get("submission_payload"), dict)
        else None,
    ]

    for candidate in candidates:
        if candidate and str(candidate).startswith("SUB-"):
            submission_id = str(candidate)
            claim["submission_id"] = submission_id
            submission["submission_id"] = submission_id
            if isinstance(claim.get("submission_payload"), dict):
                claim["submission_payload"]["submission_id"] = submission_id
            return submission_id

    submission_id = f"SUB-{uuid.uuid4().hex[:8]}"
    claim["submission_id"] = submission_id
    submission["submission_id"] = submission_id
    return submission_id



class SubmissionAgent(BaseAgent):
    """
    SubmissionAgent prepares a validated and compliant claim for clearinghouse review.

    Responsibilities:
    - Validate that the claim is ready for submission
    - Generate submission ID
    - Generate CMS-1500/837P or UB-04/837I artifacts
    - Send/queue claim to clearinghouse
    - Persist submission state
    - Notify frontend through WebSocket
    """

    async def run(self, claim):
        start_time = time.time()
        started_at = self._utc_now()
        claim = claim or {}

        claim_id = claim.get("claim_id", "UNKNOWN")
        trace_id = await self.log_start("SubmissionAgent", claim_id)

        print("\n" + "=" * 80)
        print("📤 [SubmissionAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"🔎 Trace ID: {trace_id}")
        print(f"📥 Incoming claim keys: {list(claim.keys())}")
        print("=" * 80)

        await send_pipeline_event(
            manager,
            topic="submission",
            action="running",
            claim_id=claim_id,
            stage="SUBMISSION",
            status="RUNNING",
            progress=65,
            current_stage="SUBMISSION",
            current_agent="SubmissionAgent",
            active_step="submission",
            pipeline_state="SUBMISSION_RUNNING",
            pipeline_status="RUNNING",
            message="Submission Agent started",
            extra={"trace_id": trace_id},
        )

        try:
            # ---------------------------------------------------
            # Step 1: Pre-submission validation
            # ---------------------------------------------------
            print("➡️ [1] Running pre-submission checks...")

            required_errors = self._pre_submission_errors(claim)

            await self.log_step(
                "SubmissionAgent",
                "Validating claim before submission",
                {
                    "service_count": len(claim.get("services", []) or []),
                    "errors": required_errors,
                },
                trace_id=trace_id,
                claim_id=claim_id,
            )

            if required_errors:
                raise ValueError("; ".join(required_errors))

            print("✅ Pre-submission checks passed")

            # ---------------------------------------------------
            # Step 2: Generate submission ID
            # ---------------------------------------------------
            print("➡️ [2] Resolving submission ID...")

            submission_id = get_or_create_submission_id(claim)

            encounter_type = str(
                claim.get("encounter_type") or "outpatient"
            ).lower()

            print(f"✅ Submission ID: {submission_id}")
            print(f"✅ Encounter type: {encounter_type}")

            await self.log_step(
                "SubmissionAgent",
                "Generated submission metadata",
                {
                    "submission_id": submission_id,
                    "encounter_type": encounter_type,
                },
                trace_id=trace_id,
                claim_id=claim_id,
            )

            # ---------------------------------------------------
            # Step 3: Generate claim artifacts
            # ---------------------------------------------------
            print("➡️ [3] Generating claim artifacts...")

            generated_artifacts = {}

            if encounter_type == "outpatient":
                print("📄 Generating CMS-1500 + 837P")

                await manager.send_event(
                    "submission",
                    "generating_cms1500",
                    {
                        "claim_id": claim_id,
                        "submission_id": submission_id,
                        "message": "Generating CMS-1500 and 837P artifacts",
                    },
                )

                await self.log_step(
                    "SubmissionAgent",
                    "Generating CMS1500 + 837P",
                    {},
                    trace_id=trace_id,
                    claim_id=claim_id,
                )

                generated_artifacts = generate_outputs(
                    claim_data=claim,
                    patient_id=claim_id,
                    sessionid=submission_id,
                    mode="both",
                )

                cms1500_result = generated_artifacts.get("form") or {}

                if cms1500_result.get("status") == "PARTIAL_SUCCESS":
                    print("⚠️ CMS-1500 partial success")
                    print(f"⚠️ Reason: {cms1500_result.get('reason')}")

                    await manager.send_event(
                        "submission",
                        "artifact_warning",
                        {
                            "claim_id": claim_id,
                            "submission_id": submission_id,
                            "stage": "CMS1500",
                            "reason": cms1500_result.get("reason") or "Template missing",
                            "warnings": [
                                cms1500_result.get("message")
                                or "CMS template unavailable"
                            ],
                        },
                    )

            else:
                print("📄 Generating UB-04 + 837I")

                await manager.send_event(
                    "submission",
                    "generating_ub04",
                    {
                        "claim_id": claim_id,
                        "submission_id": submission_id,
                        "message": "Generating UB-04 and 837I artifacts",
                    },
                )

                await self.log_step(
                    "SubmissionAgent",
                    "Generating UB04 + 837I",
                    {},
                    trace_id=trace_id,
                    claim_id=claim_id,
                )

                pdf_output = generate_ub04_form(
                    claim_data=claim,
                    patient_id=claim_id,
                    sessionid=submission_id,
                )

                edi_output = generate_ub04_edi(
                    claim_data=claim,
                    patient_id=claim_id,
                    sessionid=submission_id,
                )

                generated_artifacts = {
                    "pdf": pdf_output,
                    "edi": edi_output,
                }

            print("✅ Claim artifacts generated")
            print(json.dumps(mask_sensitive_payload(generated_artifacts), indent=2, default=str))

            await self.log_step(
                "SubmissionAgent",
                "Claim artifacts generated",
                mask_sensitive_payload(generated_artifacts),
                trace_id=trace_id,
                claim_id=claim_id,
            )

            # ---------------------------------------------------
            # Step 4: Build EDI payload
            # ---------------------------------------------------
            print("➡️ [4] Building EDI payload...")

            edi_payload = {
                "claim_id": claim_id,
                "submission_id": submission_id,
                "encounter_type": encounter_type,
                "artifacts": generated_artifacts,
                "timestamp": datetime.utcnow().isoformat(),
            }

            print("✅ EDI payload prepared")

            await self.log_step(
                "SubmissionAgent",
                "EDI payload generated",
                mask_sensitive_payload(edi_payload),
                trace_id=trace_id,
                claim_id=claim_id,
            )

            # ---------------------------------------------------
            # Step 5: Send to clearinghouse
            # ---------------------------------------------------
            print("➡️ [5] Sending claim to clearinghouse...")

            await manager.send_event(
                "submission",
                "sending_to_clearinghouse",
                {
                    "claim_id": claim_id,
                    "submission_id": submission_id,
                    "message": "Sending claim package to clearinghouse",
                },
            )

            ch_response = send_to_clearinghouse(edi_payload)

            print("✅ Clearinghouse response received")
            print(json.dumps(mask_sensitive_payload(ch_response), indent=2, default=str))

            await self.log_step(
                "SubmissionAgent",
                "Clearinghouse response received",
                mask_sensitive_payload(ch_response),
                trace_id=trace_id,
                claim_id=claim_id,
            )

            # ---------------------------------------------------
            # Step 6: Snapshot prior agent results
            # Do not overwrite real Compliance/Learning/Analytics.
            # ---------------------------------------------------
            print("➡️ [6] Saving submission snapshots...")

            claim["submission_validation_snapshot"] = {
                "validation_status": claim.get("validation_status"),
                "validation_score": claim.get("validation_score"),
                "risk_score": claim.get("risk_score"),
                "captured_at": datetime.utcnow().isoformat(),
            }

            claim["submission_compliance_snapshot"] = {
                "compliance_status": claim.get("compliance_status"),
                "compliance_failed": claim.get("compliance_failed"),
                "hard_reject": claim.get("hard_reject"),
                "hitl_required": claim.get("hitl_required"),
                "captured_at": datetime.utcnow().isoformat(),
            }

            print("✅ Submission snapshots saved")

            # ---------------------------------------------------
            # Step 7: Update DB status
            # ---------------------------------------------------
            print("➡️ [7] Updating DB status...")

            update_record_status(
                claim_id,
                PENDING_CLEARINGHOUSE,
            )

            print(f"✅ DB status updated: {PENDING_CLEARINGHOUSE}")

            await self.log_step(
                "SubmissionAgent",
                "Updated claim status in DB",
                {
                    "status": PENDING_CLEARINGHOUSE
                },
                trace_id=trace_id,
                claim_id=claim_id,
            )

            # ---------------------------------------------------
            # Step 8: Update claim object
            # ---------------------------------------------------
            print("➡️ [8] Updating claim submission state...")

            claim["status"] = PENDING_CLEARINGHOUSE
            claim["generated_artifacts"] = generated_artifacts

            claim["submission"] = {
                **(ch_response or {}),
                "submission_id": submission_id,
                "status": PENDING_CLEARINGHOUSE,
                "review_required": True,
                "encounter_type": encounter_type,
                "submitted_at": datetime.utcnow().isoformat(),
            }

            print("✅ Claim submission state updated")

            # ---------------------------------------------------
            # Step 9: Persist record
            # ---------------------------------------------------
            print("➡️ [9] Persisting submission details...")

            record = get_record_by_id(claim_id)

            if record:
                record.setdefault("pipeline", {"steps": {}})
                record["pipeline"].setdefault("steps", {})

                record["pipeline"]["steps"]["submitted"] = True
                record["pipeline"]["steps"]["clearinghouse_queued"] = True

                record["status"] = PENDING_CLEARINGHOUSE
                record["submission_id"] = submission_id
                record["clearinghouse"] = ch_response
                record["generated_artifacts"] = generated_artifacts
                record["submitted_at"] = datetime.utcnow().isoformat()
                record["approval_required"] = True

                save_record(record)

                print("✅ Submission details persisted")

                await self.log_step(
                    "SubmissionAgent",
                    "Persisted submission details",
                    {
                        "submission_id": submission_id,
                        "approval_required": True,
                    },
                    trace_id=trace_id,
                    claim_id=claim_id,
                )
            else:
                print("⚠️ No DB record found to persist submission details")

            # ---------------------------------------------------
            # Step 10: Queue clearinghouse review
            # ---------------------------------------------------
            print("➡️ [10] Queueing clearinghouse review...")

            db = SessionLocal()
            try:
                ClearinghouseOrchestrationService(db).queue_after_submission(
                    claim_id=claim_id,
                    claim=claim,
                    clearinghouse_response=claim["submission"],
                    artifacts=generated_artifacts,
                    reviewer="SubmissionAgent",
                )
                print("✅ Clearinghouse review queued")
            finally:
                db.close()

            # ---------------------------------------------------
            # Step 11: Update pipeline state
            # ---------------------------------------------------
            print("➡️ [11] Updating pipeline state to WAITING_FOR_APPROVAL...")

            claim["status"] = "WAITING_FOR_APPROVAL"
            claim["pipeline_state"] = "WAITING_FOR_APPROVAL"
            claim["current_stage"] = "CLEARINGHOUSE"
            claim["current_agent"] = "CLEARINGHOUSE"
            claim["active_step"] = "clearinghouse"
            claim["progress"] = 70

            processing_mode = str(
                claim.get("clearinghouse_processing_mode")
                or claim.get("processing_mode")
                or "MANUAL"
            ).upper()
            if processing_mode not in {"AUTO", "MANUAL"}:
                processing_mode = "MANUAL"
            claim["processing_mode"] = processing_mode
            claim["clearinghouse_processing_mode"] = processing_mode

            duration_seconds = round(time.time() - start_time, 2)

            submission_payload = {
                "claim_id": claim_id,
                "agent": "SubmissionAgent",
                "submission_id": submission_id,
                "status": "WAITING_FOR_APPROVAL",
                "pipeline_state": "WAITING_FOR_APPROVAL",
                "pipeline_status": "WAITING_FOR_APPROVAL",
                "current_stage": "CLEARINGHOUSE",
                "current_agent": "CLEARINGHOUSE",
                "active_step": "clearinghouse",
                "progress": 70,
                "encounter_type": encounter_type,
                "clearinghouse_status": PENDING_CLEARINGHOUSE,
                "review_required": True,
                "approval_required": True,
                "pipeline_paused": True,
                "processing_mode": processing_mode,
                "artifacts": generated_artifacts,
                "duration_seconds": duration_seconds,
                "next_agent": "Clearinghouse Review",
                "trace_id": trace_id,
            }

            claim["submission_duration_seconds"] = duration_seconds

# Store only a compact submission summary on claim.
# Do not store full submission_payload inside claim, because claim is also sent in events
# and saved into DB payload later.
            claim["submission_summary"] = {
                "submission_id": submission_id,
                "status": "WAITING_FOR_APPROVAL",
                "pipeline_state": "WAITING_FOR_APPROVAL",
                "pipeline_status": "WAITING_FOR_APPROVAL",
                "current_stage": "CLEARINGHOUSE",
                "clearinghouse_status": PENDING_CLEARINGHOUSE,
                "review_required": True,
                "approval_required": True,
                "pipeline_paused": True,
                "processing_mode": processing_mode,
                "duration_seconds": duration_seconds,
                "trace_id": trace_id,
            }
            claim["submission_payload"] = submission_payload

            agent_detail = self.build_agent_detail(
                "submission",
                status="COMPLETED",
                active_step="Claim submitted and queued for clearinghouse review",
                message="Claim submitted to clearinghouse review queue",
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=True,
                output=submission_payload,
                next_agent="Clearinghouse Review",
            )
            self.apply_agent_detail(
                claim,
                "submission",
                agent_detail,
                step_completed=True,
                result_status="COMPLETED",
            )
            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage="CLEARINGHOUSE",
                status="WAITING_FOR_APPROVAL",
                progress=70,
                current_stage="CLEARINGHOUSE",
                current_agent="CLEARINGHOUSE",
                active_step="clearinghouse",
                pipeline_state="WAITING_FOR_APPROVAL",
                pipeline_status="WAITING_FOR_APPROVAL",
                review_required=True,
                approval_required=True,
                pipeline_paused=True,
                message="Waiting for clearinghouse approval",
            )

            if record:
                record["claim"] = claim
                record["agents"] = claim.get("agents", {})
                record.setdefault("pipeline", {"steps": {}})
                record["pipeline"].setdefault("steps", {})
                record["pipeline"]["steps"].update(
                    claim.get("pipeline", {}).get("steps", {})
                )
                record["pipeline_state"] = claim.get("pipeline_state")
                record["pipeline_status"] = claim.get("pipeline_status")
                record["current_stage"] = claim.get("current_stage")
                record["current_agent"] = claim.get("current_agent")
                record["active_step"] = claim.get("active_step")
                record["progress"] = claim.get("progress")
                save_record(record)

            print("✅ Submission payload prepared")
            print(json.dumps(mask_sensitive_payload(submission_payload), indent=2, default=str))

            # ---------------------------------------------------
            # Step 12: Broadcast clearinghouse queued
            # ---------------------------------------------------
            print("➡️ [12] Broadcasting clearinghouse_queued event...")

            await manager.broadcast(clean_nan({
                "event": "clearinghouse_queued",
                "type": "clearinghouse_queued",
                **submission_payload,
                "agent_detail": agent_detail,
                "claim": {
                    "claim_id": claim_id,
                    "patient": claim.get("patient"),
                    "provider": claim.get("provider"),
                    "payer": claim.get("payer"),
                    "insurance": claim.get("insurance"),
                    "services": claim.get("services"),
                    "diagnosis_codes": claim.get("diagnosis_codes") or claim.get("icd_codes"),
                    "icd_codes": claim.get("icd_codes") or claim.get("diagnosis_codes"),
                    "cpt_codes": claim.get("cpt_codes"),
                    "total_charge": claim.get("total_charge"),
                    "status": "WAITING_FOR_APPROVAL",
                    "pipeline_state": "WAITING_FOR_APPROVAL",
                    "current_stage": "CLEARINGHOUSE",
                    "current_agent": "CLEARINGHOUSE",
                    "active_step": "clearinghouse",
                    "progress": 70,
                    "submission_id": submission_id,
                    "generated_artifacts": generated_artifacts,
                },
                "pipeline": claim.get("pipeline"),
            }))

            print("✅ clearinghouse_queued event broadcasted")

            # ---------------------------------------------------
            # Step 13: Auto accept if configured
            # ---------------------------------------------------
            if processing_mode == "AUTO":
                print("➡️ [13] AUTO mode detected. Checking auto-accept...")

                db = SessionLocal()
                try:
                    await ClearinghouseOrchestrationService(db).auto_accept_if_qualified(
                        claim_id,
                        reviewer="SYSTEM_AUTO",
                    )
                    print("✅ Auto-accept check completed")
                finally:
                    db.close()
            else:
                print("➡️ [13] MANUAL mode. Waiting for clearinghouse approval.")

            # ---------------------------------------------------
            # Step 14: Final clearinghouse wait event
            # ---------------------------------------------------
            print("➡️ [14] Sending final clearinghouse wait event...")

            await manager.broadcast(clean_nan({
                "type": "agent_update",
                "event": "agent_update",
                "claim_id": claim_id,
                "submission_id": submission_id,
                "stage": "CLEARINGHOUSE",
                "status": "WAITING_FOR_APPROVAL",
                "progress": 70,
                "current_stage": "CLEARINGHOUSE",
                "current_agent": "CLEARINGHOUSE",
                "active_step": "clearinghouse",
                "pipeline_state": "WAITING_FOR_APPROVAL",
                "pipeline_status": "WAITING_FOR_APPROVAL",
                "clearinghouse_status": PENDING_CLEARINGHOUSE,
                "review_required": True,
                "approval_required": True,
                "processing_mode": processing_mode,
                "agent_detail": agent_detail,
                "claim": {
                    **claim,
                    "status": "WAITING_FOR_APPROVAL",
                    "pipeline_state": "WAITING_FOR_APPROVAL",
                    "pipeline_status": "WAITING_FOR_APPROVAL",
                    "current_stage": "CLEARINGHOUSE",
                    "current_agent": "CLEARINGHOUSE",
                    "active_step": "clearinghouse",
                    "progress": 70,
                    "clearinghouse_status": PENDING_CLEARINGHOUSE,
                    "review_required": True,
                    "approval_required": True,
                },
                "pipeline": claim.get("pipeline"),
                "timestamp": datetime.utcnow().isoformat(),
            }))

            print("✅ Final clearinghouse wait event sent")

            await manager.send_event(
                "submission",
                "completed",
                self.build_agent_event_payload(
                    "submission",
                    claim_id,
                    agent_detail,
                    existing_payload=submission_payload,
                    result_status="WAITING_FOR_APPROVAL",
                ),
            )

            # ---------------------------------------------------
            # Step 15: Metrics
            # ---------------------------------------------------
            print("➡️ [15] Updating submission metrics...")

            update_metrics(
                event_type="submission_completed",
                claim_id=claim_id,
                agent="SUBMISSION",
                payer=claim.get("payer"),
                risk_score=claim.get("risk_score", 0),
                latency=duration_seconds,
                status="COMPLETED",
            )

            print("✅ Submission metrics updated")

            # ---------------------------------------------------
            # Step 16: End logs
            # ---------------------------------------------------
            await self.log_end(
                "SubmissionAgent",
                PENDING_CLEARINGHOUSE,
                duration_seconds,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            print("✅ [SubmissionAgent] COMPLETED")
            print(f"⏱️ Submission duration: {duration_seconds}s")
            print("⏭️ Next agent: Clearinghouse Review")
            print("=" * 80 + "\n")

            return {
                "claim": clean_nan(claim),
                "pipeline": clean_nan(claim.get("pipeline", {})),
                "stage": "WAITING_FOR_APPROVAL",
                "status": "WAITING_FOR_APPROVAL",
                "pipeline_state": "WAITING_FOR_APPROVAL",
                "current_stage": "CLEARINGHOUSE",
                "current_agent": "CLEARINGHOUSE",
                "active_step": "clearinghouse",
                "review_required": True,
                "processing_mode": processing_mode,
                "next_agent": "Clearinghouse Review",
                "submission": submission_payload,
                "duration_seconds": duration_seconds,
                "trace_id": trace_id,
                "agent_detail": agent_detail,
            }

        except Exception as error:
            duration_seconds = round(time.time() - start_time, 2)

            print("❌ [SubmissionAgent] FAILED")
            print(f"❌ Error: {str(error)}")
            print(f"⏱️ Submission duration before failure: {duration_seconds}s")
            print("=" * 80 + "\n")

            await self.log_error(
                "SubmissionAgent",
                error,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            failure_payload = {
                "claim_id": claim_id,
                "agent": "SubmissionAgent",
                "status": "failed",
                "error": str(error),
                "duration_seconds": duration_seconds,
                "trace_id": trace_id,
                "next_agent": "Case Orchestrator",
            }

            agent_detail = self.build_agent_detail(
                "submission",
                status="FAILED",
                active_step="Submission processing failed",
                message=str(error),
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=False,
                errors=[str(error)],
                output=failure_payload,
                next_agent="Case Orchestrator",
            )
            self.apply_agent_detail(
                claim,
                "submission",
                agent_detail,
                step_completed=False,
                result_status="FAILED",
                failed=True,
            )

            await manager.send_event(
                "submission",
                "failed",
                self.build_agent_event_payload(
                    "submission",
                    claim_id,
                    agent_detail,
                    existing_payload=failure_payload,
                    result_status="FAILED",
                    failed=True,
                    error=error,
                    duration_seconds=duration_seconds,
                ),
            )

            update_metrics(
                event_type="submission_failed",
                claim_id=claim_id,
                agent="SUBMISSION",
                payer=claim.get("payer"),
                risk_score=claim.get("risk_score", 0),
                latency=duration_seconds,
                status="FAILED",
            )

            await self.log_end(
                "SubmissionAgent",
                "FAILED",
                duration_seconds,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            return {
                "claim": claim,
                "pipeline": claim.get("pipeline", {}),
                "stage": "SUBMISSION_FAILED",
                "status": "FAILED",
                "error": str(error),
                "duration_seconds": duration_seconds,
                "trace_id": trace_id,
                "agent_detail": agent_detail,
            }

    def _pre_submission_errors(self, claim):
        errors = []

        if not claim.get("claim_id"):
            errors.append("Missing claim ID")

        if not claim.get("patient"):
            errors.append("Missing patient information")

        if not claim.get("provider"):
            errors.append("Missing provider information")

        if not claim.get("payer"):
            errors.append("Missing payer information")

        if not claim.get("services"):
            errors.append("No services to submit")

        validation = claim.get("validation") or {}

        if validation and validation.get("valid") is False:
            errors.append("Claim validation failed")

        if claim.get("validation_status") == "failed":
            errors.append("Claim validation status is failed")

        if claim.get("compliance_failed"):
            errors.append("Claim compliance failed")

        if claim.get("hard_reject"):
            errors.append("Claim is hard rejected by compliance")

        if claim.get("hitl_required"):
            errors.append("Claim requires human review before submission")

        return errors
