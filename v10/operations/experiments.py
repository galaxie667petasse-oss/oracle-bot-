from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from v10.db.models import ShadowExperiment, ShadowExperimentDecision, ShadowExperimentOutcome
from v10.llm.evidence.models import stable_hash
from v10.time import ensure_utc, utc_now


DEFAULT_EXPERIMENT_KEY = "statistical_vs_llm_shadow_v1"


class ShadowExperimentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create(self, key: str = DEFAULT_EXPERIMENT_KEY, version: str = "1.0", apply: bool = True) -> tuple[ShadowExperiment | None, bool]:
        existing = self.session.scalar(select(ShadowExperiment).where(ShadowExperiment.experiment_key == key, ShadowExperiment.version == version))
        if existing:
            return existing, False
        if not apply:
            return None, True
        row = ShadowExperiment(
            experiment_key=key,
            version=version,
            cohort_rules_json={
                "mode": "shadow",
                "arms": ["deterministic_only", "deterministic_plus_llm"],
                "outcome_hidden_until_after_match": True,
                "no_real_money": True,
            },
            starts_at=utc_now(),
            status="ACTIVE",
            statistical_model_versions_json=["ensemble_v1"],
            prompt_versions_json=["sol_shadow_judge_v1"],
            gate_version="deterministic_gate_v1",
            preregistered_metrics_json=["coverage", "brier", "log_loss", "clv", "paper_roi", "llm_cost"],
        )
        self.session.add(row)
        self.session.flush()
        return row, True

    def record_decision(
        self,
        experiment_id: str,
        candidate_id: str,
        fixture_id: str,
        arm: str,
        decision: str,
        decision_time,
        evidence_packet_hash: str,
        payload: dict[str, Any],
        model_versions: list[str] | None = None,
        prompt_versions: list[str] | None = None,
    ) -> tuple[ShadowExperimentDecision, bool]:
        decision_time = ensure_utc(decision_time, "decision_time")
        decision_hash = stable_hash(
            {
                "experiment_id": experiment_id,
                "candidate_id": candidate_id,
                "fixture_id": fixture_id,
                "arm": arm,
                "decision": decision,
                "decision_time": decision_time.isoformat(),
                "evidence_packet_hash": evidence_packet_hash,
                "payload": payload,
            }
        )
        existing = self.session.scalar(
            select(ShadowExperimentDecision).where(
                ShadowExperimentDecision.experiment_id == experiment_id,
                ShadowExperimentDecision.candidate_id == candidate_id,
                ShadowExperimentDecision.arm == arm,
                ShadowExperimentDecision.decision_hash == decision_hash,
            )
        )
        if existing:
            return existing, False
        row = ShadowExperimentDecision(
            experiment_id=experiment_id,
            candidate_id=candidate_id,
            fixture_id=fixture_id,
            arm=arm,
            decision=decision,
            decision_time=decision_time,
            model_versions_json=list(model_versions or ["ensemble_v1"]),
            prompt_versions_json=list(prompt_versions or []),
            evidence_packet_hash=evidence_packet_hash,
            outcome_hidden=True,
            decision_hash=decision_hash,
            decision_json=payload,
        )
        self.session.add(row)
        try:
            self.session.flush()
            return row, True
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(ShadowExperimentDecision).where(
                    ShadowExperimentDecision.experiment_id == experiment_id,
                    ShadowExperimentDecision.candidate_id == candidate_id,
                    ShadowExperimentDecision.arm == arm,
                    ShadowExperimentDecision.decision_hash == decision_hash,
                )
            )
            if existing:
                return existing, False
            raise

    def report(self, key: str = DEFAULT_EXPERIMENT_KEY) -> dict[str, Any]:
        experiment = self.session.scalar(select(ShadowExperiment).where(ShadowExperiment.experiment_key == key).order_by(ShadowExperiment.created_at.desc()))
        if not experiment:
            return {"experiment_key": key, "status": "MISSING", "decisions": 0, "outcomes": 0}
        decisions = list(self.session.scalars(select(ShadowExperimentDecision).where(ShadowExperimentDecision.experiment_id == experiment.id)))
        outcomes = list(
            self.session.scalars(
                select(ShadowExperimentOutcome).join(
                    ShadowExperimentDecision,
                    ShadowExperimentOutcome.experiment_decision_id == ShadowExperimentDecision.id,
                ).where(ShadowExperimentDecision.experiment_id == experiment.id)
            )
        )
        by_arm: dict[str, int] = {}
        by_decision: dict[str, int] = {}
        for row in decisions:
            by_arm[row.arm] = by_arm.get(row.arm, 0) + 1
            by_decision[row.decision] = by_decision.get(row.decision, 0) + 1
        return {
            "experiment_key": experiment.experiment_key,
            "version": experiment.version,
            "status": experiment.status,
            "decisions": len(decisions),
            "outcomes": len(outcomes),
            "by_arm": by_arm,
            "by_decision": by_decision,
            "bias_warning": "Comparer les deux bras uniquement sur la meme cohorte initiale; les resultats restent paper-only.",
        }


def dry_run_experiment_status(key: str = DEFAULT_EXPERIMENT_KEY) -> dict[str, Any]:
    return {
        "experiment_key": key,
        "version": "1.0",
        "status": "DRY_RUN",
        "arms": ["deterministic_only", "deterministic_plus_llm"],
        "immutable_decisions": True,
        "outcome_hidden_until_after_match": True,
        "paper_only": True,
        "lab_only": True,
    }
