"""Dice Roll Tool - Roll virtual dice using standard dice notation."""
import json
import logging
import random
import re

from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool("roll_dice", parse_docstring=True)
def roll_dice_tool(dice_notation: str) -> str:
    """Roll dice using standard notation (e.g., '2d6', '3d20', 'd8').

    Dice notation format: <number>d<sides>, where:
    - <number> is how many dice to roll (default 1 if omitted, max 200)
    - <sides> is how many sides each die has (min 2)

    Args:
        dice_notation: Dice notation like '2d6' (2 six-sided dice) or 'd20' (1 twenty-sided die).
    """
    match = re.match(r"^(\d*)d(\d+)$", dice_notation.lower().strip())
    if not match:
        return json.dumps(
            {"error": f"Invalid dice notation: '{dice_notation}'. Use format like '2d6' or 'd20'."},
            ensure_ascii=False,
        )

    count = int(match.group(1)) if match.group(1) else 1
    sides = int(match.group(2))

    if count < 1 or count > 200:
        return json.dumps({"error": "Number of dice must be between 1 and 200."}, ensure_ascii=False)
    if sides < 2:
        return json.dumps({"error": "Dice must have at least 2 sides."}, ensure_ascii=False)

    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    rolls_str = ", ".join(str(r) for r in rolls)

    return json.dumps(
        {
            "notation": dice_notation,
            "rolls": rolls,
            "total": total,
            "count": count,
            "sides": sides,
            "summary": f"Rolled {count}d{sides}: [{rolls_str}] = {total}",
        },
        indent=2,
        ensure_ascii=False,
    )
