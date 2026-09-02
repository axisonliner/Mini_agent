import time
from pathlib import Path

from animation import Animation, AnimationFrame


class AnimationEngine:
    """
    Керує відтворенням анімацій.

    Engine відповідає тільки за timing та playback.

    Він НЕ відповідає за:
        - PNG decoding
        - OpenCV
        - rendering
        - framebuffer
        - Raspberry Pi
    """

    def __init__(self, fps: int = 24):
        if fps <= 0:
            raise ValueError("FPS must be greater than zero")

        self.fps = fps
        self.tick_duration = 1.0 / fps

        self.current_animation: Animation | None = None

        self.current_frame_index = 0
        self.current_frame_tick = 0

        self.running = False

        self._last_time = time.monotonic()

        # True означає:
        # renderer повинен намалювати поточний кадр.
        self._frame_dirty = False

    # ---------------------------------------------------------
    # Animation control
    # ---------------------------------------------------------

    def set_animation(self, animation: Animation) -> None:
        """
        Встановлює animation та починає її з першого кадру.
        """

        self.current_animation = animation

        self.current_frame_index = 0
        self.current_frame_tick = 0

        self.running = True

        self._last_time = time.monotonic()

        # Нову animation потрібно одразу намалювати.
        self._frame_dirty = True

    def play(self) -> None:
        """
        Запускає playback.
        """

        if self.current_animation is None:
            return

        self.running = True
        self._last_time = time.monotonic()

    def pause(self) -> None:
        """
        Тимчасово зупиняє playback.
        """

        self.running = False

    def stop(self) -> None:
        """
        Повністю зупиняє playback та повертає
        animation на перший кадр.
        """

        self.running = False

        self.current_frame_index = 0
        self.current_frame_tick = 0

        if self.current_animation is not None:
            self._frame_dirty = True

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    def update(self) -> bool:
        """
        Оновлює animation engine.

        Повертає True, якщо renderer повинен
        перемалювати кадр.
        """

        if self.current_animation is None:
            return self.consume_frame_dirty()

        if not self.running:
            return self.consume_frame_dirty()

        now = time.monotonic()
        elapsed = now - self._last_time

        if elapsed < self.tick_duration:
            return self.consume_frame_dirty()

        ticks = int(elapsed / self.tick_duration)

        if ticks <= 0:
            return self.consume_frame_dirty()

        self._last_time += ticks * self.tick_duration

        for _ in range(ticks):
            self._advance_tick()

        return self.consume_frame_dirty()

    def _advance_tick(self) -> None:
        """
        Переміщує playback на один tick вперед.
        """

        animation = self.current_animation

        if animation is None:
            return

        frame = animation.frames[self.current_frame_index]

        self.current_frame_tick += 1

        # Кадр ще повинен залишатися поточним.
        if self.current_frame_tick < frame.hold:
            return

        # Кадр завершився.
        self.current_frame_tick = 0

        next_frame = self.current_frame_index + 1

        # -----------------------------------------------------
        # Animation finished
        # -----------------------------------------------------

        if next_frame >= len(animation.frames):

            if animation.loop:
                next_frame = 0

            else:
                # One-shot animation.
                #
                # Залишаємо останній кадр на екрані.
                next_frame = len(animation.frames) - 1
                self.running = False

        # -----------------------------------------------------
        # Frame changed
        # -----------------------------------------------------

        if next_frame != self.current_frame_index:

            self.current_frame_index = next_frame
            self._frame_dirty = True

    # ---------------------------------------------------------
    # Frame state
    # ---------------------------------------------------------

    def consume_frame_dirty(self) -> bool:
        """
        Повертає True один раз після зміни кадру.

        Це дозволяє renderer'у знати,
        коли саме потрібно перемалювати display.
        """

        if not self._frame_dirty:
            return False

        self._frame_dirty = False

        return True

    def get_current_frame(self) -> AnimationFrame | None:
        """
        Повертає поточний AnimationFrame.
        """

        if self.current_animation is None:
            return None

        return self.current_animation.frames[
            self.current_frame_index
        ]

    def get_current_image(self) -> Path | None:
        """
        Повертає шлях до PNG поточного кадру.
        """

        frame = self.get_current_frame()

        if frame is None:
            return None

        return frame.image

    def get_current_animation_name(self) -> str | None:
        """
        Повертає назву поточної animation.
        """

        if self.current_animation is None:
            return None

        return self.current_animation.name

    def is_running(self) -> bool:
        """
        Чи зараз відтворюється animation.
        """

        return self.running

    def is_finished(self) -> bool:
        """
        True, якщо поточна non-loop animation завершилась.
        """

        return (
            self.current_animation is not None
            and not self.current_animation.loop
            and not self.running
        )
