"""nyu2 2026.10: the copy with the training split's depth in metres

Revision ID: 5e8b1f0c9d42
Revises: a92a312bd5d3
Create Date: 2026-10-31 02:10:00.000000

The lab's NYU2 export held its training depths as 8-bit PNG values divided by 1000 (median 0.076
against 2.75 m for validation), so every metric of a model trained on it was meaningless.
`make nyu2-fix` (scripts/nyu2-fix-depth.py) makes a copy with them in metres; version 2026.10 is
that copy, and ARP_DATASET_NYU2 points at it. The harness still checks the units of every job's
splits, so a machine still on the old export is warned about it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e8b1f0c9d42"
down_revision: str | None = "a92a312bd5d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DESCRIPTION_2026_10 = (
    "Indoor scenes recorded with a Microsoft Kinect. The lab's copy is the metric-ready H5 export "
    "with its training depths converted to metres (make nyu2-fix): 50,688 training frames and "
    "654 validation frames, each an aligned RGB image and a depth map in metres."
)
DESCRIPTION_2026_05 = (
    "Indoor scenes recorded with a Microsoft Kinect. The lab's copy is the metric-ready "
    "H5 export: 50,688 training frames and 654 validation frames, each an aligned RGB "
    "image and a depth map in metres."
)


def _set(version: str, description: str) -> None:
    op.execute(
        sa.text(
            "UPDATE datasets SET version = :version, checksum = NULL, checksum_at = NULL, "
            "details = jsonb_set(details, '{description}', to_jsonb(CAST(:description AS text))), "
            "updated_at = now() WHERE name = 'nyu2'"
        ).bindparams(version=version, description=description)
    )


def upgrade() -> None:
    _set("2026.10", DESCRIPTION_2026_10)


def downgrade() -> None:
    _set("2026.05", DESCRIPTION_2026_05)
