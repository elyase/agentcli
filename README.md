# agentcli

Python CLIs for agents and humans.

agentcli builds command-line interfaces that produce structured, parseable output for AI agents while remaining human-friendly. Type hints are the schema — a function signature IS the CLI specification.

## Install

```sh
pip install humancli
```

The package installs as `humancli` on PyPI and you import it as `humancli`:

```python
from humancli import App
```

## Quick start

### Single function

```python
from humancli import run

def greet(name: str):
    """Greet someone."""
    return {"message": f"hello {name}"}

run(greet)
```

```sh
$ greet world
message: hello world

$ greet world --json
{"ok": true, "data": {"message": "hello world"}}

$ greet --llms
# greet
| Command | Description |
|---------|-------------|
| `greet <name>` | Greet someone |
```

### Multi-command app

```python
from humancli import App

app = App("my-cli", version="1.0.0")

@app.command
def status():
    """Show status."""
    return {"clean": True, "branch": "main"}

@app.command
def install(package: str, *, save_dev: bool = False):
    """Install a package."""
    return {"added": 1, "packages": 451}

app()
```

Parameters before `*` are positional arguments. Parameters after `*` are named options/flags. This is just Python's own syntax.

### Parameter metadata

```python
from typing import Annotated, Literal
from humancli import App, Param

app = App("deploy-cli")

@app.command
def deploy(
    env: Annotated[Literal["staging", "prod"], Param(help="Target environment")],
    *,
    token: Annotated[str, Param(env="DEPLOY_TOKEN", secret=True)] = "",
):
    """Deploy to an environment."""
    return {"url": f"https://{env}.example.com"}

app()
```

### Sub-apps

```python
app = App("gh")
pr = App("pr")

@pr.command
def list_(*, state: Literal["open", "closed"] = "open"):
    """List pull requests."""
    return {"prs": [], "state": state}

app.mount(pr)
app()

# $ gh pr list --state closed
```

### Default commands

```python
app = App("fetch")

@app.default
def fetch_cases(*, limit: int = 20):
    """Fetch cases."""
    return {"fetched": limit}

# Runs when no sub-command is given:
# $ fetch --limit 5
```

## Agent discovery

Every humancli app gets built-in flags for agent consumption:

- `--llms` — markdown command index
- `--llms-full` — full JSON schema of all commands
- `--json` / `--yaml` / `--jsonl` — structured output formats
- `--mcp` — start as an MCP server (requires `humancli[mcp]`)

## Optional extras

```sh
pip install humancli[rich]      # rich terminal formatting
pip install humancli[pydantic]  # pydantic model support
pip install humancli[yaml]      # yaml output format
pip install humancli[mcp]       # MCP server mode
pip install humancli[all]       # everything
```

## License

MIT
