from langgraph.graph import StateGraph, END
from app.websocket.manager import manager
from app.agents.langgraph_node import create_node

# -------------------------
# Imports
# -------------------------
from app.agents.submission.submission_agent import SubmissionAgent
from app.agents.acknowledgment.acknowledgment_agent import AcknowledgmentAgent
from app.agents.payment.payment_agent import PaymentAgent
from app.agents.analytics.analytics_agent import AnalyticsAgent
from app.agents.denial.denial_agent import DenialAgent
from app.agents.eligibility.eligibility_agent import EligibilityAgent
from app.agents.case.case_agent import CaseOrchestratorAgent
from app.agents.rules.rules_validation_agent import RulesValidationAgent
from app.agents.compliance.compliance_agent import ComplianceAgent
from app.agents.learning.learning_agent import LearningAgent
from app.agents.validation.validation_agent import ValidationAgent
# -------------------------
# State
# -------------------------
State = dict

builder = StateGraph(State)

# -------------------------
# Initialize Agents
# -------------------------
# supervisor = SuperAgent()

submission = SubmissionAgent()
acknowledgment = AcknowledgmentAgent()
payment = PaymentAgent()
analytics = AnalyticsAgent()
denial = DenialAgent()
eligibility = EligibilityAgent()

case_agent = CaseOrchestratorAgent()
# rules_agent = RulesValidationAgent()
validation_agent = ValidationAgent()
compliance_agent = ComplianceAgent()
learning_agent = LearningAgent()

# -------------------------
# Rules Validation Node
# -------------------------
# async def rules_validation_node(state):

#     claim = state.get("claim", {})

#     await manager.send_event("rules_validation", "running")

#     result = await rules_agent.run(claim)

#     # Extract
#     validation = result.get("validation", {})
#     state["validation"] = validation
#     state["claim"] = result.get("claim")

#     # 🔥 Merge pipeline safely
#     state.setdefault("pipeline", {}).setdefault("steps", {}).update(
#         result.get("pipeline", {}).get("steps", {})
#     )

#     await manager.send_event(
#         "rules_validation",
#         validation.get("status"),
#         {"errors": validation.get("errors", [])}
#     )

#     return state


# -------------------------
# 🔥 FINAL SUPERVISOR NODE (FIXED)
# -------------------------
# async def supervisor_node(state):
    

#     # 🔥 HITL STOP (CRITICAL)
#     if state.get("status") == "HITL_REQUIRED":
#         print("⛔ STOPPING PIPELINE (HITL)")
#         return END

#     state["iteration"] = state.get("iteration", 0) + 1

#     # 🛑 HARD STOP (prevents demo crash)
#     if state["iteration"] > 15:
#         print("🛑 FORCE STOP (demo safe)")
#         return END

#     steps = state.get("pipeline", {}).get("steps", {})

#     print("🧠 PIPELINE:", steps)

#     # 1. Eligibility
#     if not steps.get("eligibility_checked"):
#         state["next"] = "eligibility"
#         return state

#     # 2. Validation
#     if not steps.get("rules_validated"):
#         state["next"] = "rules_validation"
#         return state

#     # 3. Case (AFTER validation)
#     if not steps.get("case_orchestrated"):
#         state["next"] = "case_orchestrator"
#         return state

#     # 4. Submission
#     if not steps.get("submitted"):
#         state["next"] = "submission"
#         return state

#     # 5. Denial
#     if not steps.get("denial_checked"):
#         state["next"] = "denial"
#         return state

#     # 6. Payment
#     if not steps.get("paid"):
#         state["next"] = "payment"
#         return state

#     # 7. Analytics
#     if not steps.get("analytics_done"):
#         state["next"] = "analytics"
#         return state
    
#     print("✅ PIPELINE COMPLETE")
#     return END

async def supervisor_node(state):

    # 🔥 HITL STOP
    if state.get("status") == "HITL_REQUIRED":
        print("⛔ STOPPING PIPELINE (HITL)")
        return END

    state["iteration"] = state.get("iteration", 0) + 1

    if state["iteration"] > 15:
        print("🛑 FORCE STOP (demo safe)")
        return END

    steps = state.get("pipeline", {}).get("steps", {})

    print("🧠 PIPELINE:", steps)

    # 1. Eligibility
    if not steps.get("eligibility_checked"):
        state["next"] = "eligibility"
        return state

    # 2. Validation
    if not steps.get("rules_validated"):
        state["next"] = "rules_validation"
        return state

    # 3. Case
    if not steps.get("case_orchestrated"):
        state["next"] = "case_orchestrator"
        return state

    # 4. Submission
    if not steps.get("submitted"):
        state["next"] = "submission"
        return state

    # 🔥 🔥 CRITICAL FIX: STOP AFTER SUBMISSION
    if steps.get("submitted") and not steps.get("acknowledged"):
        print("⏸ WAITING FOR CLEARINGHOUSE APPROVAL")
        
        state["next"] = "finish"
        return state   # ⛔ STOP PIPELINE HERE

    # 5. Denial
    if not steps.get("denial_checked"):
        state["next"] = "denial"
        return state

    # 6. Payment
    if not steps.get("paid"):
        state["next"] = "payment"
        return state

    # 7. Analytics
    if not steps.get("analytics_done"):
        state["next"] = "analytics"
        return state

    print("✅ PIPELINE COMPLETE")
    return END
# -------------------------
# Add Nodes
# -------------------------
builder.add_node("supervisor", supervisor_node)
builder.add_node("case_orchestrator", create_node(case_agent))
builder.add_node("eligibility", create_node(eligibility))
builder.add_node("rules_validation", create_node(validation_agent))
builder.add_node("submission", create_node(submission))
builder.add_node("acknowledgment", create_node(acknowledgment))
builder.add_node("denial", create_node(denial))
builder.add_node("payment", create_node(payment))
builder.add_node("analytics", create_node(analytics))
builder.add_node("compliance", create_node(compliance_agent))
builder.add_node("learning", create_node(learning_agent))

# -------------------------
# Router
# -------------------------
def router(state):

    if not isinstance(state, dict):
        print("❌ Invalid state:", state)
        return "finish"

    return state.get("next", "finish")


# -------------------------
# Conditional Edges
# -------------------------
builder.add_conditional_edges(
    "supervisor",
    router,
    {
        "case_orchestrator": "case_orchestrator",
        "eligibility": "eligibility",
        "rules_validation": "rules_validation",
        "submission": "submission",
        "acknowledgment": "acknowledgment",
        "denial": "denial",
        "payment": "payment",
        "analytics": "analytics",
        "compliance": "compliance",
        "learning": "learning",
        "finish": "__end__"
    }
)

# -------------------------
# Loop Back
# -------------------------
for node in [
    "case_orchestrator",
    "eligibility",
    "rules_validation",
    "submission",
    "acknowledgment",
    "denial",
    "payment",
    "analytics",
    "compliance",
    "learning",
]:
    builder.add_edge(node, "supervisor")

# -------------------------
# Entry
# -------------------------
builder.set_entry_point("supervisor")

# -------------------------
# Compile
# -------------------------
rcm_graph = builder.compile()