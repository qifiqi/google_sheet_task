import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _parse_args():
    parser = argparse.ArgumentParser(description="Run local XPL analysis worker.")
    parser.add_argument("--processes", type=int, default=None, help="Process pool worker count.")
    parser.add_argument("--batch-size", type=int, default=None, help="Number of jobs to claim per loop.")
    parser.add_argument("--poll-interval", type=float, default=None, help="Sleep seconds when no jobs are available.")
    parser.add_argument("--stale-after", type=int, default=None, help="Seconds before a running job is considered stale.")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit.")
    return parser.parse_args()


def _int_config(config_manager, key, default):
    try:
        return int(config_manager.get_config(key, default))
    except (TypeError, ValueError):
        return default


def _float_config(config_manager, key, default):
    try:
        return float(config_manager.get_config(key, default))
    except (TypeError, ValueError):
        return default


def main():
    args = _parse_args()

    from app import create_app
    from app.services.config_manager import get_config_manager
    from app.services.xpl_analysis_worker import XplAnalysisWorker

    app = create_app()
    with app.app_context():
        config_manager = get_config_manager()
        worker = XplAnalysisWorker(
            process_count=args.processes or _int_config(config_manager, "xpl_analysis_worker_processes", 2),
            claim_batch_size=args.batch_size or _int_config(config_manager, "xpl_analysis_claim_batch_size", 4),
            poll_interval_seconds=(
                args.poll_interval
                if args.poll_interval is not None
                else _float_config(config_manager, "xpl_analysis_poll_interval_seconds", 2.0)
            ),
            stale_after_seconds=args.stale_after or _int_config(config_manager, "xpl_analysis_job_timeout_seconds", 300),
        )
        if args.once:
            result = worker.run_once()
            print(
                "XPL worker run once: "
                f"claimed={result.claimed}, completed={result.completed}, failed={result.failed}"
            )
            return
        worker.run_forever()


if __name__ == "__main__":
    main()
