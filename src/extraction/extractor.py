import re
from .schema import AmountEntry

def parse_flat_single_value(text: str) -> list[AmountEntry]:
    """Handles Kaiser / Blue Shield CA shape: a single bare value, no tier, no scope. e.g. '$0.' or '$0..'"""
    match = re.search(r"\$([\d,]+)", text)
    if not match:
        return []
    amount = float(match.group(1).replace(",", ""))
    return [AmountEntry(label="all", amount=amount)]

def parse_flat_tier_only(text: str) -> list[AmountEntry]:
    """Handles Cigna / UHC shape: tier values, no scope. e.g. '$9,450 person/ $18,900 family.'"""
    pairs = re.findall(r"\$([\d,]+)\s*(person|family|individual|member)", text, re.IGNORECASE)
    return [
        AmountEntry(label=label.lower(), amount=float(amount.replace(",", "")))
        for amount, label in pairs
    ]
    

def find_tier_amount_pairs(text: str) -> list[AmountEntry]:
    """
    Shared helper: finds tier-label + value pairs in either order
    ("Individual $6,000" or "$6,000 individual"), where value is either
    a dollar amount or the literal word "Unlimited". Reused by any shape
    function that needs this specific sub-task, regardless of the larger
    surrounding structure (scope-outer, category-outer, etc.).
    """
    pattern = re.compile(
        r"(?P<label1>individual|family|person|member)\s*[:\s]\s*(?P<value1>\$[\d,]+|Unlimited)"
        r"|(?P<value2>\$[\d,]+|Unlimited)\s*/?\s*(?:per\s+)?(?P<label2>individual|family|person|member)",
        re.IGNORECASE,
    )
    entries = []
    for m in pattern.finditer(text):
        if m.group("label1"):
            label, value = m.group("label1").lower(), m.group("value1")
        else:
            label, value = m.group("label2").lower(), m.group("value2")

        if value.lower() == "unlimited":
            entries.append(AmountEntry(label=label, is_unlimited=True))
        else:
            entries.append(AmountEntry(label=label, amount=float(value.replace("$", "").replace(",", ""))))
    return entries


def find_label_amount_pairs(text: str, labels: list[str]) -> list[AmountEntry]:
    """
    Generalized shared helper: finds label + value pairs in either order,
    where `labels` is a list of regex fragments to match against (caller
    decides what counts as a label — tier words, scope words, etc.), and
    value is either a dollar amount or the literal word "Unlimited".
    Label order matters when one label is a substring of another
    (e.g. "non-participating" must be checked before "participating").
    """
    label_pattern = "|".join(labels)
    pattern = re.compile(
        rf"(?P<label1>{label_pattern})\s*[:\s]\s*(?P<value1>\$[\d,]+|Unlimited)"
        rf"|(?P<value2>\$[\d,]+|Unlimited)\s*/?\s*(?:per\s+)?(?P<label2>{label_pattern})",
        re.IGNORECASE,
    )
    entries = []
    for m in pattern.finditer(text):
        if m.group("label1"):
            label_raw, value = m.group("label1"), m.group("value1")
        else:
            label_raw, value = m.group("label2"), m.group("value2")
        label = re.sub(r"\s+", "", label_raw.lower())  # collapse "Non- Participating" -> "non-participating"

        if value.lower() == "unlimited":
            entries.append(AmountEntry(label=label, is_unlimited=True))
        else:
            entries.append(AmountEntry(label=label, amount=float(value.replace("$", "").replace(",", ""))))
    return entries


TIER_LABELS = ["individual", "family", "person", "member"]
BCBSIL_SCOPE_LABELS = [r"non-\s*participating", "participating"]  # order matters — non- checked first


def parse_scope_outer_colon(text: str) -> list[AmountEntry]:
    """Aetna's shape."""
    segments = re.split(r"(in-network|out-of-network)\s*:", text, flags=re.IGNORECASE)
    entries = []
    current_scope = None
    for part in segments:
        part = part.strip()
        if not part:
            continue
        if re.fullmatch(r"in-network|out-of-network", part, re.IGNORECASE):
            current_scope = normalize_scope(part)
        elif current_scope:
            for pair in find_label_amount_pairs(part, TIER_LABELS):
                entries.append(AmountEntry(
                    label=f"{pair.label}, {current_scope}",
                    amount=pair.amount,
                    is_unlimited=pair.is_unlimited,
                ))
    return entries


