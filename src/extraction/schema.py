from pydantic import BaseModel, model_validator

class AmountEntry(BaseModel):
    label: str
    amount: float | None = None
    is_unlimited: bool = False

    @model_validator(mode="after")
    def amount_xor_unlimited(self):
        if self.is_unlimited and self.amount is not None:
            raise ValueError("AmountEntry cannot have both an amount and is_unlimited=True")
        if not self.is_unlimited and self.amount is None:
            raise ValueError("AmountEntry must have either an amount or is_unlimited=True")
        return self

class PlanFacts(BaseModel):
    source_filename: str
    insurer: str
    plan_name: str
    plan_type: str
    deductibles: list[AmountEntry]
    out_of_pocket_maxes: list[AmountEntry]
    referral_required: bool | None
    raw_referral_text: str
    raw_deductible_text: str
    raw_oop_max_text: str