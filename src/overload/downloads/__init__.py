"""Sous-système de téléchargement d'OverLoad."""

from overload.downloads.bandwidth import BandwidthLimiter
from overload.downloads.duplicates import (
    DuplicateDetectedError,
    DuplicateMatch,
    DuplicatePolicy,
    DuplicateSource,
    detect_duplicate,
)
from overload.downloads.engine import DownloadCancelled, DownloadPaused, download_to
from overload.downloads.files import filename_from_url, plan_destination, sanitize_filename
from overload.downloads.manager import DownloadManager
from overload.downloads.models import BatchResult, ManagerSettings, RejectedLink, TaskSnapshot
from overload.downloads.state import TaskState, can_transition, transition
from overload.downloads.telemetry import ConnectionIssue, IssueKind, SpeedEstimator, classify_error
from overload.downloads.urls import parse_url_list, validate_direct_url

__all__ = [
    "BandwidthLimiter",
    "BatchResult",
    "ConnectionIssue",
    "DownloadCancelled",
    "DownloadManager",
    "DownloadPaused",
    "DuplicateDetectedError",
    "DuplicateMatch",
    "DuplicatePolicy",
    "DuplicateSource",
    "IssueKind",
    "ManagerSettings",
    "RejectedLink",
    "SpeedEstimator",
    "TaskSnapshot",
    "TaskState",
    "can_transition",
    "classify_error",
    "detect_duplicate",
    "download_to",
    "filename_from_url",
    "parse_url_list",
    "plan_destination",
    "sanitize_filename",
    "transition",
    "validate_direct_url",
]
