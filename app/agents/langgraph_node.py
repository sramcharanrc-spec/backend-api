# from app.websocket.manager import manager


# def create_node(agent):

#     async def node(state):

#         claim = state.get("claim")

#         if claim is None:
#             raise ValueError("claim missing in state")

#         # 🔥 Step name (UI safe)
#         step_name = state.get("current_step") or agent.__class__.__name__.replace("Agent", "").lower()

#         # 🔥 STEP START
#         await manager.broadcast({
#             "type": "STEP_START",
#             "step": step_name,
#             "next": state.get("next")
#         })

#         try:
#             # -------------------------
#             # Run agent
#             # -------------------------
#             result = await agent.run(claim)

#             if result is None:
#                 result = {}

#             # 🔥 STEP COMPLETE
#             await manager.broadcast({
#                 "type": "STEP_COMPLETE",
#                 "step": step_name,
#                 "data": result
#             })

#             # =========================================
#             # 🔥 FINAL SAFE MERGE (WITH NORMALIZATION)
#             # =========================================

#             # 🔹 Normalize existing state pipeline
#             state_pipeline = state.get("pipeline", {})
#             if not isinstance(state_pipeline, dict):
#                 state_pipeline = {}

#             if "steps" not in state_pipeline:
#                 state_pipeline = {"steps": state_pipeline}

#             # 🔹 Normalize result pipeline
#             result_pipeline = result.get("pipeline", {})
#             if not isinstance(result_pipeline, dict):
#                 result_pipeline = {}

#             if "steps" not in result_pipeline:
#                 result_pipeline = {"steps": result_pipeline}

#             # 🔹 Extract steps safely
#             current_steps = state_pipeline.get("steps", {})
#             result_steps = result_pipeline.get("steps", {})

#             if not isinstance(current_steps, dict):
#                 current_steps = {}

#             if not isinstance(result_steps, dict):
#                 result_steps = {}

#             # 🔥 CRITICAL: REASSIGN (LangGraph requirement)
#             merged_steps = {**current_steps, **result_steps}

#             state["pipeline"] = {
#                 "steps": merged_steps
#             }

#             # -------------------------
#             # Merge remaining fields
#             # -------------------------
#             for key, value in result.items():
#                 if key != "pipeline":
#                     state[key] = value

#             return state

#         except Exception as e:

#             # 🔥 STEP FAILED
#             await manager.broadcast({
#                 "type": "STEP_FAILED",
#                 "step": step_name,
#                 "error": str(e)
#             })

#             raise e

#     return node

from app.websocket.manager import manager

def create_node(agent):

    async def node(state):

        claim = state.get("claim")

        if claim is None:
            raise ValueError("claim missing in state")

        step_name = agent.__class__.__name__.replace("Agent", "").lower()

        await manager.broadcast({
            "type": "STEP_START",
            "step": step_name
        })

        try:
            result = await agent.run(claim) or {}
            print("✅ PIPELINE UPDATE:", result.get("pipeline"))
            await manager.broadcast({
                "type": "STEP_COMPLETE",
                "step": step_name
            })

            # -------------------------
            # 🔥 SAFE PIPELINE MERGE
            # -------------------------
            if "pipeline" in result and "steps" in result["pipeline"]:

                if "pipeline" not in state:
                    state["pipeline"] = {"steps": {}}

                if "steps" not in state["pipeline"]:
                    state["pipeline"]["steps"] = {}

                state["pipeline"]["steps"].update(
                    result["pipeline"]["steps"]
                )

            # -------------------------
            # 🔥 MERGE OTHER DATA
            # -------------------------
            for key, value in result.items():
                if key != "pipeline":
                    state[key] = value

            return state

        except Exception as e:
            await manager.broadcast({
                "type": "STEP_FAILED",
                "step": step_name,
                "error": str(e)
            })
            raise e
   
    return node