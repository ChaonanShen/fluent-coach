from __future__ import annotations

from hashlib import sha1

from backend.app.models import Scenario


class CustomScenarioBuilder:
    def build(self, prompt: str, *, name: str | None = None) -> Scenario:
        normalized = " ".join(prompt.split())
        digest = sha1(normalized.lower().encode("utf-8")).hexdigest()[:10]
        scenario_id = f"custom_{digest}"
        matched = _matched_template(normalized, scenario_id=scenario_id, name=name)
        if matched is not None:
            return matched
        return _generic_scenario(normalized, scenario_id=scenario_id, name=name)


def _matched_template(prompt: str, *, scenario_id: str, name: str | None) -> Scenario | None:
    lowered = prompt.lower()
    if _contains_any(lowered, ["医生", "问诊", "doctor", "clinic", "symptom"]):
        return _doctor_scenario(scenario_id=scenario_id, name=name)
    if _contains_any(lowered, ["酒店", "hotel", "front desk", "reservation"]):
        return _hotel_scenario(scenario_id=scenario_id, name=name)
    if _contains_any(lowered, ["机场", "登机", "flight", "airport", "boarding"]):
        return _airport_scenario(scenario_id=scenario_id, name=name)
    if _contains_any(lowered, ["面试", "interview"]):
        return _interview_scenario(scenario_id=scenario_id, name=name)
    if _contains_any(lowered, ["点餐", "餐厅", "restaurant", "ordering food"]):
        return _restaurant_scenario(scenario_id=scenario_id, name=name)
    if _contains_any(lowered, ["会议", "meeting", "sync"]):
        return _meeting_scenario(scenario_id=scenario_id, name=name)
    return None


def _doctor_scenario(*, scenario_id: str, name: str | None) -> Scenario:
    return Scenario(
        id=scenario_id,
        name=_scenario_name(name, "Doctor Consultation"),
        ai_role="Doctor in a clinic role-play",
        user_role="Patient describing symptoms and asking for advice",
        opening_line="Good morning. What symptoms have you been having?",
        conversation_goals=[
            "Describe symptoms clearly",
            "Answer follow-up questions about duration and severity",
            "Ask about possible next steps",
        ],
        target_expressions=[
            "I have been feeling...",
            "It started...",
            "The pain gets worse when...",
            "What should I do next?",
        ],
        correction_focus=[
            "symptom descriptions",
            "present perfect for ongoing symptoms",
            "clear time expressions",
            "polite health-related questions",
        ],
        summary_rubric={
            "grammar": "Use clear tense and sentence structure when describing symptoms.",
            "task": "Explain symptoms, answer follow-up questions, and ask about next steps.",
        },
    )


def _hotel_scenario(*, scenario_id: str, name: str | None) -> Scenario:
    return Scenario(
        id=scenario_id,
        name=_scenario_name(name, "Hotel Check-in"),
        ai_role="Hotel front desk clerk",
        user_role="Hotel guest checking in and handling a reservation issue",
        opening_line="Good evening. Welcome to the hotel. May I have your name for the reservation?",
        conversation_goals=[
            "Check in at the front desk",
            "Clarify a reservation or room issue",
            "Ask polite questions about hotel services",
        ],
        target_expressions=[
            "I have a reservation under...",
            "Could you check that for me?",
            "Is breakfast included?",
            "Could I change rooms?",
        ],
        correction_focus=["polite requests", "hotel vocabulary", "clear problem descriptions"],
        summary_rubric={
            "grammar": "Use polite request forms and clear question structure.",
            "task": "Complete check-in and resolve the reservation issue politely.",
        },
    )


def _airport_scenario(*, scenario_id: str, name: str | None) -> Scenario:
    return Scenario(
        id=scenario_id,
        name=_scenario_name(name, "Airport Check-in"),
        ai_role="Airline check-in agent",
        user_role="Passenger checking in for a flight",
        opening_line="Hello. Where are you flying today?",
        conversation_goals=[
            "Check in for a flight",
            "Answer questions about bags and travel documents",
            "Ask about seat options or boarding time",
        ],
        target_expressions=[
            "I am flying to...",
            "I would like to check this bag.",
            "Could I have an aisle seat?",
            "What time does boarding start?",
        ],
        correction_focus=["travel vocabulary", "polite requests", "clear destination and time expressions"],
        summary_rubric={
            "grammar": "Use clear travel-related questions and statements.",
            "task": "Complete check-in and confirm key flight details.",
        },
    )


