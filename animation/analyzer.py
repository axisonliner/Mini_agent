from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIRECTORY = Path(__file__).resolve().parent

ASSETS_DIRECTORY = BASE_DIRECTORY / "assets" / "idle"
CACHE_DIRECTORY = BASE_DIRECTORY / "cache"
DEBUG_DIRECTORY = BASE_DIRECTORY / "debug"

CACHE_FILE = CACHE_DIRECTORY / "animation.json"

# Animation timeline.
FPS = 24

# Brightness threshold.
#
# Pixels brighter than this value become part
# of the eye mask.
#
# This is intentionally configurable because
# we will tune it against the real animation.
THRESHOLD = 30

# Ignore very small objects.
MIN_EYE_AREA = 100

# Maximum number of candidate objects.
MAX_CANDIDATES = 10

# Maximum distance used when trying to associate
# an eye with an eye from the previous frame.
MAX_TRACK_DISTANCE = 180


# ============================================================
# UTILITIES
# ============================================================

def calculate_file_hash(path: Path) -> str:
    """
    Calculate SHA-256 hash of a PNG file.

    The hash allows us to detect whether a source
    frame has changed since the previous analysis.
    """

    sha256 = hashlib.sha256()

    with open(path, "rb") as file:

        while True:

            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


# ============================================================
# EYE DETECTION
# ============================================================

def detect_objects(gray: np.ndarray) -> tuple[np.ndarray, list[dict]]:
    """
    Detect bright connected objects in a grayscale image.

    Returns:

        mask
        objects
    """

    # --------------------------------------------------------
    # Convert grayscale image into a binary mask.
    # --------------------------------------------------------

    _, mask = cv2.threshold(
        gray,
        THRESHOLD,
        255,
        cv2.THRESH_BINARY,
    )

    # --------------------------------------------------------
    # Small morphological cleanup.
    #
    # This removes isolated single pixels/noise.
    # --------------------------------------------------------

    kernel = np.ones(
        (3, 3),
        np.uint8,
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        kernel,
    )

    # --------------------------------------------------------
    # Find external contours.
    # --------------------------------------------------------

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    objects = []

    for contour in contours:

        area = cv2.contourArea(contour)

        if area < MIN_EYE_AREA:
            continue

        x, y, width, height = cv2.boundingRect(
            contour
        )

        moments = cv2.moments(contour)

        if moments["m00"] != 0:

            center_x = (
                moments["m10"] /
                moments["m00"]
            )

            center_y = (
                moments["m01"] /
                moments["m00"]
            )

        else:

            center_x = x + width / 2
            center_y = y + height / 2

        objects.append(
            {
                "x": int(x),
                "y": int(y),

                "width": int(width),
                "height": int(height),

                "area": float(area),

                "center_x": float(center_x),
                "center_y": float(center_y),

                "contour": contour,
            }
        )

    # --------------------------------------------------------
    # Largest objects first.
    # --------------------------------------------------------

    objects.sort(
        key=lambda obj: obj["area"],
        reverse=True,
    )

    return mask, objects[:MAX_CANDIDATES]


# ============================================================
# EYE MATCHING
# ============================================================

def distance(
    eye_a: dict,
    eye_b: dict,
) -> float:

    dx = (
        eye_a["center_x"] -
        eye_b["center_x"]
    )

    dy = (
        eye_a["center_y"] -
        eye_b["center_y"]
    )

    return float(
        (dx * dx + dy * dy) ** 0.5
    )


def classify_eyes(
    objects: list[dict],
    previous: dict | None,
) -> tuple[dict | None, dict | None]:
    """
    Determine which detected objects correspond
    to the left and right eye.

    The analyzer supports:

        0 eyes
        1 eye
        2 eyes
    """

    if not objects:

        return None, None

    # --------------------------------------------------------
    # No previous frame.
    #
    # Use horizontal position.
    # --------------------------------------------------------

    if previous is None:

        objects = sorted(
            objects,
            key=lambda obj: obj["center_x"],
        )

        if len(objects) == 1:

            # We cannot know with certainty whether
            # this is left or right.
            #
            # Use the center of the screen as reference.

            if objects[0]["center_x"] < 240:

                return objects[0], None

            return None, objects[0]

        return objects[0], objects[1]

    previous_left = previous.get(
        "left_eye"
    )

    previous_right = previous.get(
        "right_eye"
    )

    # --------------------------------------------------------
    # One detected object.
    #
    # Try to match it to the previous left/right eye.
    # --------------------------------------------------------

    if len(objects) == 1:

        current = objects[0]

        candidates = []

        if previous_left is not None:

            candidates.append(
                (
                    distance(
                        current,
                        previous_left,
                    ),
                    "left",
                )
            )

        if previous_right is not None:

            candidates.append(
                (
                    distance(
                        current,
                        previous_right,
                    ),
                    "right",
                )
            )

        if candidates:

            candidates.sort(
                key=lambda item: item[0]
            )

            best_distance, side = candidates[0]

            if best_distance <= MAX_TRACK_DISTANCE:

                if side == "left":

                    return current, None

                return None, current

        # ----------------------------------------------------
        # Tracking failed.
        #
        # Fall back to screen position.
        # ----------------------------------------------------

        if current["center_x"] < 240:

            return current, None

        return None, current

    # --------------------------------------------------------
    # Two or more objects.
    #
    # Find the best left/right combination.
    # --------------------------------------------------------

    best_pair = None
    best_score = float("inf")

    for left in objects:

        for right in objects:

            if left is right:
                continue

            if left["center_x"] >= right["center_x"]:
                continue

            score = 0.0

            # ------------------------------------------------
            # Prefer previous eye positions.
            # ------------------------------------------------

            if previous_left is not None:

                score += distance(
                    left,
                    previous_left,
                )

            else:

                score += abs(
                    left["center_x"] - 120
                )

            if previous_right is not None:

                score += distance(
                    right,
                    previous_right,
                )

            else:

                score += abs(
                    right["center_x"] - 360
                )

            if score < best_score:

                best_score = score

                best_pair = (
                    left,
                    right,
                )

    if best_pair is not None:

        return best_pair

    return objects[0], objects[1]


