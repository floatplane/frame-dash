"""Main entry point for Frame Dash.

Orchestrates the fetch → render → push loop.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from .config import Config
from .ha_client import HAClient
from .renderer import Renderer
from .samsung import SamsungFrameClient

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
    samsung: SamsungFrameClient | None,
    output_path: str,
) -> bool:
    """Execute a single fetch → render → push cycle.

    Returns True if successful.
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

        # 2. Render to PNG
        logger.info("Rendering dashboard...")
        renderer.render(data, output_path)

        # 3. Push to Samsung Frame (if configured)
        if samsung and config.samsung_tv_ip:
            logger.info("Pushing to Samsung Frame TV...")
            success = samsung.push_image(output_path)
            if not success:
                logger.warning("Failed to push to TV — will retry next cycle")
                return False
        else:
            logger.info(f"Render-only mode. Dashboard saved to {output_path}")

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
        "--render-only",
        action="store_true",
        help="Only render the dashboard (don't push to TV)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for rendered PNG (default: {data_dir}/dashboard.png)",
    )
    args = parser.parse_args()

    # Load configuration
    config = Config.load()
    output_path = args.output or f"{config.data_dir}/dashboard.png"

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info("Frame Dash starting")
    logger.info(f"  TV IP: {config.samsung_tv_ip or '(render-only)'}")
    logger.info(f"  Resolution: {config.tv_width}x{config.tv_height}")
    logger.info(f"  Update interval: {config.update_interval}s")
    logger.info(f"  Calendars: {config.calendars}")
    logger.info(f"  Theme: {config.theme}")

    # Initialize components
    ha_client = HAClient(config)
    renderer = Renderer(config)
    renderer.start()

    samsung = None
    if not args.render_only and config.samsung_tv_ip:
        samsung = SamsungFrameClient(config)
        if not samsung.check_supported():
            logger.warning(
                "TV does not report art mode support. "
                "Will attempt to push anyway — some TVs report incorrectly."
            )

    try:
        if args.once:
            # Single run
            success = run_once(config, ha_client, renderer, samsung, output_path)
            sys.exit(0 if success else 1)
        else:
            # Continuous loop
            logger.info("Entering main loop...")
            consecutive_failures = 0
            max_failures = 10

            while True:
                success = run_once(config, ha_client, renderer, samsung, output_path)

                if success:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        logger.error(
                            f"{max_failures} consecutive failures. "
                            "Backing off to 10x normal interval."
                        )

                # Sleep until next update
                interval = config.update_interval
                if consecutive_failures >= max_failures:
                    interval *= 10  # Back off on repeated failures

                logger.info(f"Sleeping {interval}s until next update...")
                time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        renderer.stop()
        ha_client.close()


if __name__ == "__main__":
    main()
