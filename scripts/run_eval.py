"""Evaluate sentiment on the labeled set: accuracy, Macro-F1, per-class metrics, confusion matrix.

    python scripts/run_eval.py                        # deterministic stub (always runs)
    python scripts/run_eval.py --analyzer hf          # real model (needs torch + transformers
                                                      #   and the model files or hub access)
    python scripts/run_eval.py --analyzer hf --sweep  # also compare neutral margins

Also reports aspect detection recall (annotated aspects the lexicon found) and aspect
sentiment accuracy, and for the real model the cold start, throughput and peak memory.
Prints a text report; `--json-out PATH` writes the same numbers as JSON.

Never called by default tests with a real model (AGENTS.md rule 5). No network is used unless
`--analyzer hf` has to download the model. Exit codes: 0 ok, 1 thresholds missed (only with
`--enforce`), 2 real model unavailable.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

DEFAULT_DATASET = ROOT / "backend" / "tests" / "fixtures" / "nlp" / "sentiment_eval_v1.json"
DEFAULT_MARGINS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40)
MIN_ACCURACY = 0.75  # docs/DEVELOPMENT_PLAN.md Phase 4 "Done when" (suggested thresholds)
MIN_MACRO_F1 = 0.70


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--analyzer", choices=("stub", "hf"), default="stub")
    parser.add_argument("--model-id", default=None, help="default: Settings.sentiment_model")
    parser.add_argument("--cache-dir", default=None, help="default: Settings.hf_home")
    parser.add_argument("--local-files-only", action="store_true", help="never touch the network")
    parser.add_argument("--neutral-margin", type=float, default=0.15)
    parser.add_argument("--sweep", action="store_true", help="compare margins (hf only)")
    parser.add_argument("--margins", type=float, nargs="+", default=list(DEFAULT_MARGINS))
    parser.add_argument("--show-errors", action="store_true", help="list misclassified items")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--enforce", action="store_true", help="exit 1 below the thresholds")
    parser.add_argument("--min-accuracy", type=float, default=MIN_ACCURACY)
    parser.add_argument("--min-macro-f1", type=float, default=MIN_MACRO_F1)
    return parser.parse_args(argv)


def _peak_rss_mb() -> float | None:
    try:
        import resource  # not available on Windows
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round((peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024), 1)


def _confusion_text(report) -> str:
    labels = list(report.confusion)
    width = max(len(label) for label in labels) + 2
    head = " " * (width + 12) + "".join(f"{label:>{width}}" for label in labels)
    lines = [f"{'':{width}}(rows = true, columns = predicted)", head]
    for true in labels:
        cells = "".join(f"{report.confusion[true][pred]:>{width}}" for pred in labels)
        lines.append(f"{true:>{width + 12}}{cells}")
    return "\n".join(lines)


def _report_text(title: str, report) -> str:
    lines = [
        f"{title}: n={report.total}  accuracy={report.accuracy:.4f}  "
        f"macro_f1={report.macro_f1:.4f}",
        f"  {'class':<10}{'precision':>10}{'recall':>10}{'f1':>10}{'support':>9}",
    ]
    for label, m in report.per_class.items():
        lines.append(
            f"  {label:<10}{m.precision:>10.4f}{m.recall:>10.4f}{m.f1:>10.4f}{m.support:>9}"
        )
    lines.append("  confusion matrix")
    lines.extend("  " + line for line in _confusion_text(report).splitlines())
    return "\n".join(lines)


def _report_dict(report) -> dict:
    return {
        "total": report.total,
        "accuracy": report.accuracy,
        "macro_f1": report.macro_f1,
        "per_class": {
            label: {
                "precision": m.precision,
                "recall": m.recall,
                "f1": m.f1,
                "support": m.support,
            }
            for label, m in report.per_class.items()
        },
        "confusion": {t: dict(row) for t, row in report.confusion.items()},
    }


def _full_dict(report) -> dict:
    detection = report.aspect_detection
    return {
        "margin": report.margin,
        "overall": _report_dict(report.overall),
        "aspect_detection": {
            "expected": detection.expected,
            "detected": detection.detected,
            "recall": detection.recall,
            "missed": list(detection.missed),
            "unannotated_detected": detection.unannotated_detected,
        },
        "aspect_sentiment": (
            _report_dict(report.aspect_sentiment) if report.aspect_sentiment else None
        ),
        "misclassified": [
            {
                "id": m.id,
                "expected": m.expected,
                "predicted": m.predicted,
                "positive_prob": m.positive_prob,
                "neutral_prob": m.neutral_prob,
                "negative_prob": m.negative_prob,
                "text": m.text,
            }
            for m in report.misclassified
        ],
        "aspect_misclassified": list(report.aspect_misclassified),
    }


def _build_analyzer(args: argparse.Namespace):
    if args.analyzer == "stub":
        from app.services.nlp.sentiment import StubSentimentAnalyzer

        return StubSentimentAnalyzer()
    from app.config.settings import Settings
    from app.services.nlp.hf_sentiment import HFSentimentAnalyzer

    settings = Settings(_env_file=None)
    # Margin 0 keeps the raw argmax; the margin rule is re-applied in `score` so one model pass
    # serves every margin. Equivalent to constructing the analyzer with that margin.
    return HFSentimentAnalyzer(
        args.model_id or settings.sentiment_model,
        cache_dir=args.cache_dir or settings.hf_home or None,
        local_files_only=args.local_files_only,
        neutral_margin=0.0,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    if args.sweep and args.analyzer != "hf":
        print("--sweep needs --analyzer hf (the stub has no calibrated probabilities).")
        return 2
    if not 0.0 <= args.neutral_margin < 1.0:
        print("--neutral-margin must be in [0, 1).")
        return 2

    from app.services.nlp import evaluation
    from app.services.nlp.model_loader import ModelUnavailableError

    dataset = evaluation.load_dataset(args.dataset)
    analyzer = _build_analyzer(args)
    timing: dict[str, float | None] = {}
    try:
        if args.analyzer == "hf":
            started = time.perf_counter()
            analyzer.analyze(["warm up"])  # loads the model (and downloads it if missing)
            timing["cold_start_seconds"] = round(time.perf_counter() - started, 3)
        started = time.perf_counter()
        outcomes = evaluation.run_analyzer(dataset, analyzer)
        elapsed = time.perf_counter() - started
    except ModelUnavailableError as exc:
        print(f"REAL MODEL NOT AVAILABLE: {exc}")
        print("Nothing was evaluated. Install torch + transformers and make the model reachable")
        print("(pip install -e '.[nlp]'; first run needs the Hugging Face hub or a populated")
        print("HF_HOME), then rerun with --analyzer hf.")
        return 2

    texts = sum(1 + len(o.aspects) for o in outcomes)
    timing.update(
        texts_scored=texts,
        eval_seconds=round(elapsed, 3),
        texts_per_second=round(texts / elapsed, 1) if elapsed > 0 else None,
        peak_rss_mb=_peak_rss_mb(),
    )
    margin = args.neutral_margin if args.analyzer == "hf" else None
    report = evaluation.score(outcomes, margin=margin)

    model = getattr(analyzer, "model_name", args.analyzer)
    print(f"dataset: {dataset.name} v{dataset.version} ({len(dataset.items)} items) {args.dataset}")
    print(f"analyzer: {args.analyzer}  model: {model}  neutral_margin: {margin}")
    print()
    print(_report_text("overall sentiment", report.overall))
    print()
    detection = report.aspect_detection
    print(
        f"aspect detection: recall={detection.recall:.4f} "
        f"({detection.detected}/{detection.expected} annotated aspects found); "
        f"{detection.unannotated_detected} more detected but not annotated"
    )
    if detection.missed:
        print("  missed: " + ", ".join(detection.missed))
    if report.aspect_sentiment:
        print()
        print(_report_text("aspect sentiment (annotated and detected)", report.aspect_sentiment))
    print()
    print("timing: " + json.dumps(timing))

    if args.show_errors:
        print()
        print(f"misclassified overall ({len(report.misclassified)}):")
        for m in report.misclassified:
            print(
                f"  {m.id} true={m.expected} pred={m.predicted} "
                f"p(pos/neu/neg)={m.positive_prob:.2f}/{m.neutral_prob:.2f}/{m.negative_prob:.2f}"
                f"  {m.text}"
            )
        if report.aspect_misclassified:
            print("misclassified aspects: " + ", ".join(report.aspect_misclassified))

    swept = []
    if args.sweep:
        swept = evaluation.sweep(outcomes, args.margins)
        print()
        print("neutral margin sweep (overall sentiment; aspect clauses relabeled the same way)")
        print(f"  {'margin':>7}{'accuracy':>10}{'macro_f1':>10}{'asp_acc':>9}{'neutral_pred':>14}")
        for value, swept_report in swept:
            aspect = swept_report.aspect_sentiment
            neutral_pred = sum(row["neutral"] for row in swept_report.overall.confusion.values())
            print(
                f"  {value:>7.2f}{swept_report.overall.accuracy:>10.4f}"
                f"{swept_report.overall.macro_f1:>10.4f}"
                f"{(aspect.accuracy if aspect else float('nan')):>9.4f}{neutral_pred:>14}"
            )

    if args.json_out:
        payload = {
            "dataset": {"name": dataset.name, "version": dataset.version, "n": len(dataset.items)},
            "analyzer": args.analyzer,
            "model": model,
            "timing": timing,
            "report": _full_dict(report),
            "sweep": [_full_dict(r) for _, r in swept],
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")

    if args.enforce and (
        report.overall.accuracy < args.min_accuracy or report.overall.macro_f1 < args.min_macro_f1
    ):
        print(
            f"BELOW THRESHOLD: need accuracy >= {args.min_accuracy} and "
            f"macro_f1 >= {args.min_macro_f1}"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