def parse_tier_outer_bcbsil(text: str) -> list[AmountEntry]:
    """BCBS IL's shape."""
    segments = re.split(r"(individual|family)\s*:", text, flags=re.IGNORECASE)
    entries = []
    current_tier = None
    for part in segments:
        part = part.strip()
        if not part:
            continue
        if re.fullmatch(r"individual|family", part, re.IGNORECASE):
            current_tier = part.lower()
        elif current_tier:
            for pair in find_label_amount_pairs(part, BCBSIL_SCOPE_LABELS):
                entries.append(AmountEntry(
                    label=f"{current_tier}, {normalize_scope(pair.label)}",
                    amount=pair.amount,
                    is_unlimited=pair.is_unlimited,
                ))
    return entries


def parse_scope_outer_trailing_clause(text: str) -> list[AmountEntry]:
    """Anthem's shape — amount-before-label, scope stated as a trailing 'for X Providers' clause, 3 tiers."""
    parts = re.split(r"for\s+(in-network|non-\s*network)\s+providers\.?", text, flags=re.IGNORECASE)
    entries = []
    for i in range(0, len(parts) - 1, 2):
        content, scope = parts[i], normalize_scope(parts[i + 1])
        for pair in find_label_amount_pairs(content, TIER_LABELS):
            entries.append(AmountEntry(
                label=f"{pair.label}, {scope}",
                amount=pair.amount,
                is_unlimited=pair.is_unlimited,
            ))
    return entries

SCOPE_LABEL_MAP = {
    "in-network": "in-network",
    "out-of-network": "out-of-network",
    "non-network": "out-of-network",     # Anthem's wording
    "participating": "in-network",        # BCBS IL's wording
    "non-participating": "out-of-network", # BCBS IL's wording
    "network": "in-network",              # Highmark's wording (coming up next)
}

def normalize_scope(raw: str) -> str:
    key = re.sub(r"\s+", "", raw.strip().lower())
    if key not in SCOPE_LABEL_MAP:
        raise ValueError(f"Unrecognized scope label: {raw!r} — add it to SCOPE_LABEL_MAP")
    return SCOPE_LABEL_MAP[key]

def clean_text(text: str) -> str:
    """
    Normalizes recurring PDF-extraction artifacts before any matching or
    parsing happens: Unicode dash variants (en dash, em dash) collapse to a
    plain hyphen, and a stray space right after a hyphen followed by a
    lowercase letter (e.g. "out-of- pocket") is removed. Deliberately scoped
    to the lowercase case so it doesn't touch "Non- Participating"/"Non-
    Network" style artifacts, which already have their own tested
    whitespace-tolerant regex downstream.
    """
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"-\s+(?=[a-z])", "-", text)
    return text

def parse_scope_outer_trailing_label(text: str, scope_labels: list[str]) -> list[AmountEntry]:
    """
    Handles scope-outer text where the scope label TRAILS the amounts
    instead of leading them, with optional trailing punctuation, e.g.:
      Highmark deductible: "...family network. ...family out-of-network.."
      UHC OOP max:          "...family In-network ...family Out-of-network."

    scope_labels must be ordered most-specific-first, so a label that is a
    substring of another (e.g. "network" inside "out-of-network") can't
    match too early and truncate the real one.
    """
    entries = []
    pattern = r"([^.]*?)\s*(" + "|".join(scope_labels) + r")\.*\s*"
    for chunk, scope_raw in re.findall(pattern, text, flags=re.IGNORECASE):
        scope = normalize_scope(scope_raw)
        for entry in find_label_amount_pairs(chunk, TIER_LABELS):
            entries.append(AmountEntry(
                label=f"{scope}_{entry.label}",
                amount=entry.amount,
                is_unlimited=entry.is_unlimited,
            ))
    return entries


