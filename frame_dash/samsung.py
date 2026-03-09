"""Samsung Frame TV art mode integration.

Handles uploading dashboard PNG images to the Frame TV and managing
the art mode display. Uses the samsungtvws library.

Key design decision: we maintain a single "slot" on the TV. Each update:
1. Uploads the new image
2. Selects it as current art
3. Deletes the previous image

This prevents filling up the TV's internal storage over time.
"""

import logging
import time

from samsungtvws import SamsungTVWS

from .config import Config

logger = logging.getLogger(__name__)

# Prefix for images we upload, so we can identify and clean up our own
FRAME_DASH_PREFIX = "frame-dash"


class SamsungFrameClient:
    """Client for pushing images to Samsung Frame TV art mode."""

    def __init__(self, config: Config):
        self.config = config
        self.tv_ip = config.samsung_tv_ip
        self._previous_image_id: str | None = None
        self._token_file = f"{config.data_dir}/samsung-tv-token.txt"

    def _connect(self) -> SamsungTVWS:
        """Create a connection to the TV.

        The token file persists the auth token so you only need to
        accept the permission prompt on the TV once.
        """
        return SamsungTVWS(
            host=self.tv_ip,
            port=8002,
            token_file=self._token_file,
        )

    def check_supported(self) -> bool:
        """Check if the TV supports art mode."""
        try:
            tv = self._connect()
            supported = tv.art().supported()
            logger.info(f"Art mode supported: {supported}")
            return bool(supported)
        except Exception as e:
            logger.error(f"Failed to check art mode support: {e}")
            return False

    def is_art_mode(self) -> bool:
        """Check if the TV is currently in art mode."""
        try:
            tv = self._connect()
            return bool(tv.art().get_artmode())
        except Exception as e:
            logger.warning(f"Could not check art mode status: {e}")
            return False

    def _recover_previous_image_id(self, art) -> None:
        """On first run after restart, find and clean up any orphaned images."""
        try:
            available = art.available()
            if not isinstance(available, list):
                return
            my_images = [
                img for img in available
                if isinstance(img, dict) and img.get("content_type") == "mobile"
            ]
            if not my_images:
                return
            # Keep only the most recent; delete the rest
            my_images.sort(key=lambda x: x.get("image_date", ""))
            for img in my_images[:-1]:
                try:
                    art.delete(img["content_id"])
                    logger.info(f"Cleaned up orphaned image {img['content_id']}")
                except Exception:
                    pass
            self._previous_image_id = my_images[-1]["content_id"]
            logger.info(f"Recovered previous image ID: {self._previous_image_id}")
        except Exception as e:
            logger.warning(f"Could not recover previous image ID: {e}")

    def _is_tv_on(self, ha_client) -> bool:
        """Check TV power state via HA entity, if configured."""
        entity_id = self.config.samsung_tv_entity
        if not entity_id:
            return True  # No entity configured — assume on, let connection decide
        state = ha_client.get_entity_state(entity_id)
        if state is None:
            return True  # Can't determine — try anyway
        on = state.state not in ("off", "unavailable", "unknown")
        if not on:
            logger.info(f"TV is {state.state}, skipping push")
        return on

    def push_image(self, image_path: str, ha_client=None) -> bool:
        """Upload a PNG image and set it as the current art.

        Returns True if successful.
        """
        if ha_client and not self._is_tv_on(ha_client):
            return True  # TV is off — skip silently

        try:
            tv = self._connect()
            art = tv.art()

            # On first push after a restart, clean up any orphaned images
            if self._previous_image_id is None:
                self._recover_previous_image_id(art)

            # Read the image file
            with open(image_path, "rb") as f:
                image_data = f.read()

            logger.info(f"Uploading image ({len(image_data)} bytes) to Frame TV...")

            # Upload the new image (no matte — full screen dashboard)
            new_id = art.upload(
                image_data,
                file_type="PNG",
                matte="none",
            )
            logger.info(f"Uploaded image with ID: {new_id}")

            # Select the new image as current art.
            # Use show=True only if already in art mode — this switches the displayed
            # image without forcing art mode on when the user is watching TV.
            if new_id:
                in_art_mode = bool(tv.art().get_artmode())
                art.select_image(new_id, show=in_art_mode)
                logger.info(f"Selected image {new_id} as current art (show={in_art_mode})")

            # Clean up the previous image — must happen after selecting the new one
            # so the TV isn't trying to delete the currently displayed image
            if self._previous_image_id and self._previous_image_id != new_id:
                try:
                    time.sleep(1)
                    art.delete(self._previous_image_id)
                    logger.info(f"Deleted previous image {self._previous_image_id}")
                except Exception as e:
                    logger.warning(f"Could not delete previous image: {e}")

            self._previous_image_id = new_id

            return True

        except (ConnectionRefusedError, OSError, TimeoutError) as e:
            logger.info(f"TV unreachable (probably off): {e}")
            return True  # Not a real failure — skip silently
        except Exception as e:
            logger.error(f"Failed to push image to Frame TV: {e}")
            return False

    def cleanup_old_images(self) -> int:
        """Remove all previously uploaded Frame Dash images from the TV.

        Useful for maintenance. Returns count of deleted images.
        """
        try:
            tv = self._connect()
            art = tv.art()
            available = art.available()

            if not isinstance(available, list):
                return 0

            # Find images with our content_id pattern
            deleted = 0
            my_images = [
                img for img in available
                if isinstance(img, dict)
                and img.get("content_id", "").startswith("MY-")
            ]

            # Be conservative: only delete if we have more than 2 of our own
            if len(my_images) > 2:
                for img in my_images[:-1]:  # Keep the most recent
                    try:
                        art.delete(img["content_id"])
                        deleted += 1
                    except Exception:
                        pass

            logger.info(f"Cleaned up {deleted} old images")
            return deleted

        except Exception as e:
            logger.error(f"Failed to clean up old images: {e}")
            return 0
