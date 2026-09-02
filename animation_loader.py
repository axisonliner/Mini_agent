import json
from pathlib import Path

from animation import Animation, AnimationFrame


class AnimationLoader:
    """
    Loads Animation objects from animation.json.
    """

    def __init__(self, assets_directory: Path):
        self.assets_directory = assets_directory.resolve()

    def load_file(self, json_path: Path) -> dict[str, Animation]:
        json_path = json_path.resolve()

        if not json_path.exists():
            raise FileNotFoundError(
                f"Animation file not found: {json_path}"
            )

        with json_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return self._parse(data)

    def _parse(self, data: dict) -> dict[str, Animation]:
        if isinstance(data.get("frames"), list):
            return {
                "idle": self._parse_animation(
                    "idle",
                    {
                        "frames": [
                            {
                                "image": Path("idle") / frame["source"],
                                "hold": frame.get("hold", 1),
                            }
                            for frame in data["frames"]
                        ],
                        "loop": True,
                    },
                )
            }

        animations_data = data.get("animations")

        if not isinstance(animations_data, dict):
            raise ValueError(
                "animation.json must contain an 'animations' object or a 'frames' list"
            )

        return {
            name: self._parse_animation(name, animation_data)
            for name, animation_data in animations_data.items()
        }

    def _parse_animation(
        self,
        name: str,
        animation_data: dict,
    ) -> Animation:
        frames_data = animation_data.get("frames", [])

        if not isinstance(frames_data, list):
            raise ValueError(
                f"Animation '{name}': frames must be a list"
            )

        frames = []

        for index, frame_data in enumerate(frames_data):
            image = frame_data.get("image")
            hold = frame_data.get("hold", 1)

            if not image:
                raise ValueError(
                    f"Animation '{name}', frame {index}: missing image"
                )

            if not isinstance(hold, int) or hold < 1:
                raise ValueError(
                    f"Animation '{name}', frame {index}: hold must be integer >= 1"
                )

            frames.append(
                AnimationFrame(
                    image=self.assets_directory / image,
                    hold=hold,
                )
            )

        return Animation(
            name=name,
            frames=tuple(frames),
            loop=animation_data.get("loop", True),
        )
