import random

class ClearinghouseClient:

    def submit(self, claim):

        return {
            "transaction_id": f"TXN-{claim.id}"
        }

    def check_status(self, transaction_id):

        outcomes = ["accepted", "denied", "paid"]
        result = random.choice(outcomes)

        if result == "denied":
            return {"status": "DENIED", "denial_code": "CO-50"}

        if result == "paid":
            return {"status": "PAID"}

        return {"status": "ACK_RECEIVED"}