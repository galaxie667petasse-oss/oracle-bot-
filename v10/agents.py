from dataclasses import asdict, dataclass
from typing import Any, Mapping


SPECIALIST_AGENT_IDS = [
    "statistical_model_auditor",
    "market_pricing_analyst",
    "recent_form_analyst",
    "home_away_specialist",
    "squad_availability_analyst",
    "tactical_matchup_analyst",
    "schedule_fatigue_analyst",
    "competition_context_analyst",
    "news_source_reliability_analyst",
    "data_quality_anomaly_analyst",
    "devils_advocate",
    "portfolio_correlation_analyst",
]

ALLOWED_VERDICTS = {
    "STRONG_SUPPORT",
    "SUPPORT",
    "NEUTRAL",
    "OPPOSE",
    "STRONG_OPPOSE",
    "INSUFFICIENT_DATA",
}


@dataclass(frozen=True)
class AgentEvidence:
    fact: str
    source_type: str
    source_reference: str
    observed_at: str
    reliability: float

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AgentEvidence":
        reliability = float(data.get("reliability"))
        if reliability < 0.0 or reliability > 1.0:
            raise ValueError("evidence reliability must be between 0 and 1")
        fact = str(data.get("fact", "")).strip()
        if not fact:
            raise ValueError("evidence fact is required")
        return cls(
            fact=fact,
            source_type=str(data.get("source_type", "")).strip(),
            source_reference=str(data.get("source_reference", "")).strip(),
            observed_at=str(data.get("observed_at", "")).strip(),
            reliability=reliability,
        )


@dataclass(frozen=True)
class AgentFinding:
    schema_version: str
    agent_id: str
    fixture_id: str
    market_key: str
    selection_key: str
    verdict: str
    confidence: float
    probability_adjustment_bps: int
    veto: bool
    veto_reason: str | None
    evidence: list[AgentEvidence]
    risks: list[str]
    missing_information: list[str]
    contradictions: list[str]
    summary: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AgentFinding":
        version = str(data.get("schema_version", "")).strip()
        if version != "1.0":
            raise ValueError("agent schema_version must be 1.0")
        agent_id = str(data.get("agent_id", "")).strip()
        if agent_id not in SPECIALIST_AGENT_IDS:
            raise ValueError("unknown agent_id")
        verdict = str(data.get("verdict", "")).strip()
        if verdict not in ALLOWED_VERDICTS:
            raise ValueError("invalid agent verdict")
        confidence = float(data.get("confidence"))
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError("agent confidence must be between 0 and 1")
        adjustment = int(data.get("probability_adjustment_bps", 0))
        if abs(adjustment) > 500:
            raise ValueError("probability_adjustment_bps outside conservative bounds")
        evidence = [AgentEvidence.from_mapping(item) for item in data.get("evidence", [])]
        return cls(
            schema_version=version,
            agent_id=agent_id,
            fixture_id=str(data.get("fixture_id", "")).strip(),
            market_key=str(data.get("market_key", "")).strip(),
            selection_key=str(data.get("selection_key", "")).strip(),
            verdict=verdict,
            confidence=confidence,
            probability_adjustment_bps=adjustment,
            veto=bool(data.get("veto", False)),
            veto_reason=None if data.get("veto_reason") in (None, "") else str(data.get("veto_reason")),
            evidence=evidence,
            risks=[str(item) for item in data.get("risks", [])],
            missing_information=[str(item) for item in data.get("missing_information", [])],
            contradictions=[str(item) for item in data.get("contradictions", [])],
            summary=str(data.get("summary", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [asdict(item) for item in self.evidence]
        return data


def mock_agent_findings(candidate: Mapping[str, Any], observed_at: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for agent_id in SPECIALIST_AGENT_IDS:
        verdict = "NEUTRAL"
        confidence = 0.55
        risks = ["mock agent: no external source consulted"]
        missing = ["real specialist evidence not collected in deterministic demo"]
        if agent_id == "statistical_model_auditor":
            verdict = "SUPPORT"
            confidence = 0.68
            risks = ["sample synthetic; no historical validation"]
            missing = ["walk-forward validation"]
        if agent_id == "data_quality_anomaly_analyst" and candidate.get("data_quality_status") != "PASS":
            verdict = "INSUFFICIENT_DATA"
            confidence = 0.80
        raw = {
            "schema_version": "1.0",
            "agent_id": agent_id,
            "fixture_id": candidate.get("fixture_id"),
            "market_key": candidate.get("market_key"),
            "selection_key": candidate.get("selection_key"),
            "verdict": verdict,
            "confidence": confidence,
            "probability_adjustment_bps": 0,
            "veto": False,
            "veto_reason": None,
            "evidence": [
                {
                    "fact": "Deterministic demo candidate metrics were supplied by Python.",
                    "source_type": "internal_demo",
                    "source_reference": str(candidate.get("fixture_id")),
                    "observed_at": observed_at,
                    "reliability": 0.75,
                }
            ],
            "risks": risks,
            "missing_information": missing,
            "contradictions": [],
            "summary": "Mock finding for offline V10 demo.",
        }
        findings.append(AgentFinding.from_mapping(raw).to_dict())
    return findings

