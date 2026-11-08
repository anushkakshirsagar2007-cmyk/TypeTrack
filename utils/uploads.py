import mimetypes
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import current_app


def _object_url(name):
    bucket = quote(current_app.config["SUPABASE_STORAGE_BUCKET"], safe="")
    object_name = quote(name, safe="")
    return f"{current_app.config['SUPABASE_URL']}/storage/v1/object/{bucket}/{object_name}"


def _storage_request(request):
    try:
        with urlopen(request, timeout=15) as response:
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Supabase Storage request failed (HTTP {exc.code}).") from exc
    except URLError as exc:
        raise RuntimeError("Could not connect to Supabase Storage.") from exc


def save_upload(file_storage, name):
    if current_app.config["UPLOAD_STORAGE_BACKEND"] == "supabase":
        key = current_app.config["SUPABASE_SERVICE_ROLE_KEY"]
        request = Request(
            _object_url(name),
            data=file_storage.read(),
            headers={
                "Authorization": f"Bearer {key}",
                "apikey": key,
                "Content-Type": file_storage.mimetype or "application/octet-stream",
                "x-upsert": "false",
            },
            method="POST",
        )
        _storage_request(request)
        return
    file_storage.save(os.path.join(current_app.config["UPLOAD_FOLDER"], name))


def read_upload(name):
    if current_app.config["UPLOAD_STORAGE_BACKEND"] == "supabase":
        key = current_app.config["SUPABASE_SERVICE_ROLE_KEY"]
        request = Request(
            _object_url(name),
            headers={"Authorization": f"Bearer {key}", "apikey": key},
        )
        return _storage_request(request)
    with open(os.path.join(current_app.config["UPLOAD_FOLDER"], name), "rb") as uploaded:
        return uploaded.read()


def upload_mimetype(name):
    return mimetypes.guess_type(name)[0] or "application/octet-stream"
