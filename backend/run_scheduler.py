"""Dedicated scheduler process entrypoint.

Production topology (recommended):
    Terminal A (API, stateless, N workers):   gunicorn -w 4 -b 0.0.0.0:5000 app:app
    Terminal B (background work, exactly 1):   python run_scheduler.py

Run ONLY ONE scheduler process. A Redis leader-lock guards against accidental
double-start, but the intended deployment is a single dedicated process here while
the web app runs with START_SCHEDULER_IN_APP unset/false.
"""
import time

from config import config
from services import (
    scheduler_service,
    start_direction_scheduler,
    stop_direction_scheduler,
)


def main():
    # Fail fast on unsafe config (insecure secrets, DEBUG+LIVE, ...).
    config.validate()
    print(f"[scheduler] Starting background workers in {config.EXECUTION_MODE} mode")

    scheduler_service.start()
    start_direction_scheduler()

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("[scheduler] Shutting down...")
        scheduler_service.stop()
        stop_direction_scheduler()


if __name__ == '__main__':
    main()
