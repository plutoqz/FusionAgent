from __future__ import annotations

from schemas.fusion import JobType


DEFAULT_ARTIFACT_REUSE_MAX_AGE_SECONDS = 24 * 60 * 60

# Conservative reuse windows by work type. Building fusion artifacts are usually
# more stable than road-state artifacts, which can change rapidly after a
# disaster event.
ARTIFACT_REUSE_MAX_AGE_BY_JOB_TYPE = {
    JobType.building.value: 3 * 24 * 60 * 60,
    JobType.road.value: 24 * 60 * 60,
}


def get_artifact_reuse_max_age_seconds(job_type: str | JobType) -> int:
    token = job_type.value if isinstance(job_type, JobType) else str(job_type).strip()
    if not token:
        return DEFAULT_ARTIFACT_REUSE_MAX_AGE_SECONDS
    return ARTIFACT_REUSE_MAX_AGE_BY_JOB_TYPE.get(token, DEFAULT_ARTIFACT_REUSE_MAX_AGE_SECONDS)
