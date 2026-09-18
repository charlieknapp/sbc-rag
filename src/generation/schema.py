from typing import Literal

from pydantic import BaseModel


class Citation(BaseModel):
    insurer: str
    plan_name: str
    source_filename: str
    section: str
    source_type: Literal["verified_plan_data", "sbc_text"]


class GeneratedAnswer(BaseModel):
    answer: str
    citations: list[Citation]
    confident: bool