import json

INSURER_KEYWORDS: dict[str, list[str]] = {
    "kaiser_ca_traditional_hmo_2026.pdf": ["kaiser"],
    "aetna_md_bronze_ppo_2019.pdf": ["aetna"],
    "uhc_stancounty_hdhp_2025.pdf": ["unitedhealthcare", "united healthcare", "uhc"],
    "cigna_nc_connect_bronze_hmo_2024.pdf": ["cigna"],
    "blueshield_ca_calpers_access_hmo_2025.pdf": ["blue shield of ca", "blue shield california", "blue shield of california"],
    "bcbsil_bluechoice_bronze_ppo_2024.pdf": ["blue cross blue shield of il", "bcbs il", "bcbs of illinois", "blue cross blue shield of illinois"],
    "anthem_ppo_hsa_2022.pdf": ["anthem"],
    "highmark_hdhp_ppoblue_2026.pdf": ["highmark"],
}

with open("data/processed/plan_facts.json") as f:
    all_plan_facts = json.load(f)

plan_texts = {
    p["source_filename"]: f"{p['insurer']} {p['plan_name']}".lower()
    for p in all_plan_facts
}

print("Checking for collisions (a keyword matching more than one plan)...")
collisions_found = False
for source_filename, keywords in INSURER_KEYWORDS.items():
    for kw in keywords:
        matches = [fn for fn, text in plan_texts.items() if kw in text]
        if len(matches) > 1:
            collisions_found = True
            print(f"  COLLISION: '{kw}' (intended for {source_filename}) also matches: {matches}")

print()
print("Checking for false negatives (a keyword that doesn't match its own intended plan)...")
false_negatives_found = False
for source_filename, keywords in INSURER_KEYWORDS.items():
    text = plan_texts[source_filename]
    if not any(kw in text for kw in keywords):
        false_negatives_found = True
        print(f"  FALSE NEGATIVE: none of {keywords} matched {source_filename}'s real text: '{text}'")

print()
if not collisions_found and not false_negatives_found:
    print("All clear — no collisions, no false negatives.")
else:
    print("Issues found above — fix INSURER_KEYWORDS before trusting it.")