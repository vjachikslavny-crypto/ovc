"""One owner contract, including offline mode. Orphans require explicit repair."""
from fastapi import HTTPException
from sqlalchemy import and_

from app.db.models import FileAsset, Note


def is_owned(obj, user_id) -> bool:
    return bool(obj is not None and user_id and obj.user_id == user_id
                and not getattr(obj, "tombstone", False))


def owned_notes_filter(user_id):
    """The query equivalent of the live-note ownership contract."""
    return and_(Note.user_id == user_id, Note.user_id.isnot(None), Note.tombstone.is_(False))


def require_note_owner(note, user_id):
    if not is_owned(note, user_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return note


def get_owned_note(session, note_id, user_id):
    return require_note_owner(session.get(Note, note_id), user_id)


def get_owned_file(session, file_id, user_id):
    asset = session.get(FileAsset, file_id)
    if not is_owned(asset, user_id):
        raise HTTPException(status_code=404, detail="File not found")
    if asset.note_id and not is_owned(session.get(Note, asset.note_id), user_id):
        raise HTTPException(status_code=404, detail="File not found")
    return asset
