import datetime
import uuid
import json
import hashlib
import os

from threading import Lock

AUDIT_FILE = "audit_log.json"

def load_audit_logs():
    if not os.path.exists(AUDIT_FILE):
        return []
    try:
        with open(AUDIT_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

audit_logs = load_audit_logs()
audit_lock = Lock()

def _save_audit_logs():
    with open(AUDIT_FILE, 'w') as f:
        json.dump(audit_logs, f, indent=4)

def clean_entry(entry):
    return {k: v for k, v in entry.items() if k != "hash"}


def verify_audit_integrity():

    for i in range(1, len(audit_logs)):

        current = audit_logs[i]
        prev = audit_logs[i - 1]

        expected_hash = generate_hash(
            clean_entry(current),
            current["prev_hash"]
        )

        if current["prev_hash"] != prev["hash"]:
            return False, f"Chain broken at index {i}"

        if current["hash"] != expected_hash:
            return False, f"Data tampered at index {i}"

    return True, "Audit log is valid"

# 🔒 Generate hash
def generate_hash(entry, prev_hash):
    payload = json.dumps(entry, sort_keys=True, default=str)
    return hashlib.sha256((payload + (prev_hash or "")).encode()).hexdigest()


def log_audit(claim_id, step, status, details=None):

    with audit_lock:

        prev_hash = audit_logs[-1]["hash"] if audit_logs else ""

        entry = {
            "id": str(uuid.uuid4()),
            "claim_id": claim_id,
            "step": step,
            "status": status,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "details": details or {},
            "prev_hash": prev_hash
        }

        entry["hash"] = generate_hash(entry, prev_hash)

        audit_logs.append(entry)
        _save_audit_logs()

        return entry


def get_audit_logs(claim_id=None):

    if claim_id:
        return [log for log in audit_logs if log["claim_id"] == claim_id]

    return audit_logs


# # 🔍 VERIFY INTEGRITY (VERY IMPORTANT)
# def verify_audit_integrity():

#     for i in range(1, len(audit_logs)):

#         current = audit_logs[i]
#         prev = audit_logs[i - 1]

#         expected_hash = generate_hash(
#             {k: v for k, v in current.items() if k != "hash"},
#             current["prev_hash"]
#         )

#         if current["prev_hash"] != prev["hash"]:
#             return False, f"Chain broken at index {i}"

#         if current["hash"] != expected_hash:
#             return False, f"Data tampered at index {i}"

#     return True, "Audit log is valid"