

import time
from pathlib import Path

from animation_engine import AnimationEngine
from animation_loader import AnimationLoader
from framebuffer_renderer import FramebufferRenderer


FPS = 24

BASE_DIRECTORY = Path(__file__).resolve().parent

ASSETS_DIRECTORY = BASE_DIRECTORY / "assets"
ANIMATION_FILE = BASE_DIRECTORY / "cache" / "animation.json"

FRAMEBUFFER = "/dev/fb0"

WIDTH = 480
HEIGHT = 320


def main():

    # ---------------------------------------------------------
    # Load animations
    # ---------------------------------------------------------

    loader = AnimationLoader(
        assets_directory=ASSETS_DIRECTORY
    )

    animations = loader.load_file(
        ANIMATION_FILE
    )

    if "idle" not in animations:
        raise RuntimeError(
            "Animation 'idle' was not found"
        )

    idle = animations["idle"]

    print()
    print("Idle Animation Test")
    print("-------------------")
    print(f"Frames: {len(idle.frames)}")
    print(f"Ticks: {idle.total_ticks}")
    print(f"FPS: {FPS}")
    print(f"Duration: {idle.duration(FPS):.3f} sec")
    print()

    # ---------------------------------------------------------
    # Animation engine
    # ---------------------------------------------------------

    engine = AnimationEngine(
        fps=FPS
    )

    engine.set_animation(idle)

    # ---------------------------------------------------------
    # Framebuffer renderer
    # ---------------------------------------------------------

    renderer = FramebufferRenderer(
        framebuffer=FRAMEBUFFER,
        width=WIDTH,
        height=HEIGHT,
    )

    renderer.open()

    try:

        print("Starting idle animation...")
        print("Press Ctrl+C to stop.")
        print()

        last_frame = None

        while True:

            if engine.update():

                frame = engine.get_current_frame()

                if frame is None:
                    continue

                if engine.current_frame_index != last_frame:

                    print(
                        f"frame={engine.current_frame_index:02d} "
                        f"hold={frame.hold} "
                        f"{frame.image.name}"
                    )

                    renderer.render(
                        frame.image
                    )

                    last_frame = (
                        engine.current_frame_index
                    )

            time.sleep(0.001)

    except KeyboardInterrupt:

        print()
        print("Stopping...")

    finally:

        renderer.close()


if __name__ == "__main__":
    main()
