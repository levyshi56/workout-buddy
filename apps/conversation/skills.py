"""
Skills — the LLM's tools for interacting with the database.

Each skill is an OpenAI function-calling tool. Read skills query data,
write skills mutate state. Every skill returns a result dict so the LLM
sees what happened.
"""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── OpenAI Tool Definitions ──────────────────────────────────────────

TOOL_DEFINITIONS = [
    # Read skills
    {
        "type": "function",
        "function": {
            "name": "get_profile",
            "description": (
                "Retrieve the user's profile: name, goals, equipment, injuries, "
                "preferences, notes, PRs, session count. Call this at the start of "
                "a conversation or when you need to recall something about the user."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workout_history",
            "description": (
                "Retrieve the user's most recent workout sessions. Use this to "
                "avoid repeating the same workout and to plan progressive overload."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of recent sessions to retrieve (1-10).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_prs",
            "description": (
                "Retrieve the user's personal records dictionary. Call this when "
                "planning weights or celebrating milestones."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_session",
            "description": (
                "Retrieve the current active workout session state: plan, current "
                "exercise/set indices, completed sets. Returns null if no session is active."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # Write skills
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": (
                "Persist information the user shared about themselves. Use this whenever "
                "the user reveals their name, goals, available equipment, injuries, "
                "preferences, or other notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["name", "goals", "equipment", "injuries", "preferences", "notes"],
                        "description": "Which profile field to update.",
                    },
                    "value": {
                        "type": "string",
                        "description": "The new value for the field.",
                    },
                },
                "required": ["field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_session",
            "description": (
                "Start a new workout session with a structured plan. Call this once "
                "when the user is ready to begin working out. The plan is a list of "
                "exercises with sets, reps, and suggested weight."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "workout_plan": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "sets": {"type": "integer"},
                                "reps": {"type": "integer"},
                                "weight": {"type": "number"},
                            },
                            "required": ["name", "sets", "reps"],
                        },
                        "description": "Ordered list of exercises for this session.",
                    },
                },
                "required": ["workout_plan"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_set",
            "description": (
                "Record a completed set. Automatically advances the set/exercise "
                "index. Call this every time the user reports finishing a set."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise": {"type": "string", "description": "Exercise name."},
                    "reps": {"type": "integer", "description": "Reps completed."},
                    "weight": {"type": "number", "description": "Weight used."},
                },
                "required": ["exercise", "reps", "weight"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_rest",
            "description": (
                "Start a rest timer. The user will receive a notification when rest "
                "is over. Use 60-90s for compound lifts, 30-60s for accessories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "description": "Rest duration in seconds.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "advance_exercise",
            "description": (
                "Skip to the next exercise in the plan. Use when the user wants to "
                "move on without completing all sets. Does not log any data."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_session",
            "description": (
                "Finalize the workout. Saves all logged sets to history, updates "
                "PRs, and clears the active session. Call this when the user says "
                "they're done or after the last planned exercise."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Estimated session duration in minutes.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of the session for the log.",
                    },
                },
                "required": ["duration_minutes"],
            },
        },
    },
]


# ── Skill Implementations ────────────────────────────────────────────


def skill_get_profile(user) -> dict:
    return {
        "name": user.name or "unknown",
        "goals": user.goals or "",
        "equipment": user.equipment or "",
        "injuries": user.injuries or "",
        "preferences": user.preferences or "",
        "notes": user.notes or "",
        "prs": dict(user.prs) if user.prs else {},
        "total_sessions": user.total_sessions,
    }


def skill_get_workout_history(user, count=3) -> dict:
    count = min(max(int(count), 1), 10)
    recent = list(user.sessions)[-count:]
    sessions = []
    for s in reversed(recent):
        exercises = []
        for e in s.exercises:
            sets = [{"reps": sr.reps, "weight": sr.weight} for sr in e.sets]
            exercises.append({"name": e.name, "sets": sets})
        sessions.append({
            "date": s.date.strftime("%Y-%m-%d") if s.date else None,
            "exercises": exercises,
            "duration_minutes": s.duration_minutes,
            "notes": s.notes,
        })
    return {"sessions": sessions} if sessions else {"sessions": [], "note": "No previous sessions."}


def skill_get_prs(user) -> dict:
    return {"prs": dict(user.prs) if user.prs else {}}


def skill_get_active_session(user) -> dict:
    if not user.active_session:
        return {"active_session": None}
    s = user.active_session
    plan = s.workout_plan or []
    current_ex = plan[s.current_exercise_index] if s.current_exercise_index < len(plan) else None
    return {
        "active_session": {
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "workout_plan": plan,
            "current_exercise_index": s.current_exercise_index,
            "current_set_index": s.current_set_index,
            "current_exercise": current_ex,
            "completed_sets_count": len(s.completed_sets or []),
        }
    }


def skill_update_memory(user, field, value) -> dict:
    allowed = {"name", "goals", "equipment", "injuries", "preferences", "notes"}
    if field not in allowed:
        return {"error": f"Field '{field}' is not a valid memory field."}
    setattr(user, field, value)
    user.save()
    logger.info("memory updated: %s.%s = %r", user.phone_number, field, value)
    return {"updated": True, "field": field, "value": value}


def skill_start_session(user, workout_plan) -> dict:
    from apps.users.models import ActiveSession

    if user.active_session and user.active_session.completed_sets:
        return {"error": "A session is already active. End it first."}

    user.active_session = ActiveSession(workout_plan=workout_plan)
    user.save()
    logger.info("session started for %s (%d exercises)", user.phone_number, len(workout_plan))
    return {"started": True, "exercise_count": len(workout_plan)}


def skill_log_set(user, exercise, reps, weight) -> dict:
    if not user.active_session:
        return {"error": "No active session. Start one first."}

    record = {
        "exercise": exercise,
        "reps": reps,
        "weight": weight,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    user.active_session.completed_sets.append(record)

    # Advance set/exercise index
    session = user.active_session
    plan = session.workout_plan or []
    if plan and session.current_exercise_index < len(plan):
        current_ex = plan[session.current_exercise_index]
        total_sets = int(current_ex.get("sets", 3))
        if session.current_set_index + 1 < total_sets:
            session.current_set_index += 1
        elif session.current_exercise_index + 1 < len(plan):
            session.current_exercise_index += 1
            session.current_set_index = 0

    user.save()
    set_number = len([s for s in user.active_session.completed_sets if s.get("exercise") == exercise])
    logger.info("set logged: %s %dx%s for %s", exercise, reps, weight, user.phone_number)
    return {"logged": True, "exercise": exercise, "reps": reps, "weight": weight, "set_number": set_number}


def skill_start_rest(user, seconds=90) -> dict:
    from tasks.rest_timer import send_rest_over

    seconds = int(seconds)
    enqueued_at = datetime.now(timezone.utc).isoformat()

    task = send_rest_over.apply_async(
        args=[user.phone_number, enqueued_at],
        countdown=seconds,
    )
    if user.active_session:
        user.active_session.rest_timer_task_id = task.id
        user.save()

    logger.info("rest timer set: %ds for %s (task %s)", seconds, user.phone_number, task.id)
    return {"timer_started": True, "seconds": seconds}


def skill_advance_exercise(user) -> dict:
    if not user.active_session:
        return {"error": "No active session."}

    session = user.active_session
    plan = session.workout_plan or []
    if not plan:
        return {"error": "No workout plan in the active session."}

    if session.current_exercise_index + 1 < len(plan):
        session.current_exercise_index += 1
        session.current_set_index = 0
        user.save()
        new_exercise = plan[session.current_exercise_index]
        return {"advanced": True, "new_exercise": new_exercise}
    return {"advanced": False, "reason": "Already on last exercise."}


def skill_end_session(user, duration_minutes, summary="") -> dict:
    if not user.active_session:
        return {"error": "No active session to end."}

    from apps.users.models import WorkoutSession, ExerciseRecord, SetRecord

    completed = user.active_session.completed_sets
    exercise_map: dict[str, list] = {}
    for s in completed:
        name = s.get("exercise", "Unknown")
        exercise_map.setdefault(name, []).append(s)

    exercises = []
    prs_updated = []
    for name, sets in exercise_map.items():
        set_records = [SetRecord(reps=s.get("reps", 0), weight=s.get("weight", 0)) for s in sets]
        max_weight = max((s.get("weight", 0) for s in sets), default=0)
        current_pr = user.prs.get(name, 0)
        if max_weight > current_pr:
            user.prs[name] = max_weight
            prs_updated.append({"exercise": name, "old_pr": current_pr, "new_pr": max_weight})
        exercises.append(ExerciseRecord(name=name, sets=set_records))

    session_doc = WorkoutSession(
        date=user.active_session.started_at,
        exercises=exercises,
        duration_minutes=int(duration_minutes),
        notes=summary,
    )

    user.sessions.append(session_doc)
    user.total_sessions += 1
    user.active_session = None
    user.save()

    logger.info("session ended for %s (%d exercises)", user.phone_number, len(exercises))
    return {
        "ended": True,
        "total_exercises": len(exercises),
        "total_sets": len(completed),
        "prs_updated": prs_updated,
    }


# ── Skill Dispatcher ─────────────────────────────────────────────────

SKILL_MAP = {
    "get_profile": skill_get_profile,
    "get_workout_history": skill_get_workout_history,
    "get_prs": skill_get_prs,
    "get_active_session": skill_get_active_session,
    "update_memory": skill_update_memory,
    "start_session": skill_start_session,
    "log_set": skill_log_set,
    "start_rest": skill_start_rest,
    "advance_exercise": skill_advance_exercise,
    "end_session": skill_end_session,
}


def execute_skill(user, tool_name: str, arguments: dict) -> str:
    """Execute a skill and return JSON string result for the tool message."""
    fn = SKILL_MAP.get(tool_name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = fn(user, **arguments)
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.error("Skill execution error (%s): %s", tool_name, exc)
        return json.dumps({"error": str(exc)})
