"""`wordle-ai web`: launch the interactive Web GUI Studio & Copilot."""

from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Optional
import webbrowser

import typer

from ...config import DEFAULT_CONFIG_PATH, load_config
from ...engine.table import open_rows
from ...errors import WordleError
from ...lexicon.profile import TABLE_NAME, load_profile
from ...solver.policy import load_policy
from ..output import fail

app = typer.Typer(no_args_is_help=False, help="Launch the interactive Wordle AI Web GUI.")


@app.command("web")
def web(
    profile: str = typer.Option("classic.en.5", "--profile", help="Profile id to load."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host interface to bind to."),
    port: int = typer.Option(8000, "--port", help="Port to listen on."),
    open_browser: bool = typer.Option(
        True, "--browser/--no-browser", help="Open web browser on startup."
    ),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to TOML config."),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", help="Override data directory."),
    policy_path: Optional[Path] = typer.Option(
        None, "--policy", help="Path to verified exact DP policy artifact."
    ),
) -> None:
    """Launch the interactive Wordle AI Web GUI Studio & Copilot in your browser."""

    try:
        import uvicorn
        from ...api.http import create_app
        from ...api.service import SolverService
    except ImportError as exc:
        fail(
            WordleError(
                f"Web GUI dependencies missing: {exc}. Install with `pip install 'wordle-ai[http]'`",
                code="missing_dependency",
            )
        )
        return

    settings = load_config(config)
    root = Path(data_dir) if data_dir is not None else Path(settings.general.data_dir)
    profile_dir = root / "processed" / profile
    if not profile_dir.exists():
        if profile == "classic.en.5" and (root / "processed" / "strict.en.5").exists():
            profile = "strict.en.5"
            profile_dir = root / "processed" / profile
        else:
            fail(
                WordleError(
                    f"Profile directory not found: {profile_dir}. "
                    "Run `wordle-ai lex fetch --source scowl && wordle-ai lex fetch --source enable && wordle-ai lex build --profile strict.en.5` first.",
                    code="missing_profile",
                )
            )
            return

    loaded_profile = load_profile(profile_dir)
    table_path = profile_dir / TABLE_NAME
    rows = open_rows(loaded_profile, table_path if table_path.exists() else None)

    # Resolve policy if available
    policy_payload = None
    target_policy = policy_path or Path("policies") / f"{profile}.normal.uniform.policy.json"
    if target_policy.exists():
        try:
            policy_payload = load_policy(target_policy, profile=loaded_profile, verify=False)
        except Exception as exc:
            typer.echo(f"Notice: Policy artifact at {target_policy} could not be loaded: {exc}")

    default_strategy = "exact" if policy_payload is not None else "hybrid.balanced"
    service = SolverService(
        loaded_profile,
        rows=rows,
        strategy=default_strategy,
        policy=policy_payload,
    )
    service.policy = policy_payload

    web_app = create_app(service, policy=policy_payload)

    url = f"http://{host}:{port}"
    typer.echo("=================================================================")
    typer.echo(f"  Wordle AI Web Studio & Copilot: {url}")
    typer.echo(f"  Active Profile: {profile} ({len(loaded_profile.answers):,} answers)")
    typer.echo(f"  Default Engine: {default_strategy}")
    typer.echo(f"  Policy Loaded:  {'Yes (Exact DP)' if policy_payload is not None else 'No'}")
    typer.echo("  Press Ctrl+C to stop the server.")
    typer.echo("=================================================================")

    if open_browser:
        def _launch():
            time.sleep(0.6)
            webbrowser.open(url)

        threading.Thread(target=_launch, daemon=True).start()

    uvicorn.run(web_app, host=host, port=port, log_level="info")
