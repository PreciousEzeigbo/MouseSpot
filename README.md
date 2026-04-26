# MouseSpot 🖱️✨

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey.svg)]()
[![CI Status](https://github.com/preciousezeigbo/MouseSpot/actions/workflows/ci.yml/badge.svg)](https://github.com/preciousezeigbo/MouseSpot/actions)

**Control your PC with hand gestures via webcam.** 

MouseSpot acts as a low-latency, strictly offline hand-tracking mouse overlay. Native Wayland/X11 bindings allow seamless, system-level cursor control without being constrained to a single application window.

<!-- add demo.gif here -->
> *Placeholder: Hero GIF demonstrating the system*

---

## 🏗 Architecture

```mermaid
flowchart TD
    A[Webcam] -->|Frames| B[MediaPipe Tracker]
    B -->|Coordinates| C[Coordinate Smoother]
    B -->|Hand Shape| D[Gesture Classifier]
    D -->|Gesture Enum| E[Mouse Controller]
    C -->|Smoothed (X, Y)| E
    E -->|Wayland/X11 API| F[OS GUI Layer]
    B -->|Annotated Frame| G[OpenCV Overlay Window]
```

## 🚀 Quick Install

We exclusively use [uv](https://github.com/astral-sh/uv) for lightning fast Python environment management.

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/MouseSpot.git
cd MouseSpot

# 2. Install dependencies silently
uv sync

# 3. Launch the application
uv run mousespot
```

## 🖐️ Gesture Reference

The tracker algorithms map your gestures to instant OS mouse actions:

| Gesture | Hand Shape | Action |
| --- | --- | --- |
| **FREEZE** | Tight Fist | Pause cursor movement and tracking. |
| **POINTER** | Only Index Finger Extended | Moves the mouse cursor. |
| **LEFT CLICK** | Index tip touching Thumb tip | Emits a single Left-Click. |
| **DOUBLE CLICK** | Double Index-Thumb Pinch | Emits a Double Left-Click. |
| **RIGHT CLICK** | Middle tip touching Thumb tip | Emits a single Right-Click. |
| **SCROLL MODE** | Index & Middle Fingers Extended (Peace) | Moving your hand up or down scrolls via wheel ticks. |


## 🛠 Troubleshooting

### "mediapipe is not installed correctly"
You might encounter importing exceptions depending on the underlying OS headers.
Ensure you have successfully synced virtual environment using `uv sync`. Open CV requires some graphical libraries so if you are running headless or minimal ubuntu, you might need:
```bash
sudo apt-get update
sudo apt-get install libgl1 -y
```

### Permission Errors during Cursor Control
Since MouseSpot issues *native* system-wide clicks, Wayland specifically enforces security domains.

**If you are running Wayland (`$XDG_SESSION_TYPE=wayland`), ensure you have write permissions to `uinput`:**
1. Check if the backend auto-resolves successfully inside `uv run mousespot`.
2. Ensure you are in the `input` group: 
   ```bash
   sudo usermod -aG input $USER
   # You must log out and log back in for groups to refresh!
   ```

## 🤝 Contributing

Pull requests are actively welcomed! Please note that all code must pass rigorous type-checking and linting workflows.

```bash
uv run ruff check src/ tests/
uv run mypy src/ tests/
uv run pytest tests/
```

Before submitting large features, please open an Issue to track discussions!

## 📜 License

Distributed beneath the MIT License. See `LICENSE` for more information.
