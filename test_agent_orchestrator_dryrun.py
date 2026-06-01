import io
from contextlib import redirect_stdout

import agent_orchestrator_dryrun as agent


def main():
    assert "Verifier oracle_ops --health" in agent.build_steps("daily")
    assert "Valider le CSV manuel de cotes" in agent.build_steps("odds-cycle")
    assert "Executer evidence_gate" in agent.build_steps("evidence-cycle")
    assert len(agent.build_steps("full")) > len(agent.build_steps("daily"))
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        agent.print_steps("full")
    text = buffer.getvalue()
    assert "Dry-run uniquement" in text
    assert "Telegram" in text
    print("test_agent_orchestrator_dryrun ok")


if __name__ == "__main__":
    main()
