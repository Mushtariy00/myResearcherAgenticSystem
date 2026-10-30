"""backfill the paper library

Revision ID: 0b2bff8fd54a
Revises: 8d4f2b6a1c37
Create Date: 2026-10-30 15:36:19.265498

Data only: fills ``papers`` and ``run_papers`` from the literature outputs written before the
literature stage recorded its papers there, so the library keeps every paper it showed.

- Each literature stage run contributes its latest output version: ``data->'papers'``
  (PaperRef objects in screening order) and ``data->'analyses'``. Outputs without a papers
  array, such as plans from before the search existed, contribute nothing.
- One ``papers`` row per paper id that has none yet (key = paper id), from the newest output
  that lists it. Its DOI (lower case) and arXiv id (without a version) are kept unless another
  paper holds them already. ``demo`` is set when an output listing it is generated: some
  version of that stage run has the degraded reason ``literature.demo_search``, ``stage.demo``
  or ``stage.placeholder`` (a reviewer's edited version has none, but its papers are still
  generated). ``pdf_status`` is ``abstract_only`` for a paper that had no PDF. Otherwise a
  generated paper is ``available`` without a file, as the demo seed records them, so the API
  serves its generated preview; any other paper is ``unknown`` until the worker looks.
- One ``run_papers`` row per stage run and paper: rank = position in the list, score and
  relevance = the screening relevance, the decision and its reason, and the output's analysis
  of the paper. ``created_at`` is the output's, so the library's "last seen" stays as it was.
  The output does not say which query found a paper, so ``hits`` holds one entry with the
  paper's source, its position in the list and a ``backfill`` marker.

Rows that exist are left as they are, so the upgrade can run again and does nothing on an
empty database. The downgrade deletes the ``run_papers`` rows with the marker and the papers
nothing else uses (no other ``run_papers`` row, no parsed text, no stored file).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0b2bff8fd54a"
down_revision: str | None = "8d4f2b6a1c37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKFILL = """
WITH latest AS (
    SELECT DISTINCT ON (o.stage_run_id)
        o.stage_run_id,
        s.run_id,
        o.data,
        o.created_at,
        EXISTS (
            SELECT FROM stage_outputs AS generated
            WHERE generated.stage_run_id = o.stage_run_id
                AND generated.degraded_reason
                    IN ('literature.demo_search', 'stage.demo', 'stage.placeholder')
        ) AS demo
    FROM stage_outputs AS o
    JOIN stage_runs AS s ON s.id = o.stage_run_id
    WHERE s.stage = 'literature'
    ORDER BY o.stage_run_id, o.version DESC
),
appearance AS (
    SELECT
        latest.stage_run_id,
        latest.run_id,
        latest.created_at,
        latest.demo,
        element.paper ->> 'paper_id' AS key,
        element.paper,
        element.position,
        CASE WHEN jsonb_typeof(element.paper -> 'relevance') = 'number'
            THEN (element.paper ->> 'relevance')::double precision END AS relevance,
        (
            SELECT analysis.value
            FROM jsonb_array_elements(
                CASE WHEN jsonb_typeof(latest.data -> 'analyses') = 'array'
                    THEN latest.data -> 'analyses' ELSE '[]' END
            ) WITH ORDINALITY AS analysis (value, position)
            WHERE jsonb_typeof(analysis.value) = 'object'
                AND analysis.value ->> 'paper_id' = element.paper ->> 'paper_id'
            ORDER BY analysis.position
            LIMIT 1
        ) AS analysis
    FROM latest
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(latest.data -> 'papers') = 'array'
            THEN latest.data -> 'papers' ELSE '[]' END
    ) WITH ORDINALITY AS element (paper, position)
    WHERE jsonb_typeof(element.paper -> 'paper_id') = 'string'
        AND length(element.paper ->> 'paper_id') BETWEEN 1 AND 300
        AND jsonb_typeof(element.paper -> 'title') = 'string'
),
newest AS (
    SELECT DISTINCT ON (key)
        key,
        paper,
        bool_or(demo) OVER (PARTITION BY key) AS demo,
        CASE WHEN jsonb_typeof(paper -> 'doi') = 'string'
            AND length(btrim(paper ->> 'doi')) BETWEEN 1 AND 255
            THEN lower(btrim(paper ->> 'doi')) END AS doi,
        CASE WHEN jsonb_typeof(paper -> 'arxiv_id') = 'string'
            AND length(btrim(paper ->> 'arxiv_id')) BETWEEN 1 AND 64
            THEN nullif(regexp_replace(btrim(paper ->> 'arxiv_id'), 'v[0-9]+$', ''), '')
            END AS arxiv_id
    FROM appearance
    ORDER BY key, created_at DESC, stage_run_id DESC, position
),
candidate AS (
    -- Two paper ids may share a DOI or an arXiv id: the first in key order keeps it.
    SELECT
        newest.*,
        row_number() OVER (PARTITION BY doi ORDER BY key) AS doi_rank,
        row_number() OVER (PARTITION BY arxiv_id ORDER BY key) AS arxiv_rank
    FROM newest
    WHERE NOT EXISTS (SELECT FROM papers WHERE papers.key = newest.key)
),
inserted AS (
    INSERT INTO papers (
        key, doi, arxiv_id, title, authors, year, venue, abstract, citation_count, url, demo,
        pdf_status
    )
    SELECT
        key,
        CASE WHEN doi_rank = 1
            AND NOT EXISTS (SELECT FROM papers WHERE papers.doi = candidate.doi)
            THEN doi END,
        CASE WHEN arxiv_rank = 1
            AND NOT EXISTS (SELECT FROM papers WHERE papers.arxiv_id = candidate.arxiv_id)
            THEN arxiv_id END,
        paper ->> 'title',
        CASE WHEN jsonb_typeof(paper -> 'authors') = 'array'
            THEN paper -> 'authors' ELSE '[]' END,
        -- Nested CASEs: a cast in the same WHEN as the type check could run before it.
        CASE WHEN jsonb_typeof(paper -> 'year') = 'number' THEN
            CASE WHEN (paper ->> 'year')::numeric BETWEEN 1000 AND 2100
                THEN (paper ->> 'year')::numeric::integer END
        END,
        CASE WHEN jsonb_typeof(paper -> 'venue') = 'string' THEN paper ->> 'venue' END,
        CASE WHEN jsonb_typeof(paper -> 'abstract') = 'string' THEN paper ->> 'abstract' END,
        CASE WHEN jsonb_typeof(paper -> 'citation_count') = 'number' THEN
            CASE WHEN (paper ->> 'citation_count')::numeric BETWEEN 0 AND 2147483647
                THEN (paper ->> 'citation_count')::numeric::integer END
        END,
        CASE WHEN jsonb_typeof(paper -> 'url') = 'string' THEN paper ->> 'url' END,
        demo,
        CASE
            WHEN paper -> 'pdf_available' = 'false' THEN 'abstract_only'
            WHEN demo THEN 'available'
            ELSE 'unknown'
        END
    FROM candidate
    ON CONFLICT (key) DO NOTHING
    RETURNING id, key
),
known AS (
    -- The statement's snapshot of papers lacks the rows inserted above; RETURNING has them.
    SELECT id, key FROM inserted
    UNION ALL
    SELECT id, key FROM papers WHERE key IN (SELECT key FROM appearance)
)
INSERT INTO run_papers (
    stage_run_id, paper_id, run_id, hits, rank, score, relevance, decision, decision_reason,
    analysis, created_at
)
SELECT DISTINCT ON (appearance.stage_run_id, known.id)
    appearance.stage_run_id,
    known.id,
    appearance.run_id,
    jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
        'source', CASE WHEN jsonb_typeof(appearance.paper -> 'source') = 'string'
            THEN appearance.paper ->> 'source' END,
        'position', appearance.position,
        'backfill', '0b2bff8fd54a'
    ))),
    appearance.position,
    coalesce(appearance.relevance, 0),
    appearance.relevance,
    CASE WHEN appearance.paper ->> 'decision' IN ('include', 'maybe', 'exclude')
        THEN appearance.paper ->> 'decision' END,
    CASE WHEN jsonb_typeof(appearance.paper -> 'decision_reason') = 'string'
        THEN appearance.paper ->> 'decision_reason' END,
    appearance.analysis,
    appearance.created_at
