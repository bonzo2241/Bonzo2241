#!/usr/bin/env python3
"""
Entry point for the LMS multi-agent platform.

Usage:
    # Run web app only (no XMPP server required):
    python run.py --web-only

    # Run with SPADE agents (requires XMPP server):
    python run.py

Environment variables:
    XMPP_SERVER    – XMPP server hostname (default: localhost)
    SECRET_KEY     – Flask secret key
    FLASK_PORT     – Web server port (default: 5000)
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import threading

from app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("lms")


def run_flask(app, port: int):
    """Run the Flask dev server in a separate thread."""
    app.run(host="192.168.0.14", port=port, debug=False, use_reloader=False)


def main():
    parser = argparse.ArgumentParser(description="LMS Multi-Agent Platform")
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="Run the web interface only, without starting SPADE agents.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("FLASK_PORT", 5000)),
        help="Port for the Flask web server (default: 5000).",
    )
    args = parser.parse_args()

    app = create_app()

    if args.web_only:
        log.info("Starting LMS in web-only mode (no agents).")
        log.info("Open http://192.168.0.14:%d in your browser.", args.port)
        app.run(host="192.168.0.14", port=args.port, debug=True)
        return

    # --- Full mode: web + SPADE agents ---
    from agents import set_flask_app, start_agents, stop_agents

    set_flask_app(app)

    # Start Flask in a background thread
    flask_thread = threading.Thread(
        target=run_flask, args=(app, args.port), daemon=True,
    )
    flask_thread.start()
    log.info("Flask web server started on port %d.", args.port)

    # Start SPADE agents in the asyncio event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown():
        log.info("Shutting down agents …")
        loop.run_until_complete(stop_agents())
        loop.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, lambda *_: shutdown())
    signal.signal(signal.SIGTERM, lambda *_: shutdown())

    try:
        log.info("Starting SPADE agents …")
        loop.run_until_complete(start_agents())
        log.info("All agents are running. Press Ctrl+C to stop.")
        loop.run_forever()
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
