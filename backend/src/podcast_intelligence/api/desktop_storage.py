from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Response, UploadFile, status
from fastapi.responses import FileResponse

from podcast_intelligence.adapters.object_store.local import LocalObjectStore
from podcast_intelligence.dependencies import RegistryDep, SettingsDep
from podcast_intelligence.domain.errors import MediaValidationError, NotFoundError

router = APIRouter(tags=["desktop-storage"])


def _local_store(registry: RegistryDep) -> LocalObjectStore:
    store = registry.object_store
    if not isinstance(store, LocalObjectStore):
        raise MediaValidationError("Local storage endpoint is unavailable")
    return store


@router.post("/desktop-storage/upload/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def upload_local_object(
    token: str,
    file: UploadFile,
    registry: RegistryDep,
    settings: SettingsDep,
) -> Response:
    store = _local_store(registry)
    claims = store.verify_token(token, "put")
    expected_size = int(claims["size"])
    expected_content_type = str(claims["content_type"])
    received_content_type = (file.content_type or "").lower()
    if received_content_type != expected_content_type.lower():
        raise MediaValidationError("Uploaded media type does not match the initiated upload")

    settings.processing_temp_dir.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    received = 0
    try:
        with NamedTemporaryFile(
            prefix="desktop-upload-",
            suffix=".part",
            dir=settings.processing_temp_dir,
            delete=False,
        ) as target:
            temporary_path = Path(target.name)
            while chunk := await file.read(1024 * 1024):
                received += len(chunk)
                if received > expected_size:
                    raise MediaValidationError("Uploaded file exceeds its declared size")
                target.write(chunk)
        if received != expected_size:
            raise MediaValidationError("Uploaded file is incomplete")
        store.write_uploaded_file(
            object_key=str(claims["key"]),
            source=temporary_path,
            content_type=expected_content_type,
            expected_size_bytes=expected_size,
        )
        temporary_path = None
    finally:
        await file.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/desktop-storage/files/{token}")
def get_local_object(token: str, registry: RegistryDep) -> FileResponse:
    store = _local_store(registry)
    path, metadata = store.local_path_for_token(token)
    return FileResponse(
        path,
        media_type=metadata.get("content_type") or "application/octet-stream",
        filename=None,
        content_disposition_type="inline",
    )


@router.post("/desktop/shutdown", include_in_schema=False)
def desktop_shutdown(registry: RegistryDep) -> dict[str, bool]:
    if not registry.settings.desktop_mode:
        raise NotFoundError("Desktop runtime is not active")
    from podcast_intelligence.desktop.runtime import request_shutdown

    return {"accepted": request_shutdown()}
