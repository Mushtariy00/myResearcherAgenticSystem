"""The registered datasets (the ``datasets`` table) as the datasets page shows them.

A dataset row keeps its data contract and the page's details as JSON (agentic_db.models.Dataset),
written by a migration or an admin, so a value of the wrong type reads as missing rather than
failing the page. Postgres's JSONB keeps object keys in its own order, so the splits are put back
in the order people read them: train, val, test, then any others by name.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.schemas import DataContractOut, DatasetOut, DatasetSplitOut
from agentic_core.gpu_jobs import DATA_ROOT
from agentic_db.models import Dataset

TRAIN_SPLIT = "train"
_SPLIT_ORDER = (TRAIN_SPLIT, "val", "test")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _count(value: object) -> int | None:
    """A whole number of at least 0 (JSON booleans are not numbers here)."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def split_counts(details: object) -> dict[str, int]:
    """The dataset's splits (``details.splits``: name to sample count), in reading order."""
    splits: dict[str, int] = {}
    for name, value in _mapping(_mapping(details).get("splits")).items():
        count = _count(value)
        if isinstance(name, str) and count is not None:
            splits[name] = count
    order = {name: index for index, name in enumerate(_SPLIT_ORDER)}
    return dict(sorted(splits.items(), key=lambda item: (order.get(item[0], len(order)), item[0])))


def _contract(contract: object) -> DataContractOut:
    values = _mapping(contract)
    return DataContractOut(
        inputs=_text(values.get("inputs")),
        targets=_text(values.get("targets")),
        units=_optional_text(values.get("units")),
        valid_range=_optional_text(values.get("valid_range")),
        missing_values=_optional_text(values.get("missing_values")),
        evaluation=_optional_text(values.get("evaluation")),
    )


def dataset_out(dataset: Dataset) -> DatasetOut:
    details = _mapping(dataset.details)
    splits = split_counts(details)
    tasks = details.get("tasks")
    return DatasetOut(
        id=dataset.name,
        name=dataset.title,
        version=dataset.version,
        tasks=[task for task in tasks if isinstance(task, str)] if isinstance(tasks, list) else [],
        modality=_text(details.get("modality")),
        scenes=_text(details.get("scenes")),
        description=_text(details.get("description")),
        width=_count(details.get("width")) or 0,
        height=_count(details.get("height")) or 0,
        samples=sum(splits.values()),
        splits=[DatasetSplitOut(name=name, samples=count) for name, count in splits.items()],
        size_bytes=_count(details.get("size_bytes")),
        license=_text(details.get("license")),
        homepage=_optional_text(details.get("homepage")),
        mount_path=f"{DATA_ROOT}/{dataset.name}",  # where the executor mounts it, read-only
        checksum_sha256=dataset.checksum,
        registered_at=dataset.created_at,
        contract=_contract(dataset.contract),
        demo=False,
    )


async def enabled_datasets(db: AsyncSession) -> list[DatasetOut]:
    """The datasets GPU jobs can mount: the enabled rows, by name."""
    rows = await db.scalars(select(Dataset).where(Dataset.enabled.is_(True)).order_by(Dataset.name))
    return [dataset_out(row) for row in rows]
