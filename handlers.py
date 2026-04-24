import bpy
import logging

logger = logging.getLogger(__name__)


def _mark_actions_fake_user(filepath: str) -> None:
    """Set fake user on every action so none are lost on file close."""
    for action in bpy.data.actions:
        if not action.use_fake_user:
            action.use_fake_user = True
            logger.debug("Marked action as fake user: %s", action.name)


def register() -> None:
    bpy.app.handlers.save_pre.append(_mark_actions_fake_user)


def unregister() -> None:
    bpy.app.handlers.save_pre.remove(_mark_actions_fake_user)
