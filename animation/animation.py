from dataclasses import dataclass
from pathlib import Path


@dataclass
class AnimationFrame:
    """
    Один кадр анімації.

    image:
        шлях до PNG-файлу.

    hold:
        скільки ticks показувати кадр.
        При FPS=24:
            hold=1 → ~41.7 ms
            hold=2 → ~83.3 ms
            hold=6 → 250 ms
    """

    image: Path
    hold: int = 1


@dataclass
class Animation:
    """
    Опис однієї анімації.
    """

    name: str
    frames: list[AnimationFrame]
    loop: bool = True

    @property
    def total_ticks(self) -> int:
        """
        Загальна кількість ticks у циклі анімації.
        """
        return sum(frame.hold for frame in self.frames)

    def duration(self, fps: int) -> float:
        if fps <= 0:
            raise ValueError("FPS must be greater than zero")

        return self.total_ticks / fps
