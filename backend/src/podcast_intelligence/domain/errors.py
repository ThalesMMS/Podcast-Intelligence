from __future__ import annotations


class PodcastIntelligenceError(Exception):
    """Base class for expected domain/application errors."""

    code = "application_error"


class NotFoundError(PodcastIntelligenceError):
    code = "not_found"


class ConflictError(PodcastIntelligenceError):
    code = "conflict"


class SourceResolutionError(PodcastIntelligenceError):
    code = "source_resolution_failed"


class UnsafeRemoteURLError(SourceResolutionError):
    code = "unsafe_remote_url"


class MediaValidationError(PodcastIntelligenceError):
    code = "media_validation_failed"


class ProviderConfigurationError(PodcastIntelligenceError):
    code = "provider_configuration_error"


class ProviderExecutionError(PodcastIntelligenceError):
    code = "provider_execution_error"


class JobCancelledError(PodcastIntelligenceError):
    code = "job_cancelled"
