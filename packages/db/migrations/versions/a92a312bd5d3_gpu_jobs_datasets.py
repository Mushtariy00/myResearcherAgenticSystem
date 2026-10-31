"""gpu jobs, datasets (registers nyu2)

Revision ID: a92a312bd5d3
Revises: 164cac3d30f1
Create Date: 2026-10-30 21:23:53.851415
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a92a312bd5d3"
down_revision: str | None = "164cac3d30f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The lab's NYU Depth V2 copy (main:data_contract.json, approved 2026-05-30). Its folder differs
# from machine to machine, so host_path stays NULL and the executor's ARP_DATASET_NYU2 names it.
NYU2 = {
    "name": "nyu2",
    "version": "2026.05",
    "title": "NYU Depth V2",
    "contract": {
        "inputs": "RGB uint8, 3x480x640",
        "targets": "Depth map float32, 1x480x640",
        "units": "metres",
        "valid_range": "above 0.001 m",
        "missing_values": "0 where the sensor returned no depth",
        "evaluation": "Every valid pixel of the full frame: RMSE, MAE and AbsRel",
    },
    "details": {
        "description": (
            "Indoor scenes recorded with a Microsoft Kinect. The lab's copy is the metric-ready "
            "H5 export: 50,688 training frames and 654 validation frames, each an aligned RGB "
            "image and a depth map in metres."
        ),
        "tasks": ["monocular_depth"],
        "modality": "RGB-D (Microsoft Kinect)",
        "scenes": "indoor",
        "width": 640,
        "height": 480,
        "splits": {"train": 50688, "val": 654, "test": 0},
        "size_bytes": None,
        "license": "Non-commercial research use (NYU Depth V2 terms)",
        "homepage": "https://cs.nyu.edu/~fergus/datasets/nyu_depth_v2.html",
    },
}


def upgrade() -> None:
    datasets = op.create_table(
        "datasets",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("host_path", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("checksum_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contract", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_datasets")),
    )
    op.create_table(
        "gpu_jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("stage_run_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "smoke",
                "train",
                name="gpujobkind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "starting",
                "running",
                "succeeded",
                "failed",
                "timeout",
                "cancelled",
                name="gpujobstatus",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("dataset", sa.String(length=64), nullable=False),
        sa.Column("code", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("container_id", sa.String(length=80), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("epochs_reported", sa.Integer(), server_default="0", nullable=False),
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("gpu_seconds", sa.Float(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("log_tail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset"], ["datasets.name"], name=op.f("fk_gpu_jobs_dataset_datasets")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_gpu_jobs_run_id_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stage_run_id"],
            ["stage_runs.id"],
            name=op.f("fk_gpu_jobs_stage_run_id_stage_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gpu_jobs")),
        sa.UniqueConstraint(
            "stage_run_id", "kind", "ordinal", name=op.f("uq_gpu_jobs_stage_run_id_kind_ordinal")
        ),
    )
    op.create_index("ix_gpu_jobs_run_id", "gpu_jobs", ["run_id"], unique=False)
    op.create_index(
        "ix_gpu_jobs_status_created", "gpu_jobs", ["status", "created_at"], unique=False
    )
    op.create_index("ix_gpu_jobs_user_status", "gpu_jobs", ["user_id", "status"], unique=False)
    op.bulk_insert(datasets, [NYU2])


def downgrade() -> None:
    op.drop_index("ix_gpu_jobs_user_status", table_name="gpu_jobs")
    op.drop_index("ix_gpu_jobs_status_created", table_name="gpu_jobs")
    op.drop_index("ix_gpu_jobs_run_id", table_name="gpu_jobs")
    op.drop_table("gpu_jobs")
    op.drop_table("datasets")
