"""Thin wrapper around Votum's Supabase instance for task suggestions."""

from loguru import logger

from config import settings


def _client():
    from supabase import create_client
    return create_client(settings.VOTUM_SUPABASE_URL, settings.VOTUM_SUPABASE_KEY)


def is_task_extracted(email_id: str) -> bool:
    """Return True if tasks have already been suggested for this email_id."""
    try:
        res = _client().table("votum_suggested_tasks").select("id").eq("email_id", email_id).limit(1).execute()
        return len(res.data) > 0
    except Exception as exc:
        logger.warning(f"Supabase is_task_extracted check failed for {email_id}: {exc}")
        return False


def save_suggested_tasks(tasks: list[dict], email_id: str, user_id: str, workspace_id: str) -> None:
    """Insert extracted tasks into votum_suggested_tasks."""
    rows = [
        {"task_details": task, "user_id": user_id, "email_id": email_id, "workspace_id": workspace_id}
        for task in tasks
    ]
    try:
        _client().table("votum_suggested_tasks").insert(rows).execute()
        logger.info(f"Saved {len(rows)} suggested task(s) for email {email_id}")
    except Exception as exc:
        logger.error(f"Supabase save_suggested_tasks failed for {email_id}: {exc}")
        raise
