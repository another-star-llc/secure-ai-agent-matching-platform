import argparse
import json
import os
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Set

from jsonschema import Draft202012Validator, ValidationError

from .security_gate import run_security_gate
from .agent_card_accuracy import run_functional_accuracy
from .wandb_logger import create_wandb_logger

try:
    import wandb  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    wandb = None

WANDB_DISABLED = os.environ.get("WANDB_DISABLED", "false").lower() == "true"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluation runner CLI")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--template", required=True, choices=["google-adk", "langgraph"])
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--dry-run", action="store_true", help="Skip external calls, generate placeholder artifacts")
    parser.add_argument("--wandb-project", default="agent-store-sandbox")
    parser.add_argument("--wandb-entity", default="local")
    parser.add_argument("--wandb-base-url", default="https://wandb.fake")
    # NOTE: schemas live at evaluation-runner/schemas rather than inside src/
    # Using parents[2] keeps the default stable even when the package is installed editable.
    default_schema_dir = Path(__file__).resolve().parents[2] / "schemas"
    default_manifest = Path(__file__).resolve().parents[3] / "prompts/aisi/manifest.sample.json"
    parser.add_argument("--schema-dir", default=str(default_schema_dir), help="Directory containing JSON schemas")
    parser.add_argument("--prompt-manifest", default=str(default_manifest), help="AISI prompt manifest used for question ID validation")
    parser.add_argument("--generate-fairness", action="store_true", help="Emit fairness_probe.json artifact")
    parser.add_argument("--wandb-run-id", help="Reuse an existing W&B Run ID (resume logging)")
    default_security_dataset = Path(__file__).resolve().parents[3] / "third_party" / "aisev" / "backend" / "dataset" / "output" / "06_aisi_security_v0.1.csv"
    parser.add_argument("--security-dataset", default=str(default_security_dataset), help="Security prompt dataset CSV (AdvBench/AISIなど)")
    parser.add_argument("--security-attempts", type=int, default=8, help="Number of security prompts to run")
    parser.add_argument("--security-endpoint", help="Optional HTTP endpoint for executing prompts against the agent")
    parser.add_argument("--security-endpoint-token", help="Bearer token passed to the security endpoint")
    parser.add_argument("--security-timeout", type=float, default=15.0, help="Timeout seconds for security endpoint requests")
    parser.add_argument("--skip-security-gate", action="store_true", help="Disable security gate run even if dataset is available")
    parser.add_argument("--relay-endpoint", help="Default A2A relay endpoint used when stage-specific endpoints are未設定")
    parser.add_argument("--relay-token", help="Bearer token shared across security/functional stages")
    parser.add_argument("--functional-endpoint", help="Agent Card Accuracy HTTP endpoint (defaults to relay endpoint)")
    parser.add_argument("--functional-endpoint-token", help="Bearer token for the functional endpoint")
    parser.add_argument("--functional-timeout", type=float, default=20.0, help="Functional endpoint timeout seconds")
    parser.add_argument("--agent-card", help="Path to AgentCard JSON used for Agent Card Accuracy evaluation")
    default_ragtruth_dir = Path(__file__).resolve().parents[2] / "resources" / "ragtruth"
    default_advbench_dir = Path(__file__).resolve().parents[3] / "third_party" / "aisev" / "backend" / "dataset" / "output"
    parser.add_argument("--ragtruth-dir", default=str(default_ragtruth_dir), help="Directory containing RAGTruth-style JSONL files")
    parser.add_argument("--advbench-dir", default=str(default_advbench_dir), help="Directory containing AdvBench CSV prompts derived from AISI aisev")
    parser.add_argument("--advbench-limit", type=int, default=20, help="Maximum number of AdvBench prompts to inject (<=0 for unlimited)")
    parser.add_argument("--functional-max-scenarios", type=int, default=5, help="Maximum number of DSLシナリオ to evaluate")
    parser.add_argument("--skip-functional", action="store_true", help="Skip Agent Card Accuracy evaluation")
    return parser.parse_args(argv)


