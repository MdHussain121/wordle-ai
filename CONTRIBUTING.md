# Contributing to Wordle AI

Thank you for your interest in contributing to Wordle AI! We welcome contributions from developers, researchers, and puzzle enthusiasts.

## Development Setup

### Prerequisites
- Python 3.12 or newer
- Node.js 20+ and npm (for the web interface)
- Git

### Cloning and Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/wordle-ai/wordle-ai.git
   cd wordle
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows PowerShell
   .venv\Scripts\Activate.ps1
   # Linux / macOS
   source .venv/bin/activate
   ```

3. Install editable dependencies including development and research extras:
   ```bash
   pip install -e ".[dev,http,prior,ml]"
   ```

### Web Studio Development (Optional)

If you are working on the graphical studio interface:
```bash
cd web
npm install
npm run dev
```

## Testing & Code Quality

Before opening a pull request, ensure tests pass and code conforms to project standards:

- **Unit tests**:
  ```bash
  pytest tests/unit
  ```
- **Code formatting and linting**:
  ```bash
  ruff check .
  ruff format --check .
  ```

## Critical Data Policy: Word Lists

Wordle target wordlists and proprietary puzzle solutions **must never be committed or redistributed directly in git commits**.

- Lexicons and evaluation wordlists are compiled locally from approved open source corpora via `wordle-ai lex fetch`.
- Classic Wordle solution lists must remain user-supplied locally and are protected by `.gitignore`.
- Any pull request containing proprietary or copyrighted wordlists will be closed.

## Pull Request Guidelines

1. Create a feature branch off `master` (e.g., `git checkout -b feature/my-enhancement`).
2. Keep pull requests focused on a single logical change.
3. Include tests covering new functionality or bug fixes.
4. Verify that documentation reflects code modifications.
