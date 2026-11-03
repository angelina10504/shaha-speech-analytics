"""Rule set, severities and score penalties (from the assignment brief)."""

RULES = {
    "R1": ("Calls only between 8 AM and 7 PM", "High"),
    "R2": ("No abusive or foul language", "Critical"),
    "R3": ("No threats or intimidation", "Critical"),
    "R4": ("No shaming or disclosure to third parties", "Critical"),
    "R5": ("Never ask for OTP, PIN, CVV or passwords", "High"),
    "R6": ("Mandatory opening: name, company and purpose", "Medium"),
}

# Points taken off the 0-100 compliance score for each active flag.
PENALTY = {"Critical": 30, "High": 20, "Medium": 10, "Low": 5}

# R1 is checked in plain code from metadata, so the LLM must not report it.
LLM_RULES = ["R2", "R3", "R4", "R5", "R6"]

CALL_START_HOUR = 8   # calls allowed from 08:00
CALL_END_HOUR = 19    # and must start before 19:00
