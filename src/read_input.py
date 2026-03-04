import threading

import keyboard
import mouse


def read_user_input() -> str:
    """Block until the user presses a keyboard key or a mouse button.
    Returns the key name (e.g. 'space', 'a') or 'left' / 'right'.
    """
    result: list[str] = []
    done = threading.Event()

    def on_key(event: keyboard.KeyboardEvent):
        if not done.is_set() and event.name != "unknown":
            result.append(event.name)
            done.set()

    def on_mouse_click(event):
        if isinstance(event, mouse.ButtonEvent) and event.event_type == mouse.DOWN:
            if not done.is_set():
                result.append(event.button)  # 'left' or 'right'
                done.set()

    keyboard.hook(on_key)
    mouse.hook(on_mouse_click)
    done.wait()
    keyboard.unhook(on_key)
    mouse.unhook(on_mouse_click)

    return result[0]
