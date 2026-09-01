from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


# ============================================================
# Display configuration
# ============================================================

DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 320

FPS = 24.0
TICK_TIME = 1.0 / FPS

FRAMEBUFFER = "/dev/fb0"


# ============================================================
# Animation
# ============================================================

@dataclass(frozen=True)
class Animation:
    """
    Description of an animation.

    frames:
        List of:

            ("filename.png", hold)

        hold is the number of 24 FPS timeline ticks.

        Example:

            ("001.png", 6)

        means:

            6 / 24 = 0.25 seconds

    loop:
        True  -> repeat animation
        False -> play once
    """

    name: str
    frames: list[tuple[str, int]]
    loop: bool = True


# ============================================================
# Framebuffer
# ============================================================

class FramebufferDisplay:
    """
    Interface to Linux framebuffer /dev/fb0.
    """

    def __init__(
        self,
        device: str = FRAMEBUFFER,
    ):
        self.device = device

        if not os.path.exists(device):
            raise RuntimeError(
                f"Framebuffer not found: {device}"
            )

        self.file = open(
            device,
            "r+b",
            buffering=0,
        )

        self.lock = threading.Lock()

    def show(self, data: bytes) -> None:
        """
        Write one RGB565 frame to the display.
        """

        with self.lock:
            self.file.seek(0)
            self.file.write(data)

    def close(self) -> None:
        self.file.close()


# ============================================================
# Image conversion
# ============================================================

def prepare_image(
    image: Image.Image,
) -> bytes:
    """
    Convert PNG image to RGB565 framebuffer data.

    Supported input:

        RGB
        RGBA

    RGBA images are composited over a black background.

    The resulting data is exactly:

        480 × 320 × 2 bytes
    """

    if image.size != (
        DISPLAY_WIDTH,
        DISPLAY_HEIGHT,
    ):
        raise ValueError(
            "Invalid image size: "
            f"{image.size}. "
            f"Expected "
            f"{DISPLAY_WIDTH}x{DISPLAY_HEIGHT}."
        )

    # --------------------------------------------------------
    # RGBA support
    # --------------------------------------------------------

    if image.mode == "RGBA":

        background = Image.new(
            "RGBA",
            image.size,
            (0, 0, 0, 255),
        )

        image = Image.alpha_composite(
            background,
            image,
        )

    image = image.convert("RGB")

    pixels = image.load()

    output = bytearray(
        DISPLAY_WIDTH
        * DISPLAY_HEIGHT
        * 2
    )

    index = 0

    for y in range(DISPLAY_HEIGHT):

        for x in range(DISPLAY_WIDTH):

            r, g, b = pixels[x, y]

            # RGB888 -> RGB565

            r5 = r >> 3
            g6 = g >> 2
            b5 = b >> 3

            value = (
                (r5 << 11)
                | (g6 << 5)
                | b5
            )

            # Little endian

            output[index] = (
                value & 0xFF
            )

            output[index + 1] = (
                value >> 8
            )

            index += 2

    return bytes(output)


# ============================================================
# Animation cache
# ============================================================

class AnimationCache:
    """
    Converts PNG files to RGB565 once and keeps the result
    in RAM.

    This prevents PNG decoding and RGB565 conversion from
    happening during animation playback.
    """

    def __init__(
        self,
        assets_directory: str | Path,
    ):
        self.assets_directory = Path(
            assets_directory
        )

        self.cache: dict[
            tuple[str, str],
            bytes,
        ] = {}

        self.lock = threading.Lock()

    def get(
        self,
        animation: Animation,
        filename: str,
    ) -> bytes:

        key = (
            animation.name,
            filename,
        )

        # ----------------------------------------------------
        # Already converted?
        # ----------------------------------------------------

        with self.lock:

            if key in self.cache:
                return self.cache[key]

        # ----------------------------------------------------
        # Find PNG.
        # ----------------------------------------------------

        path = (
            self.assets_directory
            / animation.name
            / filename
        )

        if not path.exists():

            raise FileNotFoundError(
                f"Animation frame not found:\n"
                f"{path}"
            )

        print(
            f"[Cache] loading {path}"
        )

        # ----------------------------------------------------
        # Load PNG.
        # ----------------------------------------------------

        image = Image.open(path)

        # ----------------------------------------------------
        # Convert once.
        # ----------------------------------------------------

        data = prepare_image(image)

        # ----------------------------------------------------
        # Store in RAM.
        # ----------------------------------------------------

        with self.lock:

            self.cache[key] = data

        return data


# ============================================================
# Animation Controller
# ============================================================

