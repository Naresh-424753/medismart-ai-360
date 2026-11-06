"""Encrypted-file storage: local disk by default, Google Cloud Storage when GCS_BUCKET is set.
Callers always pass already-encrypted bytes; the bucket never sees plaintext."""
import os

from ..config import settings


def _bucket():
    from google.cloud import storage  # imported lazily: only needed when GCS_BUCKET is set
    return storage.Client().bucket(settings.GCS_BUCKET)


def _key(user_id: str, did: str) -> str:
    return f"{user_id}/{did}.enc"


def put(user_id: str, did: str, data: bytes) -> None:
    if settings.GCS_BUCKET:
        _bucket().blob(_key(user_id, did)).upload_from_string(data, content_type="application/octet-stream")
        return
    folder = os.path.join(settings.UPLOAD_DIR, user_id)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, did + ".enc"), "wb") as f:
        f.write(data)


def get(user_id: str, did: str) -> bytes | None:
    """Returns None when the file does not exist."""
    if settings.GCS_BUCKET:
        blob = _bucket().blob(_key(user_id, did))
        return blob.download_as_bytes() if blob.exists() else None
    path = os.path.join(settings.UPLOAD_DIR, user_id, did + ".enc")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def delete(user_id: str, did: str) -> None:
    if settings.GCS_BUCKET:
        try:
            _bucket().blob(_key(user_id, did)).delete()
        except Exception:
            pass
        return
    try:
        os.remove(os.path.join(settings.UPLOAD_DIR, user_id, did + ".enc"))
    except OSError:
        pass