# ============================================================
# CONTOUR SERIALIZATION
# ============================================================

def normalize_contour(
    contour: np.ndarray,
    x: int,
    y: int,
    width: int,
    height: int,
) -> list[list[float]]:
    """
    Convert contour coordinates into normalized
    0..1 coordinates relative to the eye bounding box.

    This makes the shape independent of its size.
    """

    if width <= 0 or height <= 0:

        return []

    points = []

    for point in contour:

        px = float(point[0][0])
        py = float(point[0][1])

        nx = (
            px - x
        ) / width

        ny = (
            py - y
        ) / height

        points.append(
            [
                round(nx, 5),
                round(ny, 5),
            ]
        )

    return points


# ============================================================
# EYE SERIALIZATION
# ============================================================

def serialize_eye(
    eye: dict | None,
) -> dict | None:

    if eye is None:

        return None

    contour = eye["contour"]

    shape = normalize_contour(
        contour,
        eye["x"],
        eye["y"],
        eye["width"],
        eye["height"],
    )

    return {
        "visible": True,

        "x": eye["x"],
        "y": eye["y"],

        "width": eye["width"],
        "height": eye["height"],

        "center_x": round(
            eye["center_x"],
            3,
        ),

        "center_y": round(
            eye["center_y"],
            3,
        ),

        "area": round(
            eye["area"],
            3,
        ),

        "shape": shape,
    }


# ============================================================
# MOTION
# ============================================================

def calculate_motion(
    current: dict | None,
    previous: dict | None,
) -> dict:

    if current is None:

        return {
            "visible": False,
        }

    if previous is None:

        return {
            "visible": True,

            "dx": 0.0,
            "dy": 0.0,

            "dwidth": 0.0,
            "dheight": 0.0,

            "velocity_x": 0.0,
            "velocity_y": 0.0,
        }

    dt = 1.0 / FPS

    dx = (
        current["center_x"] -
        previous["center_x"]
    )

    dy = (
        current["center_y"] -
        previous["center_y"]
    )

    dwidth = (
        current["width"] -
        previous["width"]
    )

    dheight = (
        current["height"] -
        previous["height"]
    )

    return {
        "visible": True,

        "dx": round(dx, 3),
        "dy": round(dy, 3),

        "dwidth": round(
            dwidth,
            3,
        ),

        "dheight": round(
            dheight,
            3,
        ),

        "velocity_x": round(
            dx / dt,
            3,
        ),

        "velocity_y": round(
            dy / dt,
            3,
        ),
    }


# ============================================================
# FRAME ANALYZER
# ============================================================

