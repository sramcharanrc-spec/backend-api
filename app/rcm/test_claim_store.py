from app.rcm.claim_store import save_claim, get_claim

save_claim("CLM-TEST-1", {"hello": "world"})
print(get_claim("CLM-TEST-1"))