def init_wandb_run(agent_id: str, revision: str, template: str, *, project: str, entity: str, base_url: str, run_id_override: str | None = None) -> Dict[str, Any]:
    run_id = run_id_override or f"sandbox-{agent_id}-{revision}-{uuid.uuid4().hex[:8]}"
    if WANDB_DISABLED:
        return {
            "enabled": False,
            "runId": run_id,
            "url": None,
            "notes": "WANDB_DISABLED=true"
        }

    if wandb is None:
        return {
            "enabled": False,
            "runId": run_id,
            "url": None,
            "notes": "wandb package not installed"
        }

    run = wandb.init(  # type: ignore[union-attr]
        project=project,
        entity=entity,
        id=run_id,
        name=run_id,
        resume="allow",
        reinit=True,
        settings=wandb.Settings(start_method="thread")  # type: ignore[attr-defined]
    )

    return {
        "enabled": True,
        "runId": run_id,
        "url": run.url if run else f"{base_url.rstrip('/')}/{entity}/{project}/runs/{run_id}",
        "notes": "wandb run started",
        "_run": run
    }


def load_schema(schema_dir: Path, filename: str) -> Dict[str, Any]:
    schema_path = schema_dir / filename
    with schema_path.open(encoding="utf-8") as f:
        return json.load(f)


def load_prompt_question_ids(manifest_path: Path) -> Set[str]:
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    base_dir = manifest_path.parent
    question_ids: Set[str] = set()
    for rel_path in manifest.get("questionFiles", []):
        question_path = base_dir / rel_path
        with question_path.open(encoding="utf-8") as qf:
            question = json.load(qf)
        question_id = question.get("id")
        if not isinstance(question_id, str):
            raise ValidationError(f"question file {rel_path} missing string 'id'")
        question_ids.add(question_id)
    return question_ids


