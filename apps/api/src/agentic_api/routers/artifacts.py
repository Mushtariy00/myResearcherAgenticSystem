"""Run artifacts: files derived from the run's latest stage outputs, streamed as attachments."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.artifacts import (
    ARTIFACT_STAGES,
    Artifact,
    coding_artifacts,
    experiment_artifacts,
    file_prefix,
    parse_artifact_id,
    writing_artifacts,
)
from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, load_run
from agentic_api.demo import is_demo_reason
from agentic_api.files import binary_response, file_response
from agentic_api.schemas import ArtifactList, ArtifactOut
from agentic_core.enums import StageStatus
from agentic_core.schemas import (
    CodingOutput,
    ExperimentOutput,
    LiteratureOutput,
    WritingOutput,
    validate_stage_output,
)
from agentic_core.stages import Stage
from agentic_db.models import StageOutput, StageRun

router = APIRouter(prefix="/api/v1", tags=["artifacts"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]
ArtifactId = Annotated[str, Path(min_length=1, max_length=64)]
_STAGE_NAMES = frozenset(stage.value for stage in ARTIFACT_STAGES)


async def _latest_outputs(db: AsyncSession, run_id: uuid.UUID) -> dict[Stage, StageOutput]:
    """Per stage, the newest version of the latest attempt that has an output. Invalidated
    attempts (a retry of an earlier stage made them stale) are skipped."""
    rows = await db.execute(
        select(StageOutput, StageRun.stage)
        .join(StageRun, StageRun.id == StageOutput.stage_run_id)
        .where(
            StageRun.run_id == run_id,
            StageRun.status != StageStatus.INVALIDATED,
            StageRun.stage.in_([Stage.LITERATURE.value, *_STAGE_NAMES]),
        )
        .order_by(StageRun.attempt.desc(), StageOutput.version.desc())
    )
    latest: dict[Stage, StageOutput] = {}
    for output, stage in rows:
        latest.setdefault(Stage(stage), output)
    return latest


def _literature(output: StageOutput | None) -> LiteratureOutput | None:
    if output is None:
        return None
    try:
        return LiteratureOutput.model_validate(output.data)
    except ValidationError:
        return None


def _derive(
    stage: Stage, output: StageOutput, run_id: uuid.UUID, literature: LiteratureOutput | None
) -> list[Artifact]:
    """The artifacts of one output; none when it doesn't pass its stage's schema (such as the
    placeholders of stages that aren't built yet)."""
    try:
        data = validate_stage_output(stage, output.data)
    except ValidationError:
        return []
    prefix = file_prefix(run_id)
    if isinstance(data, CodingOutput):
        return coding_artifacts(output.id, data, prefix=prefix, created_at=output.created_at)
    if isinstance(data, ExperimentOutput):
        return experiment_artifacts(output.id, data, prefix=prefix)
    if isinstance(data, WritingOutput):
        return writing_artifacts(output.id, data, literature, prefix=prefix)
    return []


@router.get("/runs/{run_id}/artifacts", operation_id="listRunArtifacts")
async def list_run_artifacts(run_id: uuid.UUID, user: User, db: Db) -> ArtifactList:
    """Every file the run's latest coding, experiment and writing outputs make; anyone who can
    open the run may download them."""
    await load_run(db, run_id, user)
    latest = await _latest_outputs(db, run_id)
    literature_output = latest.get(Stage.LITERATURE)
    literature = _literature(literature_output)
    literature_demo = literature_output is not None and is_demo_reason(
        literature_output.degraded_reason
    )
    items: list[ArtifactOut] = []
    for stage in ARTIFACT_STAGES:
        output = latest.get(stage)
        if output is None:
            continue
        demo = is_demo_reason(output.degraded_reason)
        for artifact in _derive(stage, output, run_id, literature):
            items.append(
                ArtifactOut(
                    id=artifact.id,
                    stage=stage.value,
                    kind=artifact.kind,
                    filename=artifact.filename,
                    path=artifact.path,
                    media_type=artifact.media_type,
                    size_bytes=len(artifact.content),
                    sha256=artifact.sha256,
                    stage_output_id=output.id,
                    version=output.version,
                    created_at=output.created_at,
                    # References carry the literature output's paper metadata too.
                    demo=demo or (artifact.kind == "references" and literature_demo),
                )
            )
    return ArtifactList(run_id=run_id, items=items, demo=any(item.demo for item in items))


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "artifact.not_found")


@router.get(
    "/artifacts/{artifact_id}",
    operation_id="getArtifact",
    response_class=StreamingResponse,
    responses=binary_response(
        "application/zip", "text/plain", "text/csv", "text/markdown", "application/x-bibtex"
    ),
)
async def get_artifact(artifact_id: ArtifactId, user: User, db: Db) -> StreamingResponse:
    """Download one artifact. The id names a stage output and an item of it; both are checked
    again here, and the caller must be able to open the run the output belongs to."""
    parsed = parse_artifact_id(artifact_id)
    if parsed is None:
        raise _not_found()
    output = await db.get(StageOutput, parsed[0])
    stage_run = await db.get(StageRun, output.stage_run_id) if output else None
    if output is None or stage_run is None or stage_run.stage not in _STAGE_NAMES:
        raise _not_found()
    try:
        await load_run(db, stage_run.run_id, user)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            raise _not_found() from None  # the same answer as for an id that doesn't exist
        raise
    stage = Stage(stage_run.stage)
    literature = None
    if stage == Stage.WRITING:  # the references need the run's papers
        latest = await _latest_outputs(db, stage_run.run_id)
        literature = _literature(latest.get(Stage.LITERATURE))
    derived = _derive(stage, output, stage_run.run_id, literature)
    artifact = next((item for item in derived if item.id == artifact_id), None)
    if artifact is None:
        raise _not_found()
    return file_response(
        artifact.content,
        media_type=artifact.media_type,
        filename=artifact.filename,
        disposition="attachment",
    )
