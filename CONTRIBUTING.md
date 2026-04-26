# Contributing to MouseSpot

First off, thank you for considering contributing to MouseSpot! Contributions are welcome to make the hand-mouse tracker even better.

## How Can I Contribute?

### Reporting Bugs
If you find a bug, please create an issue containing:
- A clear, descriptive title.
- A detailed description of the problem.
- Steps to reproduce the issue.
- Your OS, Python version, and camera model (if applicable).

### Suggesting Enhancements
Enhancements can range from small features to entirely new functionalities. If you are suggesting a new feature:
- Explain why this enhancement would be useful to most users.
- Provide examples of how it should work or look.

### Pull Requests
1. Fork the repository and create your branch from `main`.
2. Ensure you have installed the project with its development dependencies (e.g., using `uv`).
3. Make your changes and ensure your code adheres to our styles.
4. If you have added code that should be tested, add tests.
5. Make sure the test suite passes locally (`pytest tests/`).
6. Ensure docstrings are kept strictly to the **class** and **function** levels, omitting module-level docstrings unless strictly necessary.
7. Open a Pull Request referencing any related issues.

## Setup for Development
1. Clone your fork locally.
2. Ensure you have `uv` installed, then run: `uv sync`
3. Run the tests to confirm your environment is correctly set up:
   ```bash
   pytest tests/
   ```

Thank you for helping to improve MouseSpot!
