from dataclasses import dataclass

@dataclass
class RetrievalResult:
    chunk_id: str
    text: str
    score: float
    metadata: dict  # insurer, plan_name, section, category, row_index — for citations later