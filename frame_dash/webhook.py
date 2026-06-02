"""Push the rendered dashboard image to a TRMNL Webhook Image plugin.

The TRMNL "Webhook Image" plugin gives you a private URL; POSTing a PNG to it
updates that plugin's content in the device's playlist, so Frame Dash shows up
as one screen alongside any other plugins you've added.

See: https://help.trmnl.com/en/articles/13213669-webhook-image
"""

import logging

import httpx

logger = logging.getLogger(__name__)


def push_image(url: str, png: bytes, timeout: float = 30.0) -> bool:
    """POST a PNG to the TRMNL Webhook Image URL. Returns True on success.

    Best-effort: failures (network, rate limit) are logged and swallowed so a
    flaky push doesn't take down the render loop. TRMNL caps uploads at 12/hour.
    """
    try:
        resp = httpx.post(
            url,
            content=png,
            headers={"Content-Type": "image/png"},
            timeout=timeout,
        )
        if resp.status_code == 429:
            logger.warning(
                "TRMNL rate limit hit (12 uploads/hour) — skipping this push. "
                "Increase update_interval if this recurs."
            )
            return False
        resp.raise_for_status()
        logger.info(f"Pushed image to TRMNL webhook ({len(png)} bytes)")
        return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to push image to TRMNL webhook: {e}")
        return False
