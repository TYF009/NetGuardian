"""Evaluate a configured model against an existing exported evidence report.

No synthetic measurements are generated. This checks transport and evidence
consistency, not the correctness of causal diagnosis or remediation.
"""

import argparse
import asyncio
import json
from pathlib import Path

from service.investigation import ask_ollama, evidence_context, validate_output
from service.report_files import load_export


def load_evidence(path):
    exported = load_export(path)
    snapshot = exported["snapshot"]
    expected = exported["content_hash"]
    evidence = evidence_context(snapshot)
    if not evidence:
        raise ValueError("Report has no recorded observations to evaluate")
    return expected, evidence


async def evaluate(endpoint, model, evidence_hash, evidence):
    result = {
        "model": model,
        "report_hash": evidence_hash,
        "observation_count": len(evidence),
        "transport": "not_completed",
        "evidence_validation": "not_completed",
        "diagnosis_quality": "not_assessed",
        "limitations": [
            "Only the latest 30 recorded observations are supplied.",
            "Matching citations and scalar facts do not establish causal accuracy.",
            "Hypotheses remain unverified and require human review.",
            "The report checksum is not an authenticity signature.",
        ],
    }
    try:
        content = await ask_ollama(endpoint, model, evidence)
        result["transport"] = "completed"
        output = validate_output(content, evidence)
        result["evidence_validation"] = "passed"
        result["recorded_fact_count"] = len(output["facts"])
        result["nonempty_findings"] = bool(output["facts"])
        result["output"] = output
    except Exception as exc:
        # Do not copy endpoint responses, credentials or arbitrary exception text into artifacts.
        result["error_type"] = type(exc).__name__
        result["evidence_validation"] = (
            "failed" if result["transport"] == "completed" else "not_completed"
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="Existing exported report JSON")
    parser.add_argument("--endpoint", required=True, help="Administrator-approved Ollama origin")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New evaluation artifact path")
    args = parser.parse_args()
    evidence_hash, evidence = load_evidence(args.report)
    # Exclusive creation prevents overwriting reports or previous evaluations.
    with args.output.open("x", encoding="utf-8") as destination:
        result = asyncio.run(evaluate(args.endpoint, args.model, evidence_hash, evidence))
        json.dump(result, destination, indent=2, ensure_ascii=True)
        destination.write("\n")
    print(
        json.dumps(
            {key: result[key] for key in ("transport", "evidence_validation", "diagnosis_quality")}
        )
    )
    return 0 if result.get("nonempty_findings") and result["evidence_validation"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