FROM appearance
JOIN known ON known.key = appearance.key
ORDER BY appearance.stage_run_id, known.id, appearance.position
ON CONFLICT (stage_run_id, paper_id) DO NOTHING
"""

# Deleting a paper deletes its run_papers rows too (ON DELETE CASCADE).
FORGET_PAPERS = """
DELETE FROM papers
WHERE EXISTS (
        SELECT FROM run_papers
        WHERE run_papers.paper_id = papers.id
            AND run_papers.hits @> '[{"backfill": "0b2bff8fd54a"}]'
    )
    AND NOT EXISTS (
        SELECT FROM run_papers
        WHERE run_papers.paper_id = papers.id
            AND NOT (run_papers.hits @> '[{"backfill": "0b2bff8fd54a"}]')
    )
    AND NOT EXISTS (SELECT FROM paper_texts WHERE paper_texts.paper_id = papers.id)
    AND papers.pdf_sha256 IS NULL
"""

FORGET_RUN_PAPERS = """
DELETE FROM run_papers WHERE hits @> '[{"backfill": "0b2bff8fd54a"}]'
"""


def upgrade() -> None:
    op.execute(BACKFILL)


def downgrade() -> None:
    op.execute(FORGET_PAPERS)
    op.execute(FORGET_RUN_PAPERS)