class AnimationController:
    """
    Controls all animation states.

    Base state:

        idle
        listening
        thinking
        speaking

    Actions:

        blink
        look_left
        surprise
        ...

    There is ONE playback thread.

    This is intentional.

    The controller decides what should be displayed on every
    animation tick.
    """

    def __init__(
        self,
        display: FramebufferDisplay,
        assets_directory: str | Path,
    ):

        self.display = display

        self.cache = AnimationCache(
            assets_directory
        )

        # ----------------------------------------------------
        # Registered animations
        # ----------------------------------------------------

        self.animations: dict[
            str,
            Animation,
        ] = {}

        self.actions: dict[
            str,
            Animation,
        ] = {}

        # ----------------------------------------------------
        # Current base state
        # ----------------------------------------------------

        self._state: str | None = None

        # ----------------------------------------------------
        # Current action
        # ----------------------------------------------------

        self._action: str | None = None

        # ----------------------------------------------------
        # Synchronization
        # ----------------------------------------------------

        self._lock = threading.Lock()

        self._wake = threading.Event()

        self._stop = threading.Event()

        # ----------------------------------------------------
        # Playback thread
        # ----------------------------------------------------

        self._thread = threading.Thread(
            target=self._playback_loop,
            name="AnimationController",
            daemon=True,
        )

    # ========================================================
    # Registration
    # ========================================================

    def add_animation(
        self,
        animation: Animation,
    ) -> None:

        if not animation.frames:
            raise ValueError(
                f"Animation '{animation.name}' "
                f"has no frames."
            )

        for filename, hold in animation.frames:

            if hold < 1:
                raise ValueError(
                    f"Invalid hold={hold} "
                    f"in animation "
                    f"'{animation.name}', "
                    f"frame '{filename}'."
                )

        self.animations[
            animation.name
        ] = animation

    def add_action(
        self,
        animation: Animation,
    ) -> None:

        if not animation.frames:
            raise ValueError(
                f"Action '{animation.name}' "
                f"has no frames."
            )

        for filename, hold in animation.frames:

            if hold < 1:
                raise ValueError(
                    f"Invalid hold={hold} "
                    f"in action "
                    f"'{animation.name}', "
                    f"frame '{filename}'."
                )

        self.actions[
            animation.name
        ] = animation

    # ========================================================
    # Base state
    # ========================================================

    def set_state(
        self,
        state: str,
    ) -> None:
        """
        Immediately change the base animation state.

        Example:

            controller.set_state("thinking")
        """

        if state not in self.animations:

            raise ValueError(
                f"Unknown animation state: "
                f"{state}"
            )

        with self._lock:

            self._state = state

        print(
            f"[Animation] state -> {state}"
        )

        # Wake playback thread immediately.
        self._wake.set()

    @property
    def state(self) -> str | None:

        with self._lock:
            return self._state

    # ========================================================
    # Actions
    # ========================================================

    def play_action(
        self,
        action: str,
    ) -> None:
        """
        Play a short one-shot action.

        Example:

            controller.play_action("blink")

        The action temporarily overrides the base state.

        After it finishes, the base state continues.
        """

        if action not in self.actions:

            raise ValueError(
                f"Unknown animation action: "
                f"{action}"
            )

        with self._lock:

            self._action = action

        print(
            f"[Animation] action -> {action}"
        )

        # Wake playback immediately.
        self._wake.set()

    # ========================================================
    # Start
    # ========================================================

    def start(self) -> None:

        if self._thread.is_alive():
            return

        self._thread.start()

    # ========================================================
    # Stop
    # ========================================================

    def stop(self) -> None:

        self._stop.set()

        self._wake.set()

        if self._thread.is_alive():

            self._thread.join()

    # ========================================================
    # Playback
    # ========================================================

    def _playback_loop(self) -> None:

        base_frame_index = 0
        base_hold_remaining = 0

        action_frame_index = 0
        action_hold_remaining = 0

        current_base = None
        current_action = None

        while not self._stop.is_set():

            # ==================================================
            # Read current state
            # ==================================================

            with self._lock:

                state_name = self._state
                action_name = self._action

            # ==================================================
            # ACTION has priority over BASE state
            # ==================================================

            if action_name is not None:

                # ----------------------------------------------
                # New action?
                # ----------------------------------------------

                if action_name != current_action:

                    current_action = action_name

                    action_frame_index = 0

                    action_hold_remaining = 0

                animation = self.actions[
                    action_name
                ]

                # ----------------------------------------------
                # Display next action frame.
                # ----------------------------------------------

                if action_hold_remaining <= 0:

                    if (
                        action_frame_index
                        >= len(animation.frames)
                    ):
                        # Action finished.

                        with self._lock:

                            # Only clear it if it is
                            # still the same action.
                            if (
                                self._action
                                == action_name
                            ):
                                self._action = None

                        current_action = None

                        continue

                    filename, hold = (
                        animation.frames[
                            action_frame_index
                        ]
                    )

                    data = self.cache.get(
                        animation,
                        filename,
                    )

                    self.display.show(data)

                    action_hold_remaining = hold

                    action_frame_index += 1

                # ----------------------------------------------
                # One 24 FPS timeline tick.
                # ----------------------------------------------

                action_hold_remaining -= 1

                self._wait_tick()

                continue

            # ==================================================
            # BASE STATE
            # ==================================================

            if state_name is None:

                self._wait_tick()

                continue

            animation = self.animations[
                state_name
            ]

            # --------------------------------------------------
            # State changed?
            # --------------------------------------------------

            if state_name != current_base:

                current_base = state_name

                base_frame_index = 0

                base_hold_remaining = 0

            # --------------------------------------------------
            # End of animation
            # --------------------------------------------------

            if (
                base_frame_index
                >= len(animation.frames)
            ):

                if animation.loop:

                    base_frame_index = 0

                else:

                    base_frame_index = (
                        len(animation.frames) - 1
                    )

                    base_hold_remaining = 1

            # --------------------------------------------------
            # Display next base frame.
            # --------------------------------------------------

            if base_hold_remaining <= 0:

                filename, hold = (
                    animation.frames[
                        base_frame_index
                    ]
                )

                data = self.cache.get(
                    animation,
                    filename,
                )

                self.display.show(data)

                base_hold_remaining = hold

                base_frame_index += 1

            # --------------------------------------------------
            # One 24 FPS timeline tick.
            # --------------------------------------------------

            base_hold_remaining -= 1

            self._wait_tick()

    # ========================================================
    # Timeline
    # ========================================================

    def _wait_tick(self) -> None:

        """
        Wait approximately one 24 FPS timeline tick.

        The wait can be interrupted immediately when:

            - state changes
            - action starts
            - engine stops
        """

        self._wake.wait(
            timeout=TICK_TIME
        )

        self._wake.clear()
