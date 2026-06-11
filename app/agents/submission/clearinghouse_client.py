import random
import uuid

from app.utils.security import mask_sensitive_payload


class ClearinghouseClient:
    def submit(self, claim):
        safe_claim = mask_sensitive_payload(claim)

        print("📤 [ClearinghouseClient] Submit request:", safe_claim)

        claim_id = (
            claim.get("claim_id")
            if isinstance(claim, dict)
            else getattr(claim, "id", None)
        )

        response = {
            "transaction_id": f"TXN-{claim_id or uuid.uuid4().hex[:8]}",
            "status": "SUBMITTED",
        }

        print("✅ [ClearinghouseClient] Submit response:", response)

        return response

    def check_status(self, transaction_id):
        print(f"🔎 [ClearinghouseClient] Checking status: {transaction_id}")

        outcomes = ["accepted", "denied", "paid"]
        result = random.choice(outcomes)

        if result == "denied":
            response = {
                "transaction_id": transaction_id,
                "status": "DENIED",
                "denial_code": "CO-50",
            }

        elif result == "paid":
            response = {
                "transaction_id": transaction_id,
                "status": "PAID",
            }

        else:
            response = {
                "transaction_id": transaction_id,
                "status": "ACK_RECEIVED",
            }

        print("✅ [ClearinghouseClient] Status response:", response)

        return response