from datetime import datetime
from .models import UserProfile, ActiveSession


def get_or_create_user(phone_number: str) -> UserProfile:
    """Look up user by phone number, creating a new profile if not found."""
    user = UserProfile.objects(phone_number=phone_number).first()
    if not user:
        user = UserProfile(phone_number=phone_number)
        user.save()
    return user


def update_last_message_time(user: UserProfile) -> None:
    """Stamp the current time as last_user_message_at on the active session."""
    if user.active_session is None:
        user.active_session = ActiveSession()
    user.active_session.last_user_message_at = datetime.utcnow()
    user.save()


def clear_active_session(user: UserProfile) -> None:
    user.active_session = None
    user.save()
