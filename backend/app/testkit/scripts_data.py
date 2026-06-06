from __future__ import annotations

from itertools import islice, cycle


SCRIPTED_USER_LINES: dict[str, tuple[str, ...]] = {
    "interview": (
        "My weekend was relaxing and quiet overall.",
        "I enjoy building backend services and developer tools.",
        "One project taught me how to improve reliability under pressure.",
        "I usually explain trade offs with clear examples and numbers.",
        "My strongest habit is turning vague goals into small milestones.",
        "I would like to understand how this team measures ownership.",
        "A recent challenge was coordinating API changes across two teams.",
        "I handled the timeline risk by sharing a short update every day.",
    ),
    "restaurant_ordering": (
        "I would like to start with something light today.",
        "Could you explain which dishes are most popular for lunch?",
        "I prefer a meal without too much sugar or heavy sauce.",
        "Please bring the soup first and the sandwich after that.",
        "I might need a few extra minutes before choosing dessert.",
        "Could you check whether this salad includes any peanuts?",
        "The order looks good, but I think the drink is missing.",
        "That is everything for now, and thank you for your help.",
    ),
    "meeting": (
        "I finished the API review and documented the remaining questions.",
        "This week I am focusing on the integration test coverage.",
        "The biggest risk is that the design decision is still open.",
        "I can own the backend changes and share a progress note tomorrow.",
        "Could we confirm which milestone has the highest priority now?",
        "The first version is ready, but the metrics still need validation.",
        "I will follow up with data team after this meeting.",
        "We may need one extra day if the deployment window changes.",
    ),
}


def scripted_user_lines(scenario_id: str, turns: int) -> list[str]:
    if turns < 0:
        raise ValueError("turns must be non-negative")
    lines = SCRIPTED_USER_LINES.get(scenario_id)
    if lines is None:
        raise ValueError(f"Unknown scripted scenario: {scenario_id}")
    return list(islice(cycle(lines), turns))
