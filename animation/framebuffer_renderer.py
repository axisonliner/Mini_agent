from pathlib import Path

import numpy as np
from PIL import Image


class FramebufferRenderer:
    """
    Простий renderer для Linux framebuffer.

    Приймає PNG 480x320 і перетворює його
    у RGB565 для /dev/fb0.
    """

    def __init__(
        self,
        framebuffer: str = "/dev/fb0",
        width: int = 480,
        height: int = 320,
    ):
        self.framebuffer_path = Path(framebuffer)

        self.width = width
        self.height = height

        self.framebuffer = None

    def open(self):
        """
        Відкриває framebuffer.
        """

        if not self.framebuffer_path.exists():
            raise FileNotFoundError(
                f"Framebuffer not found: {self.framebuffer_path}"
            )

        self.framebuffer = self.framebuffer_path.open(
            "r+b",
            buffering=0,
        )

    def close(self):
        """
        Закриває framebuffer.
        """

        if self.framebuffer is not None:
            self.framebuffer.close()
            self.framebuffer = None

    def render(self, image_path: Path):
        """
        Завантажує PNG, конвертує його в RGB565
        та записує у framebuffer.
        """

        if self.framebuffer is None:
            raise RuntimeError(
                "Framebuffer is not open"
            )

        image = Image.open(image_path)

        # Гарантуємо правильний розмір.
        if image.size != (self.width, self.height):
            image = image.resize(
                (self.width, self.height),
                Image.Resampling.NEAREST,
            )

        # Переводимо в RGB.
        image = image.convert("RGB")

        pixels = np.asarray(image, dtype=np.uint16)

        r = pixels[:, :, 0]
        g = pixels[:, :, 1]
        b = pixels[:, :, 2]

        # RGB888 → RGB565
        rgb565 = (
            ((r >> 3) << 11)
            | ((g >> 2) << 5)
            | (b >> 3)
        )

        # Raspberry Pi framebuffer / ILI9486
        # очікує байти RGB565 у big-endian порядку.
        data = rgb565.byteswap().tobytes()

        self.framebuffer.seek(0)
        self.framebuffer.write(data)