def _interview_scenario(*, scenario_id: str, name: str | None) -> Scenario:
    return Scenario(
        id=scenario_id,
        name=_scenario_name(name, "Job Interview"),
        ai_role="Hiring manager in a role-play interview",
        user_role="Candidate answering interview questions",
        opening_line="Thanks for joining today. Could you briefly introduce yourself?",
        conversation_goals=[
            "Introduce your background clearly",
            "Explain one relevant project or achievement",
            "Ask a thoughtful question about the role",
        ],
        target_expressions=[
            "I have worked on...",
            "One challenge I faced was...",
            "The result was...",
            "Could you tell me more about...",
        ],
        correction_focus=["past tense", "specific examples", "professional tone"],
        summary_rubric={
            "grammar": "Use accurate tense and sentence structure for work experience.",
            "task": "Introduce yourself, give examples, and ask about the role.",
        },
    )


def _restaurant_scenario(*, scenario_id: str, name: str | None) -> Scenario:
    return Scenario(
        id=scenario_id,
        name=_scenario_name(name, "Restaurant Ordering"),
        ai_role="Server at a casual restaurant",
        user_role="Customer ordering food and asking about the menu",
        opening_line="Hi, welcome in. Are you ready to order, or would you like a few more minutes?",
        conversation_goals=[
            "Ask about menu items",
            "Place an order politely",
            "Make one special request",
        ],
        target_expressions=[
            "Could I have...",
            "What do you recommend?",
            "Does this come with...",
            "Could you make it without...",
        ],
        correction_focus=["polite requests", "food vocabulary", "articles and quantifiers"],
        summary_rubric={
            "grammar": "Use polite request forms and correct articles for food items.",
            "task": "Ask questions, order clearly, and handle a special request.",
        },
    )


def _meeting_scenario(*, scenario_id: str, name: str | None) -> Scenario:
    return Scenario(
        id=scenario_id,
        name=_scenario_name(name, "Work Meeting"),
        ai_role="Project lead running a weekly sync meeting",
        user_role="Team member giving updates and discussing blockers",
        opening_line="Let's start with your update. What did you finish last week?",
        conversation_goals=[
            "Give a concise progress update",
            "Explain one blocker or risk",
            "Confirm ownership and next steps",
        ],
        target_expressions=[
            "I completed...",
            "I am currently working on...",
            "The main blocker is...",
            "I will follow up by...",
        ],
        correction_focus=["status update structure", "past tense", "clear ownership"],
        summary_rubric={
            "grammar": "Use accurate tense for completed work and next steps.",
            "task": "Share progress, explain blockers, and confirm next actions.",
        },
    )


def _generic_scenario(_prompt: str, *, scenario_id: str, name: str | None) -> Scenario:
    label = _scenario_name(name, "Custom Role Play")
    return Scenario(
        id=scenario_id,
        name=label,
        ai_role="Conversation partner in a custom English speaking role-play",
        user_role="Learner practicing the requested situation",
        opening_line="Let's start the role-play. What would you like to say first?",
        conversation_goals=[
            "Practice the custom situation described by the learner",
            "Answer naturally and ask one follow-up question when it fits",
        ],
        target_expressions=[
            "Could you tell me more about...",
            "I would like to...",
            "That works for me.",
        ],
        correction_focus=["grammar", "natural expression", "clarity"],
        summary_rubric={
            "grammar": "Use clear sentence structure without repeated major errors.",
            "task": "Keep the custom scenario moving with relevant details.",
        },
    )


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _scenario_name(name: str | None, fallback: str) -> str:
    if name and name.strip() and not contains_cjk(name):
        return _truncate(" ".join(name.split()), 80)
    return fallback


def build_custom_scenario(prompt: str, *, name: str | None = None) -> Scenario:
    return custom_scenario_builder.build(prompt, name=name)


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


custom_scenario_builder = CustomScenarioBuilder()
