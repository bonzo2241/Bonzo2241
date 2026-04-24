#!/usr/bin/env python3
"""
Entry point for the LMS multi-agent platform.
"""

import argparse
import asyncio
import logging
import os
import signal
import threading

from app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("lms")


def run_flask(app, port: int):
    """Run the Flask dev server in a separate thread."""
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def main():
    parser = argparse.ArgumentParser(description="LMS Multi-Agent Platform")
    parser.add_argument("--web-only", action="store_true", help="Run only Flask web interface.")
    parser.add_argument(
        "--transport",
        choices=["local", "openclaw"],
        default="local",
        help="Agent transport backend.",
    )
    parser.add_argument(
        "--agent-role",
        choices=["all", "orchestrator", "monitoring", "adaptation", "notification"],
        default="all",
        help="Run all agents or one selected role.",
    )
    parser.add_argument(
        "--agent-only",
        action="store_true",
        help="Run only agents (no Flask server).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("FLASK_PORT", 5000)),
        help="Flask port.",
    )
    args = parser.parse_args()

    if args.web_only and args.agent_only:
        raise SystemExit("Cannot combine --web-only and --agent-only")

    app = create_app()

    if args.web_only:
        log.info("Starting LMS in web-only mode (no agents).")
        app.run(host="0.0.0.0", port=args.port, debug=True)
        return

    from agents import set_flask_app, start_agents, stop_agents, watch_agents

    set_flask_app(app)
    roles = None if args.agent_role == "all" else [args.agent_role]

    flask_thread = None
    if not args.agent_only:
        flask_thread = threading.Thread(target=run_flask, args=(app, args.port), daemon=True)
        flask_thread.start()
        log.info("Flask web server started on port %d.", args.port)
    else:
        log.info("Starting agent-only mode (role=%s, transport=%s).", args.agent_role, args.transport)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    watch_task = None

    async def _graceful_stop():
        nonlocal watch_task
        if watch_task is not None:
            watch_task.cancel()
            await asyncio.gather(watch_task, return_exceptions=True)
        await stop_agents()
        loop.stop()

    def shutdown(*_):
        asyncio.ensure_future(_graceful_stop(), loop=loop)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        log.info("Starting agents …")
        loop.run_until_complete(start_agents(transport_mode=args.transport, roles=roles))
        watch_task = asyncio.ensure_future(watch_agents(), loop=loop)
        loop.run_forever()
    except Exception as exc:
        log.error("Agent runtime failed: %s", exc)
        if flask_thread is not None:
            flask_thread.join()
    finally:
        if not loop.is_closed():
            loop.close()


if __name__ == "__main__":
    main()
