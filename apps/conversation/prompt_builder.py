"""
Builds the context dict passed to the LLM provider.
Keeps the LLM layer decoupled from MongoDB models.
"""
import json
from apps.users.models import UserProfile


def build_context(user: UserProfile) -> dict:
    """
    Returns a context dict with:
      - memory: compact text summary of user profile
      - recent_sessions: summary of last 3 sessions
      - active_session: JSON-serializable dict of current session state (or None)
    """
    context: dict = {
        "memory": user.memory_summary(),
        "recent_sessions": user.recent_sessions_summary(n=3),
        "active_session": None,
        "conversation_history": [
            {"role": msg.role, "content": msg.content}
            for msg in user.conversation_history
        ],
    }

    if user.active_session:
        s = user.active_session
        plan = s.workout_plan or []
        current_ex = plan[s.current_exercise_index] if s.current_exercise_index < len(plan) else None
        context["active_session"] = {
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "total_exercises": len(plan),
            "current_exercise_index": s.current_exercise_index,
            "current_set_index": s.current_set_index,
            "current_exercise": current_ex,
            "completed_sets_count": len(s.completed_sets or []),
        }

    return context
