"""Main entry point for Frame Dash.

Orchestrates the fetch → render → push loop: pulls data from Home Assistant,
renders a grayscale dashboard, and pushes it to a TRMNL Webhook Image plugin so
it shows up in the device's playlist.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from . import webhook
from .config import Config
from .ha_client import HAClient
from .renderer import Renderer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("frame_dash")


def run_once(
    config: Config,
    ha_client: HAClient,
    renderer: Renderer,
    output_path: str | None = None,
) -> bool:
    """Execute a single fetch → render → push cycle.

    Returns True if the fetch and render succeeded. The webhook push is
    best-effort and does not fail the cycle (so a rate limit or a flaky network
    to TRMNL doesn't trigger backoff).
    """
    try:
        # 1. Fetch data from Home Assistant
        logger.info("Fetching dashboard data from Home Assistant...")
        data = ha_client.fetch_dashboard_data()
        logger.info(
            f"Fetched: {len(data.events_today)} events today, "
            f"{len(data.events_tomorrow)} tomorrow, "
            f"{len(data.attention_items)} attention items"
        )

        # 2. Render the grayscale e-ink image
        logger.info("Rendering dashboard...")
        png = renderer.render_eink(data)
        logger.info(f"Rendered e-ink image ({len(png)} bytes)")

        # 3. Push to the TRMNL Webhook Image plugin
        if config.eink_webhook_url:
            webhook.push_image(config.eink_webhook_url, png)
        else:
            logger.warning("No eink_webhook_url configured — rendered but not pushed")

        # 4. Optionally write a copy to disk (debugging / --once inspection)
        if output_path:
            Path(output_path).write_bytes(png)
            logger.info(f"Wrote image to {output_path}")

        return True

    except Exception as e:
        logger.error(f"Error in update cycle: {e}", exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="Frame Dash - Family Dashboard")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single update cycle and exit",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Also write the rendered PNG to this path",
    )
    args = parser.parse_args()

    # Load configuration
    config = Config.load()

    logger.info("Frame Dash starting")
    logger.info(f"  Resolution: {config.eink_width}x{config.eink_height}")
    logger.info(f"  Update interval: {config.update_interval}s")
    logger.info(f"  Webhook: {'configured' if config.eink_webhook_url else 'NOT configured'}")
    logger.info(f"  Calendars: {config.calendars}")

    # Initialize components
    ha_client = HAClient(config)
    renderer = Renderer(config)
    renderer.start()

    try:
        if args.once:
            # Single run
            success = run_once(config, ha_client, renderer, output_path=args.output)
            sys.exit(0 if success else 1)
        else:
            # Continuous loop
            logger.info("Entering main loop...")
            consecutive_failures = 0
            max_failures = 10

            while True:
                success = run_once(config, ha_client, renderer, output_path=args.output)

                if success:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        logger.error(
                            f"{max_failures} consecutive failures. "
                            "Backing off to 10x normal interval."
                        )

                # Sleep until the next aligned clock boundary
                interval = config.update_interval
                if consecutive_failures >= max_failures:
                    interval *= 10  # Back off on repeated failures

                now_ts = time.time()
                next_tick = (now_ts // interval + 1) * interval
                sleep_secs = next_tick - now_ts
                logger.info(f"Sleeping {sleep_secs:.1f}s until next update...")
                time.sleep(sleep_secs)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        renderer.stop()
        ha_client.close()


if __name__ == "__main__":
    main()
