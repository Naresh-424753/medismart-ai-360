"""Nutrition, fitness and mental-wellness helpers (pure functions)."""
from __future__ import annotations

ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}


def bmi_category(b: float) -> str:
    return "Underweight" if b < 18.5 else "Normal" if b < 23 else "Overweight" if b < 27.5 else "Obese"  # Asian-Indian cut-offs


def calculate(weight_kg: float, height_cm: float, age: int, sex: str, activity: str = "light", goal: str = "maintain") -> dict:
    bmi = weight_kg / ((height_cm / 100) ** 2)
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if sex.lower().startswith("m") else -161)  # Mifflin-St Jeor
    tdee = bmr * ACTIVITY.get(activity, 1.375)
    target = tdee - 400 if goal == "lose" else tdee + 300 if goal == "gain" else tdee
    water_l = round(weight_kg * 0.035, 1)
    return {
        "bmi": round(bmi, 1), "bmi_category": bmi_category(bmi), "bmr": round(bmr), "tdee": round(tdee),
        "calorie_target": round(target), "water_liters": water_l,
        "protein_g": round(weight_kg * (1.2 if goal != "gain" else 1.6)),
        "healthy_weight_range_kg": [round(18.5 * (height_cm / 100) ** 2, 1), round(22.9 * (height_cm / 100) ** 2, 1)],
        "step_goal": 8000 if age < 60 else 6000,
    }


def diet_plan(calories: int, conditions: list[str], vegetarian: bool = True) -> dict:
    conds = {c.lower() for c in conditions}
    meals = {
        "breakfast": ["Vegetable poha / oats upma with nuts", "Low-fat milk or curd"] if vegetarian else ["Egg whites + whole-wheat toast", "Fruit"],
        "lunch": ["2 rotis (multigrain), dal, seasonal sabzi, salad", "Curd / buttermilk"],
        "snack": ["Roasted chana or fruit", "Green tea / buttermilk"],
        "dinner": ["Khichdi or vegetable soup + 1-2 rotis", "Paneer / sprouts / grilled fish"] if vegetarian else ["Grilled chicken/fish, sauteed vegetables, 1 roti"],
    }
    avoid, tips = [], [f"Aim for about {calories} kcal/day split across 3 meals and 1-2 snacks."]
    if "diabetes" in conds:
        avoid += ["sugary drinks", "sweets", "white bread/maida"]
        tips.append("Prefer low-GI foods (oats, millets, dal); keep meal timings regular.")
    if "hypertension" in conds or "high blood pressure" in conds:
        avoid += ["extra salt", "pickles/papad", "processed snacks"]
        tips.append("Keep salt under 5 g/day; add potassium-rich fruits unless told otherwise.")
    if "kidney" in conds or "ckd" in conds:
        tips.append("Kidney disease needs a personalised plan (protein, potassium, phosphorus) from your doctor/dietitian.")
    if "cholesterol" in conds or "heart" in conds:
        avoid += ["deep-fried food", "ghee/butter in excess", "red meat"]
    return {"meals": meals, "avoid": sorted(set(avoid)), "tips": tips}


def exercise_plan(bmi: float, age: int, conditions: list[str]) -> list[str]:
    plan = ["Brisk walking 30 min, 5 days/week", "Stretching / yoga 10-15 min daily", "Strength exercises 2 days/week (bodyweight)"]
    if bmi >= 27.5:
        plan.insert(0, "Start with low-impact cardio (walking, cycling, swimming) and build up gradually")
    if age >= 60:
        plan.append("Add balance exercises (tai-chi, heel-to-toe walk) to prevent falls")
    if {c.lower() for c in conditions} & {"heart", "hypertension", "diabetes"}:
        plan.append("Check with your doctor before starting a new exercise programme")
    return plan


# PHQ-2 and GAD-2 style screening (screening support only)
PHQ2 = ["Little interest or pleasure in doing things", "Feeling down, depressed or hopeless"]
GAD2 = ["Feeling nervous, anxious or on edge", "Not being able to stop or control worrying"]


def screen(kind: str, answers: list[int]) -> dict:
    """Each answer 0-3 (not at all .. nearly every day). Score >= 3 suggests further evaluation."""
    qs = PHQ2 if kind == "depression" else GAD2
    if len(answers) != len(qs) or any(a not in (0, 1, 2, 3) for a in answers):
        raise ValueError("Provide 2 answers, each 0-3")
    s = sum(answers)
    positive = s >= 3
    return {
        "kind": kind, "score": s, "positive_screen": positive,
        "message": ("Your answers suggest it may help to talk to a counselor or doctor for a fuller assessment." if positive
                    else "Your answers don't suggest a concern right now. Keep tracking your mood and sleep."),
        "disclaimer": "This is a brief screening tool, not a diagnosis.",
        "support": "If you ever feel unsafe or think about harming yourself, call your local emergency number or a crisis helpline right away (India: Tele-MANAS 14416).",
    }


def breathing_exercises() -> list[dict]:
    return [
        {"name": "4-7-8 breathing", "steps": "Inhale 4s, hold 7s, exhale 8s. Repeat 4 times."},
        {"name": "Box breathing", "steps": "Inhale 4s, hold 4s, exhale 4s, hold 4s. Repeat 5 times."},
        {"name": "Anulom-Vilom", "steps": "Alternate nostril breathing for 5 minutes at a relaxed pace."},
    ]
