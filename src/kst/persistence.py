"""Persistence layer for KST battery runs.

Five tables compose the audit trail of a battery run:

- ``kst_runs``: one row per (target, run_id) covering lifecycle
  status, aggregation parameters, environment metadata.
- ``kst_sub_test_results``: one row per (run_id, construct_id, version)
  with the normalized score, CI, error class, and duration.
- ``kst_response_records``: one row per (run_id, request_id) carrying
  the full prompt + adapter response payload for replay.
- ``kst_telemetry_capture``: one row per request that produced a
  grey-box telemetry envelope (joined to kst_response_records via
  request_id).
- ``kst_score_aggregates``: one row per (run_id) snapshotting the
  composite index, weights, and statistical layer outputs.

Connection management follows the canonical pattern in
:class:`cct_v3.knowledge.postgres_backend.PostgresBackend`: psycopg2
``ThreadedConnectionPool``, environment-variable resolution, IAM-token
mode auto-detect when ``CAICI_DB_PASSWORD`` is empty. Schema bootstrap
is idempotent ``CREATE TABLE IF NOT EXISTS``.

Author: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Generator, Iterable, List, Optional, Sequence, Tuple

from kst.envelope import (
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
    GreyBoxTelemetry,
    Item,
    RunStatus,
    SubTestScore,
)
from kst.errors import PersistenceError, ResumeError
from kst.score import KSTIndexReport

logger = logging.getLogger(__name__)


WRITER_ID_DEFAULT = "stt_runner"


def _to_jsonb(payload: Any) -> str:
    """JSON-serialize a value for a JSONB column; falls back to a stringified repr."""
    try:
        return json.dumps(payload, default=str)
    except (TypeError, ValueError):
        return json.dumps({"__unserializable__": repr(payload)[:2000]})


SCHEMA_SQL: Tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS kst_runs (
        run_id          UUID PRIMARY KEY,
        target          TEXT NOT NULL,
        adapter_name    TEXT NOT NULL,
        capability      TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'pending',
        aggregation_mode TEXT NOT NULL DEFAULT 'weighted',
        weights         JSONB DEFAULT '{}'::jsonb,
        expected_constructs JSONB DEFAULT '[]'::jsonb,
        completed_constructs JSONB DEFAULT '[]'::jsonb,
        environment     JSONB DEFAULT '{}'::jsonb,
        notes           TEXT NOT NULL DEFAULT '',
        writer_id       TEXT NOT NULL DEFAULT 'stt_runner',
        started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finished_at     TIMESTAMPTZ
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_kst_runs_target_started
        ON kst_runs (target, started_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_kst_runs_status
        ON kst_runs (status)
    """,
    """
    CREATE TABLE IF NOT EXISTS kst_sub_test_results (
        id              BIGSERIAL PRIMARY KEY,
        run_id          UUID NOT NULL REFERENCES kst_runs(run_id) ON DELETE CASCADE,
        construct_id    TEXT NOT NULL,
        version         TEXT NOT NULL,
        test_id         TEXT NOT NULL,
        test_name       TEXT NOT NULL,
        score           DOUBLE PRECISION NOT NULL,
        max_score       DOUBLE PRECISION NOT NULL DEFAULT 100.0,
        normalized      DOUBLE PRECISION NOT NULL,
        n_items         INT NOT NULL DEFAULT 0,
        n_parse_errors  INT NOT NULL DEFAULT 0,
        ci_lower        DOUBLE PRECISION,
        ci_upper        DOUBLE PRECISION,
        ci_confidence   DOUBLE PRECISION,
        ci_n_bootstrap  INT,
        duration_s      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        sub_scores      JSONB DEFAULT '{}'::jsonb,
        per_stratum     JSONB DEFAULT '{}'::jsonb,
        trace           JSONB DEFAULT '{}'::jsonb,
        error           TEXT,
        traceback_text  TEXT,
        writer_id       TEXT NOT NULL DEFAULT 'stt_runner',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (run_id, construct_id, version)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_kst_sub_test_results_run
        ON kst_sub_test_results (run_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS kst_response_records (
        id              BIGSERIAL PRIMARY KEY,
        run_id          UUID NOT NULL REFERENCES kst_runs(run_id) ON DELETE CASCADE,
        construct_id    TEXT NOT NULL,
        version         TEXT NOT NULL,
        request_id      UUID NOT NULL,
        item_id         TEXT NOT NULL,
        prompt          TEXT NOT NULL,
        system_prompt   TEXT,
        request_payload JSONB DEFAULT '{}'::jsonb,
        response_text   TEXT NOT NULL DEFAULT '',
        response_payload JSONB DEFAULT '{}'::jsonb,
        model_id        TEXT NOT NULL DEFAULT '',
        status_code     INT NOT NULL DEFAULT 0,
        latency_s       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        attempts        INT NOT NULL DEFAULT 1,
        error           TEXT,
        writer_id       TEXT NOT NULL DEFAULT 'stt_runner',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (run_id, request_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_kst_response_records_run
        ON kst_response_records (run_id, construct_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS kst_telemetry_capture (
        id              BIGSERIAL PRIMARY KEY,
        run_id          UUID NOT NULL REFERENCES kst_runs(run_id) ON DELETE CASCADE,
        request_id      UUID NOT NULL,
        epistemic_state TEXT,
        confidence      DOUBLE PRECISION,
        calibration_score DOUBLE PRECISION,
        valence         DOUBLE PRECISION,
        arousal         DOUBLE PRECISION,
        seeking_drive   DOUBLE PRECISION,
        competence      DOUBLE PRECISION,
        meta_competence DOUBLE PRECISION,
        workspace_selectivity DOUBLE PRECISION,
        ags_state       TEXT,
        ags_drift_flag  BOOLEAN,
        factual_claim_audit JSONB,
        tool_routing    JSONB,
        voice           JSONB,
        raw             JSONB,
        writer_id       TEXT NOT NULL DEFAULT 'stt_runner',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_kst_telemetry_capture_run
        ON kst_telemetry_capture (run_id, request_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS kst_score_aggregates (
        run_id          UUID PRIMARY KEY REFERENCES kst_runs(run_id) ON DELETE CASCADE,
        index_score     DOUBLE PRECISION NOT NULL,
        ci_lower        DOUBLE PRECISION,
        ci_upper        DOUBLE PRECISION,
        ci_confidence   DOUBLE PRECISION,
        ci_n_bootstrap  INT,
        weights         JSONB NOT NULL DEFAULT '{}'::jsonb,
        aggregation_mode TEXT NOT NULL,
        reproducibility_alpha DOUBLE PRECISION,
        dif             JSONB,
        environment     JSONB DEFAULT '{}'::jsonb,
        notes           TEXT NOT NULL DEFAULT '',
        writer_id       TEXT NOT NULL DEFAULT 'stt_runner',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
)


class KSTPersistence:
    """PostgreSQL-backed persistence for the KST harness."""

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        dbname: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        pool_min: int = 1,
        pool_max: int = 4,
        connect_timeout: int = 5,
        writer_id: str = WRITER_ID_DEFAULT,
        ensure_schema: bool = True,
    ) -> None:
        try:
            import psycopg2  # noqa: F401
            import psycopg2.extras  # noqa: F401
            import psycopg2.pool  # noqa: F401
        except ImportError as exc:
            raise PersistenceError(
                "psycopg2 is required for KSTPersistence.",
                context={"exception": str(exc)},
            ) from exc
        import psycopg2  # type: ignore
        import psycopg2.extras  # type: ignore
        import psycopg2.pool  # type: ignore

        psycopg2.extras.register_uuid()

        resolved_host = host or os.environ.get("CAICI_DB_HOST", "localhost")
        resolved_port = int(
            port if port is not None else os.environ.get("CAICI_DB_PORT", "5432")
        )
        resolved_dbname = dbname or os.environ.get("CAICI_DB_NAME", "cct_wake")
        resolved_user = user or os.environ.get("CAICI_DB_USER", "cct")
        resolved_password = (
            password
            if password is not None
            else os.environ.get("CAICI_DB_PASSWORD", "")
        )

        auth_mode = "iam" if not resolved_password else "password"
        self._auth_mode = auth_mode

        if auth_mode == "iam":
            iam_user = (
                os.environ.get("CAICI_DB_IAM_USER")
                or resolved_user
            )
            suffix = ".gserviceaccount.com"
            if iam_user.endswith(suffix):
                iam_user = iam_user[: -len(suffix)]
            resolved_user = iam_user

        sslmode = os.environ.get("CAICI_DB_SSLMODE", "")
        dsn = (
            f"host={resolved_host} port={resolved_port} "
            f"dbname={resolved_dbname} user={resolved_user} "
            f"connect_timeout={connect_timeout}"
        )
        if auth_mode == "password":
            dsn += f" password={resolved_password}"
        else:
            dsn += " password=iam-token-placeholder"
        if sslmode:
            dsn += f" sslmode={sslmode}"

        logger.info(
            "stt.persistence auth_mode=%s pool=%d-%d %s:%d/%s",
            auth_mode, pool_min, pool_max, resolved_host, resolved_port,
            resolved_dbname,
        )

        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=pool_min, maxconn=pool_max, dsn=dsn
            )
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"Failed to create PostgreSQL connection pool: {exc}",
                context={"host": resolved_host, "port": resolved_port},
            ) from exc

        self.writer_id = writer_id

        if ensure_schema:
            try:
                self._ensure_schema()
            except Exception as exc:  # noqa: BLE001
                # In iam mode the role may not own existing tables; only
                # raise when the bootstrap really cannot proceed (the
                # tables do not exist AND we cannot create them).
                logger.warning(
                    "stt.persistence schema bootstrap warning: %s", exc,
                )

    # ── Connection management ────────────────────────────────────────

    @contextmanager
    def _conn(self) -> Generator[Any, None, None]:
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def close(self) -> None:
        try:
            self._pool.closeall()
        except Exception:  # noqa: BLE001
            logger.exception("stt.persistence pool close error")

    # ── Schema bootstrap ─────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
                for ddl in SCHEMA_SQL:
                    cur.execute(ddl)
        logger.info("stt.persistence schema ensured (5 tables)")

    # ── Run lifecycle ────────────────────────────────────────────────

    def create_run(
        self,
        *,
        target: str,
        adapter_name: str,
        capability: AdapterCapability,
        aggregation_mode: str,
        weights: Dict[str, float],
        expected_constructs: Sequence[str],
        environment: Optional[Dict[str, Any]] = None,
        notes: str = "",
        run_id: Optional[str] = None,
    ) -> str:
        run_id = run_id or str(uuid.uuid4())
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO kst_runs
                            (run_id, target, adapter_name, capability,
                             status, aggregation_mode, weights,
                             expected_constructs, completed_constructs,
                             environment, notes, writer_id)
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s::jsonb,
                             %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
                        """,
                        (
                            run_id,
                            target,
                            adapter_name,
                            capability.value,
                            RunStatus.PENDING.value,
                            aggregation_mode,
                            _to_jsonb(weights),
                            _to_jsonb(list(expected_constructs)),
                            _to_jsonb([]),
                            _to_jsonb(environment or {}),
                            notes,
                            self.writer_id,
                        ),
                    )
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"create_run failed: {exc}",
                context={"run_id": run_id, "target": target},
            ) from exc
        return run_id

    def mark_running(self, run_id: str) -> None:
        self._update_status(run_id, RunStatus.RUNNING)

    def mark_paused(self, run_id: str) -> None:
        self._update_status(run_id, RunStatus.PAUSED)

    def mark_completed(self, run_id: str) -> None:
        self._update_status(run_id, RunStatus.COMPLETED, set_finished=True)

    def mark_failed(self, run_id: str, *, notes: Optional[str] = None) -> None:
        self._update_status(
            run_id, RunStatus.FAILED, set_finished=True, notes=notes
        )

    def _update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        set_finished: bool = False,
        notes: Optional[str] = None,
    ) -> None:
        sql_parts = ["UPDATE kst_runs SET status = %s, updated_at = NOW()"]
        params: List[Any] = [status.value]
        if set_finished:
            sql_parts.append(", finished_at = NOW()")
        if notes is not None:
            sql_parts.append(", notes = %s")
            params.append(notes)
        sql_parts.append("WHERE run_id = %s")
        params.append(run_id)
        sql = " ".join(sql_parts)
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(params))
                    if cur.rowcount != 1:
                        raise PersistenceError(
                            f"run_id {run_id} not found for status update.",
                            context={"run_id": run_id, "status": status.value},
                        )
        except PersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"_update_status failed: {exc}",
                context={"run_id": run_id, "status": status.value},
            ) from exc

    def mark_construct_completed(self, run_id: str, construct_id: str) -> None:
        """Append a construct_id to ``completed_constructs`` atomically.

        Resume uses this list to skip already-finished sub-tests.
        """
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE kst_runs
                        SET completed_constructs =
                            (SELECT jsonb_agg(DISTINCT v) FROM jsonb_array_elements_text(
                                completed_constructs || %s::jsonb
                            ) AS v),
                            updated_at = NOW()
                        WHERE run_id = %s
                        """,
                        (json.dumps([construct_id]), run_id),
                    )
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"mark_construct_completed failed: {exc}",
                context={"run_id": run_id, "construct_id": construct_id},
            ) from exc

    # ── Writes ───────────────────────────────────────────────────────

    def insert_sub_test_result(
        self, run_id: str, sub: SubTestScore
    ) -> None:
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO kst_sub_test_results
                            (run_id, construct_id, version, test_id, test_name,
                             score, max_score, normalized, n_items,
                             n_parse_errors, ci_lower, ci_upper, ci_confidence,
                             ci_n_bootstrap, duration_s, sub_scores,
                             per_stratum, trace, error, traceback_text,
                             writer_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s::jsonb,
                                %s::jsonb, %s::jsonb, %s, %s, %s)
                        ON CONFLICT (run_id, construct_id, version)
                        DO UPDATE SET
                            score = EXCLUDED.score,
                            normalized = EXCLUDED.normalized,
                            n_items = EXCLUDED.n_items,
                            n_parse_errors = EXCLUDED.n_parse_errors,
                            ci_lower = EXCLUDED.ci_lower,
                            ci_upper = EXCLUDED.ci_upper,
                            ci_confidence = EXCLUDED.ci_confidence,
                            ci_n_bootstrap = EXCLUDED.ci_n_bootstrap,
                            duration_s = EXCLUDED.duration_s,
                            sub_scores = EXCLUDED.sub_scores,
                            per_stratum = EXCLUDED.per_stratum,
                            trace = EXCLUDED.trace,
                            error = EXCLUDED.error,
                            traceback_text = EXCLUDED.traceback_text
                        """,
                        (
                            run_id,
                            sub.construct_id,
                            sub.version,
                            sub.test_id,
                            sub.test_name,
                            float(sub.score),
                            float(sub.max_score),
                            float(sub.normalized),
                            int(sub.n_items),
                            int(sub.n_parse_errors),
                            sub.ci.lower if sub.ci else None,
                            sub.ci.upper if sub.ci else None,
                            sub.ci.confidence if sub.ci else None,
                            sub.ci.n_bootstrap if sub.ci else None,
                            float(sub.duration_s),
                            _to_jsonb(sub.sub_scores),
                            _to_jsonb(sub.per_stratum),
                            _to_jsonb(sub.trace),
                            sub.error,
                            sub.traceback_text,
                            self.writer_id,
                        ),
                    )
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"insert_sub_test_result failed: {exc}",
                context={"run_id": run_id, "construct_id": sub.construct_id},
            ) from exc

    def insert_response_record(
        self,
        run_id: str,
        construct_id: str,
        version: str,
        item: Item,
        request: AdapterRequest,
        response: AdapterResponse,
    ) -> None:
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO kst_response_records
                            (run_id, construct_id, version, request_id,
                             item_id, prompt, system_prompt, request_payload,
                             response_text, response_payload, model_id,
                             status_code, latency_s, attempts, error,
                             writer_id)
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                             %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (run_id, request_id) DO NOTHING
                        """,
                        (
                            run_id,
                            construct_id,
                            version,
                            request.request_id,
                            item.item_id,
                            request.prompt,
                            request.system,
                            _to_jsonb(
                                {
                                    "temperature": request.temperature,
                                    "max_tokens": request.max_tokens,
                                    "seed": request.seed,
                                    "stop_sequences": list(request.stop_sequences),
                                    "request_logprobs": request.request_logprobs,
                                    "metadata": dict(request.metadata),
                                }
                            ),
                            response.text,
                            _to_jsonb(response.raw or {}),
                            response.model_id,
                            int(response.status_code),
                            float(response.latency_s),
                            int(response.attempts),
                            response.error,
                            self.writer_id,
                        ),
                    )
                    if response.grey_box_telemetry is not None:
                        tele = response.grey_box_telemetry
                        cur.execute(
                            """
                            INSERT INTO kst_telemetry_capture
                                (run_id, request_id, epistemic_state, confidence,
                                 calibration_score, valence, arousal,
                                 seeking_drive, competence, meta_competence,
                                 workspace_selectivity, ags_state,
                                 ags_drift_flag, factual_claim_audit,
                                 tool_routing, voice, raw, writer_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                    %s, %s, %s, %s::jsonb, %s::jsonb,
                                    %s::jsonb, %s::jsonb, %s)
                            """,
                            (
                                run_id,
                                request.request_id,
                                tele.epistemic_state,
                                tele.confidence,
                                tele.calibration_score,
                                tele.valence,
                                tele.arousal,
                                tele.seeking_drive,
                                tele.competence,
                                tele.meta_competence,
                                tele.workspace_selectivity,
                                tele.ags_state,
                                tele.ags_drift_flag,
                                _to_jsonb(tele.factual_claim_audit or {}),
                                _to_jsonb(tele.tool_routing or {}),
                                _to_jsonb(tele.voice or {}),
                                _to_jsonb(tele.raw or {}),
                                self.writer_id,
                            ),
                        )
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"insert_response_record failed: {exc}",
                context={
                    "run_id": run_id,
                    "request_id": str(request.request_id),
                },
            ) from exc

    def upsert_score_aggregate(
        self, report: KSTIndexReport
    ) -> None:
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO kst_score_aggregates
                            (run_id, index_score, ci_lower, ci_upper,
                             ci_confidence, ci_n_bootstrap, weights,
                             aggregation_mode, reproducibility_alpha, dif,
                             environment, notes, writer_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s,
                                %s::jsonb, %s::jsonb, %s, %s)
                        ON CONFLICT (run_id) DO UPDATE SET
                            index_score = EXCLUDED.index_score,
                            ci_lower = EXCLUDED.ci_lower,
                            ci_upper = EXCLUDED.ci_upper,
                            ci_confidence = EXCLUDED.ci_confidence,
                            ci_n_bootstrap = EXCLUDED.ci_n_bootstrap,
                            weights = EXCLUDED.weights,
                            aggregation_mode = EXCLUDED.aggregation_mode,
                            reproducibility_alpha = EXCLUDED.reproducibility_alpha,
                            dif = EXCLUDED.dif,
                            environment = EXCLUDED.environment,
                            notes = EXCLUDED.notes
                        """,
                        (
                            report.run_id,
                            float(report.index_score),
                            report.index_ci.lower if report.index_ci else None,
                            report.index_ci.upper if report.index_ci else None,
                            (
                                report.index_ci.confidence
                                if report.index_ci
                                else None
                            ),
                            (
                                report.index_ci.n_bootstrap
                                if report.index_ci
                                else None
                            ),
                            _to_jsonb(report.weights),
                            report.aggregation_mode.value,
                            report.reproducibility_alpha,
                            _to_jsonb(report.dif),
                            _to_jsonb(report.environment),
                            report.notes,
                            self.writer_id,
                        ),
                    )
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"upsert_score_aggregate failed: {exc}",
                context={"run_id": report.run_id},
            ) from exc

    # ── Reads ────────────────────────────────────────────────────────

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        try:
            import psycopg2.extras  # type: ignore

            with self._conn() as conn:
                with conn.cursor(
                    cursor_factory=psycopg2.extras.DictCursor
                ) as cur:
                    cur.execute(
                        "SELECT * FROM kst_runs WHERE run_id = %s",
                        (run_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        return None
                    return _row_to_dict(row)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"get_run failed: {exc}",
                context={"run_id": run_id},
            ) from exc

    def list_runs(
        self,
        *,
        target: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        try:
            import psycopg2.extras  # type: ignore

            sql_parts = ["SELECT * FROM kst_runs WHERE 1=1"]
            params: List[Any] = []
            if target:
                sql_parts.append(" AND target = %s")
                params.append(target)
            if since is not None:
                if since.tzinfo is None:
                    since = since.replace(tzinfo=timezone.utc)
                sql_parts.append(" AND started_at >= %s")
                params.append(since)
            sql_parts.append(" ORDER BY started_at DESC LIMIT %s")
            params.append(int(limit))

            with self._conn() as conn:
                with conn.cursor(
                    cursor_factory=psycopg2.extras.DictCursor
                ) as cur:
                    cur.execute("".join(sql_parts), tuple(params))
                    return [_row_to_dict(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"list_runs failed: {exc}",
                context={"target": target},
            ) from exc

    def get_sub_test_results(
        self, run_id: str
    ) -> List[Dict[str, Any]]:
        try:
            import psycopg2.extras  # type: ignore

            with self._conn() as conn:
                with conn.cursor(
                    cursor_factory=psycopg2.extras.DictCursor
                ) as cur:
                    cur.execute(
                        """
                        SELECT * FROM kst_sub_test_results
                        WHERE run_id = %s
                        ORDER BY construct_id ASC, version ASC
                        """,
                        (run_id,),
                    )
                    return [_row_to_dict(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"get_sub_test_results failed: {exc}",
                context={"run_id": run_id},
            ) from exc

    def get_response_records(
        self, run_id: str, *, construct_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        try:
            import psycopg2.extras  # type: ignore

            if construct_id is None:
                sql = (
                    "SELECT * FROM kst_response_records "
                    "WHERE run_id = %s ORDER BY id ASC"
                )
                params: Tuple[Any, ...] = (run_id,)
            else:
                sql = (
                    "SELECT * FROM kst_response_records "
                    "WHERE run_id = %s AND construct_id = %s "
                    "ORDER BY id ASC"
                )
                params = (run_id, construct_id)
            with self._conn() as conn:
                with conn.cursor(
                    cursor_factory=psycopg2.extras.DictCursor
                ) as cur:
                    cur.execute(sql, params)
                    return [_row_to_dict(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"get_response_records failed: {exc}",
                context={"run_id": run_id},
            ) from exc

    def get_score_aggregate(self, run_id: str) -> Optional[Dict[str, Any]]:
        try:
            import psycopg2.extras  # type: ignore

            with self._conn() as conn:
                with conn.cursor(
                    cursor_factory=psycopg2.extras.DictCursor
                ) as cur:
                    cur.execute(
                        "SELECT * FROM kst_score_aggregates WHERE run_id = %s",
                        (run_id,),
                    )
                    row = cur.fetchone()
                    return _row_to_dict(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"get_score_aggregate failed: {exc}",
                context={"run_id": run_id},
            ) from exc

    def compare_runs(
        self, run_ids: Sequence[str]
    ) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for rid in run_ids:
            run = self.get_run(rid)
            if run is None:
                continue
            out[rid] = {
                "run": run,
                "score": self.get_score_aggregate(rid),
                "sub_tests": self.get_sub_test_results(rid),
            }
        return out

    def resume_check(self, run_id: str) -> List[str]:
        """Return completed_constructs for ``run_id`` or raise :class:`ResumeError`.

        The harness consults this on ``--resume <run_id>`` to know
        which sub-tests to skip. A terminal status (``completed`` or
        ``failed``) raises so we never silently re-finalise a closed run.
        """
        run = self.get_run(run_id)
        if run is None:
            raise ResumeError(
                f"run_id {run_id} not found.",
                context={"run_id": run_id},
            )
        status = run.get("status", "")
        if status in (RunStatus.COMPLETED.value, RunStatus.FAILED.value):
            raise ResumeError(
                f"run_id {run_id} is in terminal status '{status}'.",
                context={"run_id": run_id, "status": status},
            )
        completed = run.get("completed_constructs", [])
        if isinstance(completed, str):
            completed = json.loads(completed)
        return list(completed or [])


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Materialise a psycopg2 DictRow as a plain JSON-safe dict.

    Datetime values become ISO 8601 strings; UUIDs become strings;
    psycopg2 already maps JSONB to native dicts.
    """
    if row is None:
        return {}
    out: Dict[str, Any] = {}
    for k in row.keys():
        v = row[k]
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


__all__ = [
    "KSTPersistence",
    "SCHEMA_SQL",
    "WRITER_ID_DEFAULT",
]
