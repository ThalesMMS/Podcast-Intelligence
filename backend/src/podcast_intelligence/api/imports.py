from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from podcast_intelligence.dependencies import AuthDep, RegistryDep, SessionDep
from podcast_intelligence.domain.errors import ConflictError, NotFoundError
from podcast_intelligence.enums import JobStatus, StepStatus
from podcast_intelligence.models import ProcessingJob
from podcast_intelligence.schemas import (
    ImportRequest,
    ImportResponse,
    JobResponse,
    UploadInitiateRequest,
    UploadInitiateResponse,
)
from podcast_intelligence.services.imports import ImportService, enqueue_job_dispatch

router = APIRouter(tags=["imports"])


@router.post("/uploads", response_model=UploadInitiateResponse)
def initiate_upload(
    request: UploadInitiateRequest,
    auth: AuthDep,
    session: SessionDep,
    registry: RegistryDep,
) -> UploadInitiateResponse:
    return ImportService(session, registry.object_store, registry.settings).initiate_upload(
        auth.workspace_id, request
    )


@router.post("/imports", response_model=ImportResponse, status_code=status.HTTP_202_ACCEPTED)
def create_import(
    request: ImportRequest,
    auth: AuthDep,
    session: SessionDep,
    registry: RegistryDep,
) -> ImportResponse:
    response = ImportService(session, registry.object_store, registry.settings).create_import(
        auth.workspace_id, request
    )
    return response


def _job(session: SessionDep, workspace_id: uuid.UUID, job_id: uuid.UUID) -> ProcessingJob:
    job = session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.workspace_id == workspace_id,
        )
        .options(selectinload(ProcessingJob.steps))
    )
    if job is None:
        raise NotFoundError("Processing job not found")
    return job


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: uuid.UUID, auth: AuthDep, session: SessionDep) -> ProcessingJob:
    return _job(session, auth.workspace_id, job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: uuid.UUID, auth: AuthDep, session: SessionDep) -> ProcessingJob:
    job = _job(session, auth.workspace_id, job_id)
    if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
        raise ConflictError(f"Job cannot be cancelled from status {job.status.value}")
    job.status = JobStatus.CANCELLED
    session.commit()
    return _job(session, auth.workspace_id, job_id)


@router.post(
    "/jobs/{job_id}/retry", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED
)
def retry_job(job_id: uuid.UUID, auth: AuthDep, session: SessionDep) -> ProcessingJob:
    job = _job(session, auth.workspace_id, job_id)
    if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
        raise ConflictError("Only failed or cancelled jobs can be retried")
    job.status = JobStatus.QUEUED
    job.error_code = None
    job.error_message = None
    job.completed_at = None
    for step in job.steps:
        if step.status == StepStatus.FAILED:
            step.status = StepStatus.PENDING
            step.error_message = None
            step.completed_at = None
    enqueue_job_dispatch(session, job.id)
    session.commit()
    return _job(session, auth.workspace_id, job_id)
