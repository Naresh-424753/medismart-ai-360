"""Blood-group compatibility, donor eligibility and stock-expiry helpers."""
from __future__ import annotations

from datetime import date, datetime, timedelta

GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
# recipient -> donors whose red cells can be given safely
DONORS_FOR = {"O-": ["O-"], "O+": ["O+", "O-"], "A-": ["A-", "O-"], "A+": ["A+", "A-", "O+", "O-"],
              "B-": ["B-", "O-"], "B+": ["B+", "B-", "O+", "O-"], "AB-": ["AB-", "A-", "B-", "O-"], "AB+": GROUPS}
MIN_DAYS_BETWEEN_DONATIONS = 90  # conservative; many banks use 56-90 days. Medical screening still decides.
RED_CELL_SHELF_LIFE_DAYS = 35


def compatible_donor_groups(recipient: str) -> list[str]:
    if recipient not in DONORS_FOR:
        raise ValueError("invalid blood group")
    return DONORS_FOR[recipient]


def donor_eligibility(last_donation: str | None, age: int | None, weight_kg: float | None, today: date | None = None) -> dict:
    today = today or date.today()
    reasons = []
    if age is not None and not 18 <= age <= 65:
        reasons.append("Donors must be 18-65 years old")
    if weight_kg is not None and weight_kg < 45:
        reasons.append("Minimum weight is 45 kg")
    nxt = None
    if last_donation:
        nxt_d = datetime.strptime(last_donation, "%Y-%m-%d").date() + timedelta(days=MIN_DAYS_BETWEEN_DONATIONS)
        nxt = nxt_d.isoformat()
        if nxt_d > today:
            reasons.append(f"Next donation possible from {nxt}")
    return {"eligible": not reasons, "reasons": reasons, "next_eligible_date": nxt}


def expiry_status(expiry: str, today: date | None = None, warn_days: int = 7) -> str:
    today = today or date.today()
    d = (datetime.strptime(expiry, "%Y-%m-%d").date() - today).days
    return "expired" if d < 0 else "expiring_soon" if d <= warn_days else "ok"


def stock_summary(batches: list[dict], today: date | None = None) -> dict:
    """batches: [{blood_group, units, expiry}] -> usable units per group, expiring and expired units."""
    out = {g: {"usable": 0, "expiring_soon": 0, "expired": 0} for g in GROUPS}
    for b in batches:
        st = expiry_status(b["expiry"], today)
        g = out[b["blood_group"]]
        if st == "expired":
            g["expired"] += b["units"]
        else:
            g["usable"] += b["units"]
            if st == "expiring_soon":
                g["expiring_soon"] += b["units"]
    return out