def validate_artifacts(samples: List[Dict[str, Any]], policy_score: Dict[str, Any], fairness_probe: List[Dict[str, Any]] | None, schema_dir: Path, manifest_path: Path) -> None:
    response_schema = load_schema(schema_dir, "response_sample.schema.json")
    policy_schema = load_schema(schema_dir, "policy_score.schema.json")
    sample_validator = Draft202012Validator(response_schema)
    policy_validator = Draft202012Validator(policy_schema)
    for sample in samples:
        sample_validator.validate(sample)
    policy_validator.validate(policy_score)

    if fairness_probe is not None:
        fairness_schema = load_schema(schema_dir, "fairness_probe.schema.json")
        fairness_validator = Draft202012Validator(fairness_schema)
        for segment in fairness_probe:
            fairness_validator.validate(segment)

    question_ids = load_prompt_question_ids(manifest_path)
    invalid_ids = {sample["questionId"] for sample in samples if sample["questionId"] not in question_ids}
    if invalid_ids:
        raise ValidationError(f"question IDs not present in manifest: {sorted(invalid_ids)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(args.agent_id + args.revision)

    response_samples: list[Dict[str, Any]] = []
    for question_id in ("safety.general", "privacy.data_retention"):
        latency_ms = random.randint(900, 1800)
        tokens_out = random.randint(80, 180)
        output_text = "申し訳ありませんが対応できません。" if question_id == "safety.general" else "データは24時間で削除します。"
        response_samples.append(
            {
                "questionId": question_id,
                "inputText": f"{question_id} に対する応答",
                "outputText": output_text,
                "latencyMs": latency_ms,
                "tokensOut": tokens_out,
            }
        )

    policy_score: Dict[str, Any] = {
        "score": round(random.uniform(0.9, 0.99), 3),
        "rulesViolated": [],
        "evaluatorVersion": "placeholder-1"
    }

    fairness_probe: List[Dict[str, Any]] | None = None
    if args.generate_fairness:
        fairness_probe = [
            {
                "segment": "ja-JP",
                "score": round(random.uniform(0.8, 0.98), 3),
                "details": {
                    "cases": random.randint(10, 25)
                }
            }
        ]

    schema_dir = Path(args.schema_dir)
    manifest_path = Path(args.prompt_manifest)

    try:
        validate_artifacts(response_samples, policy_score, fairness_probe, schema_dir, manifest_path)
    except ValidationError as exc:
        print(f"[evaluation-runner] validation error: {exc.message}", file=sys.stderr)
        return 2

    wandb_info = init_wandb_run(
        args.agent_id,
        args.revision,
        args.template,
        project=args.wandb_project,
        entity=args.wandb_entity,
        base_url=args.wandb_base_url,
        run_id_override=args.wandb_run_id
    )

    (output_dir / "response_samples.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in response_samples)
    )
    (output_dir / "policy_score.json").write_text(json.dumps(policy_score, ensure_ascii=False, indent=2))
    if fairness_probe is not None:
        (output_dir / "fairness_probe.json").write_text(json.dumps(fairness_probe, ensure_ascii=False, indent=2))

    metadata = {
        "agentId": args.agent_id,
        "revision": args.revision,
        "template": args.template,
        "dryRun": args.dry_run,
        "timestamp": int(time.time()),
        "wandb": {
            **wandb_info,
            "project": args.wandb_project,
            "entity": args.wandb_entity,
            "baseUrl": args.wandb_base_url
        },
    }
    wandb_logger = create_wandb_logger(
        base_metadata=metadata,
        wandb_info=wandb_info,
        project=args.wandb_project,
        entity=args.wandb_entity,
        base_url=args.wandb_base_url,
    )

    agent_card_data = None
    if args.agent_card:
        card_path = Path(args.agent_card)
        if card_path.exists():
            with card_path.open(encoding="utf-8") as card_file:
                agent_card_data = json.load(card_file)

    security_summary = None
    if not args.skip_security_gate:
        security_output = output_dir / "security"
        security_summary = run_security_gate(
            agent_id=args.agent_id,
            revision=args.revision,
            dataset_path=Path(args.security_dataset),
            output_dir=security_output,
            attempts=max(1, args.security_attempts),
            endpoint_url=args.security_endpoint or args.relay_endpoint,
            endpoint_token=args.security_endpoint_token or args.relay_token,
            timeout=args.security_timeout,
            dry_run=args.dry_run,
            agent_card=agent_card_data
        )
        metadata["securityGate"] = security_summary
        wandb_logger.log_stage_summary("security", security_summary)
        wandb_logger.save_artifact("security", security_output / "security_gate_report.jsonl", name="security-report")
        wandb_logger.save_artifact("security", security_output / "security_prompts.jsonl", name="security-prompts")

    functional_summary = None
    if not args.skip_functional and args.agent_card:
        functional_output = output_dir / "functional"
        functional_summary = run_functional_accuracy(
            agent_id=args.agent_id,
            revision=args.revision,
            agent_card_path=Path(args.agent_card),
            ragtruth_dir=Path(args.ragtruth_dir),
            advbench_dir=Path(args.advbench_dir),
            advbench_limit=(args.advbench_limit if args.advbench_limit > 0 else None),
            output_dir=functional_output,
            max_scenarios=max(1, args.functional_max_scenarios),
            dry_run=args.dry_run,
            endpoint_url=args.functional_endpoint or args.relay_endpoint,
            endpoint_token=args.functional_endpoint_token or args.relay_token,
            timeout=args.functional_timeout
        )
        metadata["functionalAccuracy"] = functional_summary
        wandb_logger.log_stage_summary("functional", functional_summary)
        wandb_logger.save_artifact("functional", functional_output / "agent_card_accuracy_report.jsonl", name="functional-report")

    metadata["wandbLogger"] = wandb_logger.export_metadata()
    (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))

    if wandb_info.get("enabled") and wandb is not None:
        run = wandb_info.pop("_run", None)
        try:
            wandb.config.update({  # type: ignore[attr-defined]
                "agent_id": args.agent_id,
                "revision": args.revision,
                "template": args.template
            })
            wandb.log({  # type: ignore[attr-defined]
                "policy_score": policy_score["score"],
                "latency_ms": sum(item["latencyMs"] for item in response_samples) / len(response_samples),
            })
            wandb.save(str(output_dir / "response_samples.jsonl"))  # type: ignore[attr-defined]
            wandb.save(str(output_dir / "policy_score.json"))  # type: ignore[attr-defined]
            if fairness_probe is not None:
                wandb.save(str(output_dir / "fairness_probe.json"))  # type: ignore[attr-defined]
        finally:
            if run is not None:
                run.finish()

    print(f"[evaluation-runner] generated artifacts in {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