def parse_highmark_oop_max(text: str) -> list[AmountEntry]:
    """
    Highmark's OOP max text restates the network figure twice — once as
    "network out-of-pocket limit", again as "total maximum out-of-pocket" —
    before giving the out-of-network figure once, e.g.:
    "$4,000 individual/$8,000 family network out-of-pocket limit, up to a
    total maximum out-of-pocket of $4,000 individual/$8,000 family.
    $8,000 individual/$16,000 family out-of-network.."

    Deliberately NOT reusing the generic scope-outer splitter here: the
    duplicate clause would produce two network pairs instead of one. Instead
    we bound each scope's text window explicitly before pairing, so the
    restated clause is simply never handed to the pair-finder.
    """
    entries = []

    # network window = everything up to the "up to a total maximum..." restatement
    network_chunk = re.split(r",?\s*up to a total maximum", text, flags=re.IGNORECASE)[0]
    for entry in find_label_amount_pairs(network_chunk, TIER_LABELS):
        entries.append(AmountEntry(
            label=f"network_{entry.label}",
            amount=entry.amount,
            is_unlimited=entry.is_unlimited,
        ))

    # out-of-network window = the amount pair immediately preceding "out-of-network"
    oon_chunk_match = re.search(r"([^.]*?family)\s+out-of-network", text, flags=re.IGNORECASE)
    if oon_chunk_match:
        for entry in find_label_amount_pairs(oon_chunk_match.group(1), TIER_LABELS):
            entries.append(AmountEntry(
                label=f"out-of-network_{entry.label}",
                amount=entry.amount,
                is_unlimited=entry.is_unlimited,
            ))

    return entries

# --- Blue Shield CA ---

def parse_category_outer_colon(text: str) -> list[AmountEntry]:
    """
    Handles category-outer text with a leading colon-delimited label,
    e.g.: "Medical: $1,500 per individual / $3,000 per family.
    Pharmacy: $7,700 per individual / $15,400 per family.
    Includes $1,000 for mail-service formulary prescription drugs per member.."
    Used for Blue Shield CA's OOP max field (medical/pharmacy split).

    Each category's match window is bounded to the text up through its own
    trailing period, so the mail-order aside after "Pharmacy: ..." is never
    handed to the pair-finder at all.
    """
    entries = []
    pattern = r"(Medical|Pharmacy):\s*([^.]*\.)"
    for category, chunk in re.findall(pattern, text, flags=re.IGNORECASE):
        for entry in find_label_amount_pairs(chunk, TIER_LABELS):
            entries.append(AmountEntry(
                label=f"{category.lower()}_{entry.label}",
                amount=entry.amount,
                is_unlimited=entry.is_unlimited,
            ))
    return entries

# --- Kaiser ---

def parse_kaiser_oop_max(text: str) -> list[AmountEntry]:
    """
    Kaiser's OOP max text gives an unlabeled medical pair first, followed by
    a second pair with a trailing "for prescription drugs" clause, e.g.:
    "$1,500 Individual / $3,000 Family. $8,650 Individual / $17,300 Family
    for prescription drugs.."

    Dedicated rather than generalized: the medical clause has no label word
    to split on at all, unlike every other shape built so far, so there's
    nothing shareable here beyond find_label_amount_pairs itself.
    """
    entries = []
    segments = [s.strip() for s in text.split(".") if s.strip()]
    for segment in segments:
        category = "prescription_drugs" if "prescription drugs" in segment.lower() else "medical"
        for entry in find_label_amount_pairs(segment, TIER_LABELS):
            entries.append(AmountEntry(
                label=f"{category}_{entry.label}",
                amount=entry.amount,
                is_unlimited=entry.is_unlimited,
            ))
    return entries

# --- Referral required (all insurers) ---

def parse_referral_required(text: str) -> bool | None:
    """
    Looks for a standalone "yes" or "no" via word boundaries, so stray
    OCR/PDF-extraction artifacts before the real word (e.g. Highmark's
    "o No..") don't break the match. Returns None — not a guess — if
    neither word is found, consistent with this whole phase's "fail loud,
    don't silently mis-extract" principle.

    Deliberately does NOT try to interpret conditional answers like
    Kaiser's "Yes, but you may self-refer to certain specialists." beyond
    treating the leading "Yes" as the answer — the caveat itself belongs
    in raw_referral_text on PlanFacts, not folded into this bool.
    """
    if re.search(r"\byes\b", text, flags=re.IGNORECASE):
        return True
    if re.search(r"\bno\b", text, flags=re.IGNORECASE):
        return False
    return None