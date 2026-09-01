from engine import (
    Animation,
    AnimationController,
    FramebufferDisplay,
)


# ============================================================
# IDLE
# ============================================================

idle = Animation(
    name="idle",

    frames=[
        ("001.png", 1),
        ("002.png", 1),
        ("003.png", 3),
        ("004.png", 1),
        ("005.png", 1),
        ("006.png", 1),
        ("007.png", 1),
        ("008.png", 1),
        ("009.png", 1),
        ("010.png", 1),
        ("011.png", 2),
        ("012.png", 1),
    ],

    loop=True,
)


# ============================================================
# Future animations
# ============================================================

# Поки не використовуємо їх.
#
# Коли ти намалюєш thinking:
#
# thinking = Animation(
#     name="thinking",
#     frames=[
#         ("001.png", 6),
#         ("002.png", 3),
#         ("003.png", 4),
#     ],
#     loop=True,
# )


# ============================================================
# MAIN
# ============================================================

def main():

    display = FramebufferDisplay(
        "/dev/fb0"
    )

    controller = AnimationController(
        display=display,
        assets_directory="assets",
    )

    # --------------------------------------------------------
    # Register animations
    # --------------------------------------------------------

    controller.add_animation(
        idle
    )

    # --------------------------------------------------------
    # Start animation engine
    # --------------------------------------------------------

    controller.start()

    # --------------------------------------------------------
    # Initial state
    # --------------------------------------------------------

    controller.set_state(
        "idle"
    )

    print()
    print("Animation engine running.")
    print()
    print("Current state:")
    print("    idle")
    print()
    print("Press Ctrl+C to stop.")
    print()

    try:

        while True:

            # The real AI agent will eventually control
            # the AnimationController from here.

            # For now we simply keep the main program alive.
            controller._stop.wait(1.0)

    except KeyboardInterrupt:

        print()
        print("Stopping...")

    finally:

        controller.stop()
        display.close()


if __name__ == "__main__":
    main()
