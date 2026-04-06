from app.intake.claim_mapper import map_to_claim

# 🔥 Sample extracted data (simulate Textract output)
extracted = {
    "Patient Name": "John Doe",
    "DOB": "1990-01-01",
    "Provider": "Valley Medical",
    "NPI": "1234567890",
    "Insurance": "BlueCross PPO",
    "CPT 99213": "150",
    "CPT 77078": "250"
}

claim = map_to_claim(extracted)

print("📦 CLAIM OUTPUT:")
print(claim)