def analyze_frame(
    image_path: Path,
    previous: dict | None,
    debug: bool = True,
) -> dict:

    # --------------------------------------------------------
    # Read image.
    # --------------------------------------------------------

    image = cv2.imread(
        str(image_path),
        cv2.IMREAD_GRAYSCALE,
    )

    if image is None:

        raise RuntimeError(
            f"Could not read {image_path}"
        )

    height, width = image.shape

    # --------------------------------------------------------
    # Detect bright objects.
    # --------------------------------------------------------

    mask, objects = detect_objects(
        image
    )

    # --------------------------------------------------------
    # Determine left/right eye.
    # --------------------------------------------------------

    left_eye_raw, right_eye_raw = classify_eyes(
        objects,
        previous,
    )

    # --------------------------------------------------------
    # Serialize eye data.
    # --------------------------------------------------------

    left_eye = serialize_eye(
        left_eye_raw
    )

    right_eye = serialize_eye(
        right_eye_raw
    )

    # --------------------------------------------------------
    # Motion.
    # --------------------------------------------------------

    left_motion = calculate_motion(
        left_eye,
        None
        if previous is None
        else previous.get("left_eye"),
    )

    right_motion = calculate_motion(
        right_eye,
        None
        if previous is None
        else previous.get("right_eye"),
    )

    result = {
        "width": width,
        "height": height,

        "left_eye": left_eye,
        "right_eye": right_eye,

        "motion": {
            "left": left_motion,
            "right": right_motion,
        },
    }

    # --------------------------------------------------------
    # Debug visualization.
    # --------------------------------------------------------

    if debug:

        debug_image = cv2.cvtColor(
            image,
            cv2.COLOR_GRAY2BGR,
        )

        # Draw every detected object.

        for index, obj in enumerate(objects):

            x = obj["x"]
            y = obj["y"]

            w = obj["width"]
            h = obj["height"]

            cv2.rectangle(
                debug_image,
                (x, y),
                (x + w, y + h),
                (100, 100, 100),
                1,
            )

            cv2.putText(
                debug_image,
                str(index),
                (x, max(15, y - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (150, 150, 150),
                1,
                cv2.LINE_AA,
            )

        # ----------------------------------------------------
        # Draw LEFT eye.
        # ----------------------------------------------------

        if left_eye is not None:

            x = left_eye["x"]
            y = left_eye["y"]

            w = left_eye["width"]
            h = left_eye["height"]

            cv2.rectangle(
                debug_image,
                (x, y),
                (x + w, y + h),
                (0, 0, 255),
                2,
            )

            cv2.putText(
                debug_image,
                "LEFT",
                (x, max(20, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        # ----------------------------------------------------
        # Draw RIGHT eye.
        # ----------------------------------------------------

        if right_eye is not None:

            x = right_eye["x"]
            y = right_eye["y"]

            w = right_eye["width"]
            h = right_eye["height"]

            cv2.rectangle(
                debug_image,
                (x, y),
                (x + w, y + h),
                (0, 255, 0),
                2,
            )

            cv2.putText(
                debug_image,
                "RIGHT",
                (x, max(20, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

        DEBUG_DIRECTORY.mkdir(
            exist_ok=True
        )

        debug_path = (
            DEBUG_DIRECTORY /
            f"{image_path.stem}_debug.png"
        )

        mask_path = (
            DEBUG_DIRECTORY /
            f"{image_path.stem}_mask.png"
        )

        cv2.imwrite(
            str(debug_path),
            debug_image,
        )

        cv2.imwrite(
            str(mask_path),
            mask,
        )

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    image_paths = sorted(
        ASSETS_DIRECTORY.glob("*.png")
    )

    if not image_paths:

        print(
            f"No PNG files found in "
            f"{ASSETS_DIRECTORY}"
        )

        return

    CACHE_DIRECTORY.mkdir(
        exist_ok=True
    )

    print()
    print("Animation Analyzer")
    print("==================")
    print()

    print(
        f"Frames:   {len(image_paths)}"
    )

    print(
        f"FPS:      {FPS}"
    )

    print(
        f"Threshold: {THRESHOLD}"
    )

    print()

    frames = []

    previous = None

    for index, image_path in enumerate(
        image_paths
    ):

        print(
            f"[{index + 1:03d}/{len(image_paths):03d}] "
            f"{image_path.name}"
        )

        source_hash = calculate_file_hash(
            image_path
        )

        data = analyze_frame(
            image_path,
            previous,
        )

        # ----------------------------------------------------
        # Print detection result.
        # ----------------------------------------------------

        left = data["left_eye"]
        right = data["right_eye"]

        if left is None:

            print(
                "    LEFT : not visible"
            )

        else:

            print(
                "    LEFT : "
                f"x={left['x']} "
                f"y={left['y']} "
                f"size="
                f"{left['width']}x"
                f"{left['height']}"
            )

        if right is None:

            print(
                "    RIGHT: not visible"
            )

        else:

            print(
                "    RIGHT: "
                f"x={right['x']} "
                f"y={right['y']} "
                f"size="
                f"{right['width']}x"
                f"{right['height']}"
            )

        # ----------------------------------------------------
        # Frame timing.
        #
        # For now the analyzer uses one timeline tick
        # per source frame.
        #
        # Later we will load your exact hold values.
        # ----------------------------------------------------

        frame_data = {
            "index": index,

            "source": image_path.name,

            "source_hash": source_hash,

            "tick": index,

            "hold": 1,

            "data": data,
        }

        frames.append(
            frame_data
        )

        previous = data

        print()

    # --------------------------------------------------------
    # Animation duration.
    # --------------------------------------------------------

    total_ticks = sum(
        frame["hold"]
        for frame in frames
    )

    duration = (
        total_ticks / FPS
    )

    # --------------------------------------------------------
    # Final cache.
    # --------------------------------------------------------

    cache = {
        "version": 1,

        "fps": FPS,

        "frame_width": frames[0]["data"]["width"],
        "frame_height": frames[0]["data"]["height"],

        "frame_count": len(frames),

        "total_ticks": total_ticks,

        "duration": duration,

        "frames": frames,
    }

    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            cache,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(
        "========================================"
    )

    print(
        "Analysis complete."
    )

    print(
        f"Duration: {duration:.3f} sec"
    )

    print(
        f"Cache:    {CACHE_FILE}"
    )

    print(
        f"Debug:    {DEBUG_DIRECTORY}"
    )

    print()


if __name__ == "__main__":
    main()
