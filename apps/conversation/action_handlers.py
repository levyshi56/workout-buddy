"""
Action dispatcher.

The LLM returns a structured action alongside its user-facing message.
This module routes each action type to the appropriate handler.
Adding a new action = add a new handler function + register it in HANDLERS.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def handle_start_rest(user, params: dict) -> None:
    """Enqueue a rest timer Celery task."""
    from tasks.rest_timer import send_rest_over

    seconds = int(params.get("seconds", 90))
    enqueued_at = datetime.now(timezone.utc).isoformat()

    task = send_rest_over.apply_async(
        args=[user.phone_number, enqueued_at],
        countdown=seconds,
    )
    if user.active_session:
        user.active_session.rest_timer_task_id = task.id
        user.save()

    logger.info("rest timer set: %ds for %s (task %s)", seconds, user.phone_number, task.id)


def handle_advance_set(user, params: dict) -> None:
    """Increment set/exercise index in the active session."""
    if not user.active_session:
        return

    session = user.active_session
    plan = session.workout_plan or []

    if not plan:
        return

    current_ex = plan[session.current_exercise_index] if session.current_exercise_index < len(plan) else None
    if not current_ex:
        return

    total_sets = int(current_ex.get("sets", 3))
    if session.current_set_index + 1 < total_sets:
        session.current_set_index += 1
    elif session.current_exercise_index + 1 < len(plan):
        session.current_exercise_index += 1
        session.current_set_index = 0

    user.save()


def handle_log_weight(user, params: dict) -> None:
    """Log a completed set into active_session.completed_sets."""
    if not user.active_session:
        return

    record = {
        "exercise": params.get("exercise", ""),
        "reps": params.get("reps", 0),
        "weight": params.get("weight", 0),
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    user.active_session.completed_sets.append(record)
    user.save()

    # Also advance the set index
    handle_advance_set(user, {})


def handle_end_session(user, params: dict) -> None:
    """
    Finalize the workout: save to history, update stats, clear active session.
    """
    if not user.active_session:
        return

    from apps.users.models import WorkoutSession, ExerciseRecord, SetRecord

    completed = user.active_session.completed_sets
    duration = int(params.get("duration_minutes", 0))

    # Group completed sets by exercise
    exercise_map: dict[str, list] = {}
    for s in completed:
        name = s.get("exercise", "Unknown")
        exercise_map.setdefault(name, []).append(s)

    exercises = []
    for name, sets in exercise_map.items():
        set_records = [SetRecord(reps=s.get("reps", 0), weight=s.get("weight", 0)) for s in sets]
        # Update PR if applicable
        max_weight = max((s.get("weight", 0) for s in sets), default=0)
        current_pr = user.prs.get(name, 0)
        if max_weight > current_pr:
            user.prs[name] = max_weight
        exercises.append(ExerciseRecord(name=name, sets=set_records))

    session_doc = WorkoutSession(
        date=user.active_session.started_at,
        exercises=exercises,
        duration_minutes=duration,
        notes=params.get("summary", ""),
    )

    user.sessions.append(session_doc)
    user.total_sessions += 1
    user.active_session = None
    user.save()

    logger.info("session ended for %s (%d exercises)", user.phone_number, len(exercises))


def handle_update_memory(user, params: dict) -> None:
    """Update a memory field on the user profile."""
    field = params.get("field", "")
    value = params.get("value", "")
    allowed_fields = {"goals", "equipment", "injuries", "preferences", "notes", "name"}
    if field in allowed_fields:
        setattr(user, field, value)
        user.save()
        logger.info("memory updated: %s.%s = %r", user.phone_number, field, value)


def handle_none(user, params: dict) -> None:
    pass


HANDLERS = {
    "start_rest": handle_start_rest,
    "advance_set": handle_advance_set,
    "log_weight": handle_log_weight,
    "end_session": handle_end_session,
    "update_memory": handle_update_memory,
    "none": handle_none,
}


def dispatch(user, action: dict) -> None:
    """Route an action dict to the appropriate handler."""
    action_type = action.get("type", "none")
    params = action.get("params", {})
    handler = HANDLERS.get(action_type, handle_none)
    try:
        handler(user, params)
    except Exception as exc:
        logger.error("action handler error (%s): %s", action_type, exc)
