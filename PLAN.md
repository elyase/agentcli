# agentcli: Python CLIs for agents and humans

> The only Python CLI framework designed for the agent-first era.

## Identity

- **Package name**: `agentcli` (PyPI) / `import agentcli`
- **Tagline**: "Python CLIs for agents and humans."
- **Positioning**: Not "better Typer" — **the CLI framework for the agent era**. Click/Typer/cyclopts produce human-readable output agents have to scrape. agentcli produces structured, token-efficient output agents consume natively, with built-in discovery so agents find your CLI without configuration.
- **Python version**: `>=3.11`

---

## Core Philosophy

1. **Agent-first, human-native**: Every command produces structured, parseable output agents consume efficiently. Humans get the same data, rendered beautifully. The "right thing for agents" is the default.
2. **Type-hints are the schema**: Python's `Annotated[T, ...]`, `*` separator, docstrings, and optionally Pydantic/dataclasses replace Zod. A function signature IS the CLI specification.
3. **Token-efficient by default**: TOON format for agent consumers, rich formatting for humans. Agent discovery uses compact skill files. Every design decision considers token cost.
4. **Minimal API surface**: `App`, `@app.command`, `app()` — that's the entire core. Everything else (parsing, help, validation, formatting, agent discovery, MCP) is automatic.
5. **Pythonic, not a port**: Decorators, `async`/`await`, PEP 593 `Annotated`, `*` separator, docstrings — the library feels native to Python.
6. **Composable primitives**: Commands, parameters, middleware, and prompts are all composable — small pieces that combine into complex CLIs. Inspired by Effect CLI's functional composition.

---

## API Design

### Level 0: Single function, zero config

```python
from agentcli import run

def greet(name: str):
    """Greet someone."""
    return {"message": f"hello {name}"}

run(greet)
```

```sh
$ greet world
message: hello world

$ greet world --format json
{"ok": true, "data": {"message": "hello world"}}

$ greet --help
greet — Greet someone.

Usage: greet <name>

$ greet --llms
# greet
| Command | Description |
|---------|-------------|
| `greet <name>` | Greet someone |
```

**`run()` signature:**

```python
def run(
    func: Callable,
    *,
    name: str | None = None,     # CLI name (defaults to func.__name__)
    version: str | None = None,  # --version output
    argv: list[str] | None = None,  # Override sys.argv (for testing)
) -> None:
    """Run a single function as a CLI. Creates an ephemeral App internally."""
```

Users graduate to `App()` when they need multi-command, middleware, or configuration.

### Level 1: Multi-command app

```python
from agentcli import App

app = App("my-cli", version="1.0.0", description="My tool")

@app.command
def status():
    """Show repo status."""
    return {"clean": True, "branch": "main"}

@app.command
def install(package: str, *, save_dev: bool = False):
    """Install a package.

    Parameters
    ----------
    package
        Package name to install.
    save_dev
        Save as dev dependency.
    """
    return {"added": 1, "packages": 451}

app()
```

**Convention**: Parameters before `*` are positional CLI arguments. Parameters after `*` (keyword-only) are named CLI options/flags. This uses Python's own syntax — no framework abstraction needed.

**`@app.command` supports both forms** via overloads:
```python
@app.command                           # no parens — uses function name
@app.command(name="alt", output=Model) # with parens — custom config
```

**Return value behavior:**
- `return dict/dataclass/model` → wrapped in success envelope, formatted, printed
- `return Result(data, cta=[...])` → success envelope with CTAs
- `return None` → success envelope with `data: null`, no output printed (silent success)
- `raise AgentCliError(...)` → error envelope

### Level 2: Annotated metadata

```python
from typing import Annotated, Literal
from agentcli import App, Param

app = App("deploy-cli")

@app.command
def deploy(
    env: Annotated[Literal["staging", "production"], Param(help="Target environment")],
    *,
    force: Annotated[bool, Param(alias="f", help="Skip confirmation")] = False,
    replicas: Annotated[int, Param(alias="r", help="Number of replicas")] = 3,
    token: Annotated[str, Param(env="DEPLOY_TOKEN", help="Auth token")] = "",
):
    """Deploy to an environment."""
    return {"url": f"https://{env}.example.com", "replicas": replicas}

app()
```

`Param` is the single metadata class. The `*` separator already determines arg vs option — `Param` adds only extra metadata (aliases, env vars, deprecation, help text override).

### Level 3: Output schemas and CTAs

```python
from dataclasses import dataclass
from agentcli import App, Result, AgentCliError

app = App("my-cli")

@dataclass
class DeployResult:
    url: str
    duration: float

@app.command(output=DeployResult)
def deploy(env: str, *, force: bool = False):
    """Deploy to an environment."""
    if not force and env == "production":
        raise AgentCliError(
            code="CONFIRM_REQUIRED",
            message="Use --force for production deploys",
            retryable=True,
            cta=["deploy staging", "deploy production --force"],
        )
    return Result(
        data=DeployResult(url=f"https://{env}.example.com", duration=3.2),
        cta=["status", "logs --follow"],
    )
```

**Key decision**: Plain `return data` for simple cases. `return Result(data, cta=[...])` when you need CTAs. `raise AgentCliError(...)` for errors. No `ctx.ok()`/`ctx.error()` — use Python's native return/raise semantics.

### Level 4: Command groups

```python
from agentcli import App

app = App("gh", description="GitHub CLI")
pr = App("pr", description="Pull request commands")

@pr.command
def list_(*, state: Literal["open", "closed", "all"] = "open"):
    """List pull requests."""
    return {"prs": [], "state": state}

@pr.command
def view(number: int):
    """View a pull request."""
    return {"number": number, "title": "Fix bug"}

app.mount(pr)
app()

# $ gh pr list --state closed
# $ gh pr view 42
```

### Level 5: Middleware

```python
@app.use
async def timing(ctx, next):
    """Measure command execution time."""
    start = time.monotonic()
    await next()
    elapsed = time.monotonic() - start
    ctx.meta["duration"] = f"{elapsed*1000:.0f}ms"

@app.use
async def auth(ctx, next):
    """Require authentication."""
    user = authenticate()
    if not user:
        raise AgentCliError(code="AUTH", message="Not logged in", retryable=True)
    ctx.state["user"] = user
    await next()
```

Middleware is onion-style (registration order in, reverse order out). `ctx.state` is a simple dict — no typed vars in v1. Middleware does NOT run for built-in flags (`--help`, `--llms`, `--mcp`, `--wizard`).

### Level 6: Streaming

```python
@app.command
async def logs(*, follow: bool = False):
    """Tail application logs."""
    async for line in stream_logs():
        yield {"line": line, "ts": line.timestamp}
```

Async generators stream output. Each yielded value is formatted immediately. In JSONL mode, each becomes a separate JSON line.

### Level 7: Optional context injection

```python
@app.command
def whoami(ctx: agentcli.Context):
    """Show current user."""
    if ctx.agent:
        return {"user": ctx.state.get("user"), "format": "structured"}
    return {"user": ctx.state.get("user")}
```

Context is opt-in via type annotation. Provides: `ctx.agent` (bool), `ctx.state` (dict from middleware), `ctx.meta` (envelope metadata). Most commands don't need it.

### Level 8: Wizard mode

```python
@app.command
def deploy(
    env: Annotated[Literal["staging", "production"], Param(help="Target environment")],
    *,
    force: Annotated[bool, Param(alias="f", help="Skip confirmation")] = False,
    replicas: Annotated[int, Param(alias="r", help="Number of replicas")] = 3,
):
    """Deploy to an environment."""
    return {"url": f"https://{env}.example.com"}

# $ my-cli deploy --wizard
# ? Target environment: [staging/production] › staging
# ? Skip confirmation? [y/N] › N
# ? Number of replicas: [3] › 5
# Running: my-cli deploy staging --replicas 5
# (middleware runs normally when the constructed command executes)
```

Every command automatically supports `--wizard`. The framework generates interactive prompts from the parameter definitions — types, descriptions, defaults, choices all drive the wizard UI. Zero extra code from the developer.

**Wizard + `Param(prompt="...")`**: When `--wizard` is active, `Param(prompt="...")` overrides the auto-generated prompt message for that parameter. `Param(secret=True)` carries through to wizard (masking input).

**Wizard + nested config**: Nested config parameters are prompted as individual fields with a section header (e.g., "Database Configuration:") for grouping.

**Agent behavior**: When `--wizard` is used in non-TTY mode, it outputs the JSON schema of the command's parameters (derived statically from the function signature, not runtime state) — enabling agents to construct the correct command.

### Level 9: Fallback prompts

```python
@app.command
def login(
    *,
    username: Annotated[str, Param(prompt="Username")] = "",
    password: Annotated[str, Param(prompt="Password", secret=True)] = "",
):
    """Log in to the service."""
    return {"user": username, "token": "..."}

# $ my-cli login
# ? Username: alice
# ? Password: ****
# user: alice
# token: ...

# $ my-cli login --username alice --password secret123
# (no prompts — flags override)
```

When a parameter has `prompt=` set and the user doesn't provide the flag, agentcli prompts interactively. If running non-interactively (non-TTY / agent mode), missing prompted params raise a clear error with the parameter name and expected type.

---

## Parameter Value Resolution

The full priority chain for resolving a parameter's value:

```
CLI flag (highest)  →  Environment variable  →  Interactive prompt (TTY only)  →  Config file (v1.1)  →  Default (lowest)
```

- `Param(env="PORT")` is resolved at parse time, before middleware runs
- `Param(prompt="...")` fires only in TTY mode and only when no flag/env value is found
- In non-TTY mode, if no flag/env/default is available, a `ParseError` is raised with the parameter name
- Config file support (v1.1) slots in between prompt and default

---

## Schema System

### Two tiers (not three)

**Tier 1: Plain type hints + docstrings** (the simple path)
```python
def deploy(env: str, *, force: bool = False):
    """Deploy to an environment.

    Parameters
    ----------
    env
        Target environment (staging or production).
    force
        Skip confirmation prompt.
    """
```

**Tier 2: Annotated + Param** (when you need metadata)
```python
def deploy(
    env: Annotated[Literal["staging", "production"], Param(help="Target")],
    *,
    force: Annotated[bool, Param(alias="f")] = False,
):
```

### Nested config objects (inspired by Effect CLI)

Dataclass and Pydantic parameters expand into dot-notation CLI flags, then reconstruct the object for the handler:

```python
@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    name: str = "mydb"

@dataclass
class AppConfig:
    db: DatabaseConfig
    debug: bool = False

@app.command
def serve(*, config: AppConfig):
    """Start the server."""
    return {"host": config.db.host, "port": config.db.port}

# $ my-cli serve --config.db.host 10.0.0.1 --config.db.port 3306 --config.debug
```

**Nested type expansion rules:**

1. When a parameter's type is a dataclass or Pydantic model, ALL its fields become `--prefix.field` keyword options — regardless of whether the parameter is positional or keyword-only in the function signature
2. A `ConfigError` is raised at registration time if a positional parameter has a structured type with required fields that have no defaults (ambiguous)
3. Maximum nesting depth: 4 levels (configurable via `App(max_nesting_depth=N)`). `ConfigError` if exceeded
4. Circular references are detected and raise `ConfigError` at registration time
5. The positional/keyword distinction of the nested type's own `__init__` is irrelevant — only the top-level function signature's `*` separator matters
6. `Param(file=True)` on a structured type parameter prevents field expansion (the file path is read and parsed instead)

### Schema extraction pipeline

```
Function signature
  → inspect.signature()
  → separate positional (before *) from keyword-only (after *)
  → for each parameter:
      - Extract type hint (resolve Annotated, Union, Literal, Optional)
      - Extract Param() metadata from Annotated if present
      - Extract description from docstring (numpy/google/sphinx formats)
      - If type is dataclass/Pydantic: expand fields recursively into options
  → CommandSchema(args, options, output)
```

### Description priority

1. Explicit `Param(help="...")` — highest priority
2. Pydantic `Field(description="...")` — for model fields
3. Docstring parameter section — lowest priority, auto-extracted

---

## Help System (internal AST)

Inspired by Effect CLI, help documentation is modeled internally as a data structure, not strings. The AST is an **internal implementation detail** — not part of the public API.

```python
# Internal types in _help.py
HelpNode = Empty | Header | Paragraph | DescriptionList | Enumeration | Sequence

class HelpRenderer(Protocol):
    def render(self, node: HelpNode) -> str: ...
```

**Construction algorithm**: A command produces `Sequence(Header(name), Paragraph(description), DescriptionList(args), DescriptionList(options))`. Inline text uses `Span` sub-types (`Text`, `Code`, `Strong`, `Weak`) for formatting.

### Renderers

| Renderer | Used by | Output |
|----------|---------|--------|
| `AnsiRenderer` | `--help` (TTY) | Colored terminal output (when rich installed) |
| `PlainRenderer` | `--help` (non-TTY) | Plain text, no escape codes |
| `MarkdownRenderer` | `--llms`, `--llms-full` | Markdown tables and headers |
| `JsonRenderer` | `--help --format json` | JSON Schema-like structure |

This means `--help` and `--llms` share the same data — just different renderers. Adding new output formats is trivial.

For users who need to customize help, `App` exposes `help_header: str | None` and `help_footer: str | None` — no AST manipulation needed.

---

## Output System

### Envelope format

Every command produces a structured envelope:

```python
@dataclass
class Envelope:
    ok: bool
    data: Any | None = None
    error: ErrorInfo | None = None
    meta: Meta | None = None

@dataclass
class Meta:
    command: str
    duration: str | None = None
    cta: list[str | CtaEntry] | None = None

@dataclass
class ErrorInfo:
    code: str
    message: str
    retryable: bool = False

@dataclass
class CtaEntry:
    command: str
    description: str | None = None
```

### Output formats

| Format | Flag | Description |
|--------|------|-------------|
| **TOON** | `--format toon` | Token-efficient, default for non-TTY (agent) |
| **Pretty** | (default TTY) | Human-readable with color, tables, panels |
| **JSON** | `--json` / `--format json` | Standard JSON envelope |
| **YAML** | `--format yaml` | YAML (requires `agentcli[yaml]`) |
| **Markdown** | `--format md` | Tables for arrays, key-value for dicts |
| **JSONL** | `--format jsonl` | One JSON object per line (streaming) |

### Output behavior by mode

| Aspect | Human (TTY) | Agent (non-TTY) |
|--------|-------------|-----------------|
| Default format | Pretty (rich) | TOON |
| Success envelope | Data only (use `--verbose` for full) | Data only (use `--verbose` for full) |
| Error envelope | Always full: `ok: false` + `error` object | Always full: `ok: false` + `error` object |
| CTAs | `Next:` block after data | Merged into output |
| Progress | Rich spinners/bars | Suppressed |
| Wizard/prompts | Interactive prompts | JSON schema output / error if missing |

Note: Errors always produce the full structured envelope regardless of `--verbose`, because agents need the `code`, `retryable`, and `cta` fields to self-correct.

### TOON format (built-in encoder, ~300 lines)

Token-Optimized Object Notation. 40-60% fewer tokens than JSON.

**Encoding rules:**

| Type | Encoding | Example |
|------|----------|---------|
| `str` | Bare value, no quotes | `name: Alice` |
| `int`/`float` | Bare numeric | `age: 30`, `score: 3.14` |
| `bool` | Lowercase `true`/`false` | `active: true` |
| `None`/`null` | Omitted entirely (key not emitted) | (field skipped) |
| `str` with `,` or `:` | Quoted with double quotes | `desc: "red, blue"` |
| `str` with newlines | Quoted with `\n` escape | `bio: "line1\nline2"` |
| Nested dict | Indented key-value block | See below |
| Array of scalars | Inline: `key[N]: a,b,c` | `tags[3]: py,cli,agent` |
| Array of objects | Columnar: header + CSV rows | See below |
| Mixed array | One item per indented line | `items:\n  - val1\n  - val2` |
| Empty dict/list | `key: (empty)` | `results: (empty)` |

**Serialization protocol for non-primitive types:**

Objects are serialized to dicts via this fallback chain:
1. `.to_dict()` method if defined (custom protocol)
2. `dataclasses.asdict()` for dataclasses
3. `.model_dump()` for Pydantic models
4. `str()` for everything else (`datetime`, `UUID`, `Path`, `Decimal`, `Enum`, etc.)

```
# Scalars
name: Alice
age: 30
active: true

# Nested dict
config:
  host: localhost
  port: 8080

# Array of objects (columnar — compact tabular format)
users[3]{id,name,role}:
  1,Alice,admin
  2,Bob,user
  3,Carol,editor

# Array of scalars (inline)
tags[3]: python,cli,agent
```

The encoder is pure Python, bundled in `_toon.py`. Reference implementation: `@toon-format/toon` npm package.

---

## Agent Discovery

### `--llms` flag (v1)

Compact markdown index of all commands:

```
$ my-cli --llms
# my-cli v1.0.0

My CLI tool

| Command | Description |
|---------|-------------|
| `my-cli install <package>` | Install a package |
| `my-cli status` | Show repo status |
| `my-cli deploy <env>` | Deploy to an environment |

Run `my-cli <command> --help` for details.
Run `my-cli --llms-full` for full manifest.
```

### `--llms-full` flag (v1)

Full manifest with arguments, options, examples for each command (skill file format).

### `--mcp` flag (v1)

Starts the CLI as an MCP stdio server using the `mcp` Python SDK (Anthropic's official SDK). Each command becomes an MCP tool.

```sh
$ my-cli --mcp
# Starts MCP stdio server
```

**MCP bridge details:**

1. Walk the command tree, flatten groups with underscores: `pr list` → tool `pr_list`
2. For each command, merge positional args and keyword options into a single flat JSON Schema `inputSchema` (using the same `CommandSchema` that drives `--llms`)
3. Register each as an MCP tool via `@server.tool(name, description, schema)`
4. On tool call: split the flat params back into args/options, validate, and call the command handler
5. Return the envelope data as `TextContent` in JSON format
6. Streaming commands: yield values as MCP progress notifications; final result is the tool response
7. Errors: `AgentCliError` maps to MCP error responses with the structured error info

Requires optional dep: `pip install agentcli[mcp]`. Without it, `--mcp` prints install instructions.

### `skills add` command (v1.1)

```sh
$ my-cli skills add
✓ Synced 3 skills to ~/.agents/skills/my-cli/
```

### `mcp add` command (v1.1)

```sh
$ my-cli mcp add
✓ Registered my-cli as MCP server for Claude Code, Cursor
```

---

## Wizard Mode (inspired by Effect CLI)

Every agentcli command automatically supports `--wizard`. This is a first-class feature, not an afterthought.

### How it works

1. The framework reads the command's parameter definitions (types, descriptions, defaults, choices)
2. For each parameter, it generates an appropriate interactive prompt:
   - `str` → text input
   - `int`/`float` → numeric input with validation
   - `bool` → yes/no confirmation
   - `Literal["a", "b", "c"]` → select menu
   - `Enum` → select menu from enum members
   - `list[T]` → multi-select or repeated input
   - `Path` → text input (v1.1: file browser when rich installed)
3. Pre-filled defaults are shown and can be accepted with Enter
4. After all prompts, the constructed command is shown for confirmation
5. The command executes (middleware runs normally at this point)

### Prompt composability

Prompts are **synchronous** (blocking on stdin), matching Python CLI conventions:

```python
from agentcli.prompt import text, select, confirm, password

name = text("What's your name?")
env = select("Environment:", ["staging", "production"])
ok = confirm("Deploy now?", default=True)
secret = password("API key:")
```

These work in both sync and async command handlers. The framework handles the sync→async bridge internally when needed.

### Agent behavior

When `--wizard` is used in non-TTY mode, it outputs the JSON schema of the command's parameters (derived statically from the function signature, not runtime state) — enabling agents to construct the correct command. Respects `--format`: `--wizard --format json` outputs JSON Schema.

---

## Parser Specification

The parser is a custom argv parser (not argparse). It takes a `CommandSchema` (derived from function signatures) and maps argv tokens to function parameters.

### Parsing rules

| Pattern | Behavior | Example |
|---------|----------|---------|
| `--flag value` | Named option with space-separated value | `--port 8080` |
| `--flag=value` | Named option with `=` separator | `--port=8080` |
| `-f value` | Short alias with space-separated value | `-p 8080` |
| `-f=value` | Short alias with `=` separator | `-p=8080` |
| `-abc` | Stacked boolean short flags | `-vf` → `--verbose --force` |
| `--flag` | Boolean true (for bool-typed options) | `--force` → `force=True` |
| `--no-flag` | Boolean false (negate `--flag`) | `--no-force` → `force=False` |
| `--` | End of flags; remaining tokens are positional | `-- --literally-a-file` |
| `value` | Positional argument (matched in schema order) | `deploy staging` |

### Type coercion

Argv tokens are strings. The parser coerces to the target type from the schema:

- `str` → no coercion
- `int` → `int(value)`, supports hex (`0x`), octal (`0o`), binary (`0b`)
- `float` → `float(value)`
- `bool` → flags are `True`/`False` by presence; explicit values: `true/yes/1` → `True`, `false/no/0` → `False`
- `Literal["a", "b"]` → validate value is in literal set
- `list[T]` → repeated flags accumulate: `--tag foo --tag bar` → `["foo", "bar"]`
- `Enum` → case-insensitive name match
- Union types → left-to-right coercion attempt (try first type, fall back to next)

### Unknown flags

Unknown flags raise `ParseError` with "Did you mean?" suggestions (Levenshtein distance, max 3 suggestions, sorted by distance). No pass-through mode in v1.

### Name transformation

Python `snake_case` parameter names map to `--kebab-case` CLI flags:
- `save_dev` → `--save-dev`
- `no_cache` → `--no-cache` (but also supports `--cache` with boolean negation)

---

## Async Execution Model

`app()` is always synchronous from the caller's perspective. Internally:

1. `app()` parses argv and resolves the command
2. If any middleware or the resolved command is async (`inspect.iscoroutinefunction`), wrap execution in `asyncio.run()`
3. If all middleware and the command are sync, execute directly (no event loop overhead)
4. Async generators (`inspect.isasyncgenfunction`) are consumed inside the event loop

**Sync commands with async middleware**: The sync command is wrapped via `asyncio.to_thread(fn)` to run in the default thread pool. This means sync commands in an async middleware chain run in a separate thread — document this for users who rely on thread-local state.

**Streaming with envelopes**: When a command yields via async generator:
- Each yielded value is formatted and flushed immediately
- On completion, a final envelope with `ok: true` and `meta` (including CTAs) is emitted
- On exception mid-stream, a final envelope with `ok: false` and the error is emitted
- In MCP mode, yielded values become progress notifications; the final result is the tool response

---

## Mount Semantics

`app.mount(sub_app)` attaches a sub-`App` as a command group:

- The sub-app's `name` becomes the command prefix: `app.mount(pr)` → `my-cli pr <command>`
- Parent middleware wraps sub-app commands (parent runs first, then sub-app middleware)
- Help text shows the group: `my-cli pr --help` shows all `pr` subcommands
- `--llms` includes mounted groups with full paths
- MCP flattens with underscores: `pr_list`, `pr_view`
- Optional `name` override: `app.mount(pr, name="pull-request")` → `my-cli pull-request <cmd>`

### Parent command access from subcommands (inspired by Effect CLI)

Subcommand handlers can access the parent app's parsed config and state via context injection:

```python
app = App("git", description="Git CLI")
pr = App("pr", description="Pull request commands")

@app.command
def default(*, verbose: bool = False):
    """Default git behavior."""
    pass

@pr.command
def list_(ctx: agentcli.Context):
    """List pull requests."""
    parent_state = ctx.parent_state  # Access parent middleware state
    return {"prs": [], "verbose": parent_state.get("verbose")}

app.mount(pr)
```

`ctx.parent_state` provides read-only access to the parent command group's middleware state. This enables shared configuration (e.g., `--verbose` on the root app) to flow down to subcommands without repeating flags.

---

## Error Handling

### Exception hierarchy

```python
class AgentCliError(Exception):
    """Base error for structured CLI errors."""
    code: str
    message: str
    retryable: bool = False
    cta: list[str] | None = None
    exit_code: int = 1

class ValidationError(AgentCliError):
    """Schema validation failure."""
    field_errors: list[FieldError]

class ParseError(AgentCliError):
    """Argument parsing failure."""
    # Unknown flag, missing arg, etc.

class ConfigError(AgentCliError):
    """Framework configuration error (for CLI authors)."""
    # Raised at registration time, not runtime
```

### Error output

**Human (TTY)**:
```
Error: Invalid value "banana" for env
  Expected one of: staging, production

  Try:
    my-cli deploy staging    Deploy to staging
    my-cli deploy --help     Show full usage
```

**Agent (non-TTY)**:
```
ok: false
error:
  code: VALIDATION
  message: Invalid value "banana" for env. Expected one of: staging, production
  retryable: true
cta:
  - deploy staging
  - deploy --help
```

### Auto-correction (inspired by Effect CLI)

When a flag or command is misspelled, agentcli suggests corrections using Levenshtein distance:

```
$ my-cli deplo staging
Error: Unknown command "deplo"
  Did you mean: deploy?

$ my-cli deploy staging --forse
Error: Unknown option "--forse"
  Did you mean: --force?
```

The auto-correction distance threshold is configurable: `App("my-cli", autocorrect_threshold=2)`. Max 3 suggestions shown, sorted by distance. Case-insensitive matching by default.

### Uncaught exceptions

`app()` catches all exceptions. `AgentCliError` subclasses are formatted as structured errors. Uncaught `Exception` becomes `{"code": "UNKNOWN", "message": str(e), "retryable": false}` with exit code 1. In `--verbose` mode, the traceback is included.

---

## Config Layering (inspired by Effect CLI)

Parameters cascade through multiple sources with clear priority:

```
CLI flag (highest)  →  Env var  →  Interactive prompt (TTY only)  →  Config file (v1.1)  →  Default (lowest)
```

### How it works

```python
@app.command
def serve(
    *,
    port: Annotated[int, Param(alias="p", env="PORT", help="Server port")] = 8080,
    host: Annotated[str, Param(env="HOST")] = "0.0.0.0",
):
    """Start the server."""
    return {"port": port, "host": host}
```

```sh
$ my-cli serve --port 3000         # CLI flag wins
$ PORT=3000 my-cli serve           # Env var used (no flag)
$ my-cli serve                     # Default 8080 used
```

### Config file support (v1.1)

```python
app = App("my-cli", config_files=[
    "agentcli.toml",                 # Project-local
    "~/.config/my-cli/config.toml",  # User config
])
```

Config files use **snake_case** keys matching Python parameter names (not kebab-case CLI flags). Loaded with stdlib `tomllib` (Python 3.11+).

### Internal resolver design

The resolver pipeline is designed with an extensible slot architecture from v1, even though config files are v1.1:

```python
# Internal protocol — not public API
class Resolver(Protocol):
    def resolve(self, param: ParamSpec) -> tuple[Any, str] | None:
        """Returns (value, source_name) or None if not resolved."""

# v1 resolvers: CliResolver → EnvResolver → PromptResolver → DefaultResolver
# v1.1 adds: ConfigFileResolver (between PromptResolver and DefaultResolver)
```

---

## Built-in Flags (v1)

| Flag | Description |
|------|-------------|
| `--help`, `-h` | Show help text |
| `--version` | Print version |
| `--format <fmt>` | Output format: `toon`, `json`, `yaml`, `md`, `jsonl` |
| `--json` | Shorthand for `--format json` |
| `--verbose` | Show full envelope with metadata |
| `--llms` | Compact command index (markdown) |
| `--llms-full` | Full command manifest |
| `--mcp` | Start as MCP stdio server |
| `--wizard` | Interactive guided mode |

**Flag interaction semantics:**

| Combination | Behavior |
|-------------|----------|
| `--wizard --format json` | Outputs JSON Schema of parameters (no prompts) |
| `--filter X --format json` | Filters the JSON output |
| `--verbose --json` | Full envelope in JSON |
| `--llms --format json` | Manifest as JSON Schema instead of markdown |

**Deferred to v2**: `--filter`, `--schema`, `--token-count`, `--token-limit`, `--token-offset`, `--no-color`, `--completions`

---

## Testing

```python
from agentcli.testing import CliRunner
from my_cli import app

runner = CliRunner(app)

def test_greet():
    result = runner.invoke(["greet", "world"])
    assert result.exit_code == 0
    assert result.data == {"message": "hello world"}

def test_greet_json():
    result = runner.invoke(["greet", "world", "--format", "json"])
    assert '"message": "hello world"' in result.output

def test_deploy_missing_env():
    result = runner.invoke(["deploy"])
    assert result.exit_code == 1
    assert result.error.code == "MISSING_ARG"

def test_deploy_with_env_var():
    result = runner.invoke(["deploy", "staging"], env={"DEPLOY_TOKEN": "secret"})
    assert result.exit_code == 0

def test_llms_manifest():
    result = runner.invoke(["--llms"])
    assert "| Command |" in result.output

# Context manager style
def test_with_context():
    with app.test() as client:
        result = client.invoke(["deploy", "staging"])
        assert result.data["url"] == "https://staging.example.com"
```

`CliRunner` captures stdout/stderr, exit codes, parses the envelope, and supports env var injection — all without subprocess overhead.

---

## Dependencies

### Minimal required dependencies

The core framework has one tiny required dependency. This is critical for CLI tools where startup time matters.

| Dependency | Status | Purpose | Install |
|-----------|--------|---------|---------|
| `docstring-parser` | required | Docstring parameter extraction (pure Python, 37KB, zero transitive deps) | `pip install agentcli` |
| `rich` | optional | Beautiful help text, error panels, wizard UI | `pip install agentcli[rich]` |
| `pydantic` | optional | Model support for complex inputs/outputs | `pip install agentcli[pydantic]` |
| `pyyaml` | optional | YAML output format, YAML file params | `pip install agentcli[yaml]` |
| `mcp` | optional | MCP server mode | `pip install agentcli[mcp]` |
| all | optional | Everything | `pip install agentcli[all]` |

### Internal types

All internal framework types use stdlib `dataclasses`. No attrs, no Pydantic for internals.

### Import time target

`import agentcli` should complete in **< 50ms** with zero optional deps installed.

---

## Project Structure

```
src/agentcli/
    __init__.py       # Public API: App, run, Param, Result, AgentCliError, Context
    _app.py           # App class: command registration, serve, middleware
    _parser.py        # Custom argv parser (positionals, flags, aliases, coercion)
    _schema.py        # Function signature → CommandSchema extraction
    _output.py        # Envelope, TOON encoder, JSON/YAML/MD formatters
    _help.py          # Help AST (internal), renderers (ANSI, plain, markdown, JSON)
    _errors.py        # Exception hierarchy, auto-correction
    _context.py       # Context class (agent detection, state, meta)
    _agents.py        # --llms, --mcp, agent detection, skill generation
    _wizard.py        # --wizard interactive mode, prompt primitives
    _types.py         # Internal dataclasses (CommandEntry, CommandSchema, etc.)
    prompt.py         # Public prompt API (text, select, confirm, password) — sync
    testing.py        # CliRunner, Result, test utilities
    py.typed          # PEP 561 marker
```

12 files total. Split further only when a file exceeds ~500 lines.

---

## Param class (v1)

```python
@dataclass(frozen=True)
class Param:
    """Metadata for a CLI parameter. Use inside Annotated[T, Param(...)]."""
    help: str | None = None            # Override docstring description
    alias: str | None = None           # Short flag alias (-f, -v)
    env: str | None = None             # Read from environment variable
    prompt: str | None = None          # Prompt message if value not provided (TTY only)
    secret: bool = False               # Hide input in prompts (for passwords/keys)
    deprecated: bool = False           # Mark as deprecated
    hidden: bool = False               # Hide from help text
```

**Deferred to v1.1**: `group`, `converter`, `validator`, `file`, `format`, `exists`. Keeping `Param` lean for v1 — 7 fields.

---

## Competitive Comparison

| Feature | Click | Typer | cyclopts | Effect CLI | **agentcli** |
|---------|-------|-------|----------|------------|--------------|
| Agent discovery | — | — | — | — | **--llms, --mcp, skills** |
| Structured output | — | — | — | — | **Envelope, TOON** |
| Token efficiency | — | — | — | — | **TOON (40-60% savings)** |
| Call-to-actions | — | — | — | — | **CTAs guide agents** |
| MCP server | — | — | — | — | **Built-in --mcp flag** |
| Output formats | — | — | — | — | **TOON/JSON/YAML/MD/JSONL** |
| Wizard mode | — | — | — | **Built-in** | **Built-in** |
| Nested config | — | — | partial | **Full** | **Full** |
| Fallback prompts | — | — | — | **Built-in** | **Built-in** |
| Config layering | — | — | partial | **Full** | **CLI→env→prompt→config→default** |
| Auto-correction | — | — | partial | **Built-in** | **Built-in** |
| Type hints | Decorator-heavy | Annotated | **Native** | Zod-like | **Native** |
| Middleware | — | — | — | **Effect layers** | **Onion @app.use** |
| Required deps | 0 | click+rich | attrs+rich | effect | **1 (docstring-parser)** |

---

## Implementation Phases

### Phase 1: Core CLI Engine (MVP)
*Goal: A developer can define commands, parse args, get structured output*

1. `_types.py` — Internal dataclasses (CommandEntry, CommandSchema, FieldInfo)
2. `_errors.py` — AgentCliError, ValidationError, ParseError, auto-correction
3. `_schema.py` — Function signature → CommandSchema (inspect + Annotated + docstrings)
4. `_parser.py` — Argv parser (positionals, --flags, -aliases, coercion, --no-prefix)
5. `_output.py` — TOON encoder + JSON formatter + envelope wrapping
6. `_context.py` — Context with agent detection, state dict
7. `_help.py` — Help AST + ANSI/plain/markdown renderers
8. `_app.py` — App class: @app.command, app.mount(), app(), middleware hooks
9. `__init__.py` — Public API surface (App, run, Param, Result, AgentCliError)
10. `testing.py` — CliRunner with structured Result

**Milestone**: `pip install agentcli` → define commands → get structured TOON/JSON output.

### Phase 2: Agent Discovery
*Goal: Agents can discover and use agentcli CLIs*

11. `_agents.py` — --llms manifest generation, --llms-full, agent directory registry
12. `_agents.py` — --mcp flag: MCP stdio server bridge (requires `agentcli[mcp]`)

**Milestone**: `my-cli --llms` shows manifest, `my-cli --mcp` starts MCP server.

### Phase 3a: Middleware & Streaming
*Goal: Composable middleware and async streaming*

13. Middleware system (@app.use, onion composition)
14. Streaming support (async generators)

### Phase 3b: Interactive Features
*Goal: Wizard mode and fallback prompts*

15. `_wizard.py` — --wizard mode, auto-prompt generation from schemas
16. `prompt.py` — Standalone prompt primitives (text, select, confirm, password)
17. Fallback prompts (`Param(prompt="...")`)
18. Rich help text (when rich installed)

**Milestone**: Feature-complete v1.0 release.

### Phase 4: Ecosystem (v1.1+)
19. `skills add` / `mcp add` built-in commands
20. Nested config object expansion (dataclass/Pydantic → dot-notation flags)
21. File/schema parameters (`Param(file=True, format="yaml")`)
22. Config file support (TOML via tomllib, YAML, JSON)
23. `--filter` output filtering (dot-notation key paths)
24. Shell completions (bash, zsh, fish)
25. YAML/Markdown output formatters
26. Pydantic model support (when pydantic installed)
27. Token pagination (--token-count, --token-limit, --token-offset)
28. HTTP integration (ASGI handler, API-as-CLI)
29. Sphinx/MkDocs extension
30. `agentcli migrate` tool (Click/Typer → agentcli)
31. OpenAPI spec import — generate typed CLI commands from OpenAPI specs (inspired by incur)
32. `CliConfig` parsing behavior object — configurable parsing options

---

## OpenAPI Spec Import (v1.1+, inspired by incur)

Generate typed CLI commands from an OpenAPI specification. Given a URL or file path to an OpenAPI 3.x spec, agentcli auto-generates a command group where each API endpoint becomes a CLI command with fully typed parameters.

```python
from agentcli import App

app = App("my-api")
app.from_openapi("https://api.example.com/openapi.json", prefix="api")
app()

# $ my-api api list-users --limit 10 --offset 0
# $ my-api api get-user 42
# $ my-api api create-user --name Alice --email alice@example.com
```

**How it works:**
1. Parse the OpenAPI spec (JSON or YAML)
2. For each path+method, create a command: `operationId` → command name (kebab-case)
3. Path parameters → positional args, query/header/body parameters → keyword options
4. Response schema → output type annotation for `--llms` manifest
5. Authentication schemes → middleware or `Param(env="API_KEY", secret=True)`
6. Group by tags → mount as sub-apps

**Scope**: This is a v1.1+ feature. Core implementation uses stdlib `json` + optional `pyyaml`. HTTP calls use `urllib.request` (no requests/httpx dependency).

---

## CliConfig (inspired by Effect CLI)

Configurable parsing and framework behavior via a dedicated config object on `App`:

```python
from agentcli import App, CliConfig

app = App("my-cli", config=CliConfig(
    case_sensitive=True,           # Command/flag matching (default: False)
    autocorrect_threshold=2,       # Levenshtein distance for suggestions (default: 2)
    show_built_in_flags=True,      # Show --help, --version, etc. in help (default: True)
    max_nesting_depth=4,           # Max depth for nested config expansion (default: 4)
    allow_unknown_flags=False,     # Pass-through unknown flags (default: False)
    prompt_missing_required=True,  # Auto-prompt for missing required params in TTY (default: False)
))
```

**Fields (v1):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `case_sensitive` | `bool` | `False` | Case-sensitive command and flag matching |
| `autocorrect_threshold` | `int` | `2` | Max Levenshtein distance for "did you mean?" suggestions |
| `show_built_in_flags` | `bool` | `True` | Whether `--help`, `--version`, etc. appear in help output |
| `max_nesting_depth` | `int` | `4` | Maximum depth for nested config object expansion |
| `allow_unknown_flags` | `bool` | `False` | Whether to pass through unknown flags instead of erroring |
| `prompt_missing_required` | `bool` | `False` | Auto-prompt for missing required params when in TTY mode |

Note: `autocorrect_threshold` was previously a direct `App()` kwarg (`App("my-cli", autocorrect_threshold=2)`). With `CliConfig`, it moves to the config object. The `App` kwarg remains as a convenience shorthand for backwards compatibility.

---

## Design Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Package name | `agentcli` | Descriptive, available on PyPI, self-explanatory |
| Entry point | `app()` (callable) | Click/Typer/cyclopts convention, not `serve()` |
| Arg vs Option | `*` separator | Python's native syntax, no abstraction needed |
| Metadata class | Single `Param` (7 fields in v1) | `*` determines arg/option; `Param` adds extras only |
| Schema definition | Type hints + `Annotated` | Zero deps, Pythonic, cyclopts-proven pattern |
| Return style | `return data` / `return Result(data, cta)` | Python's native return/raise semantics |
| Error style | `raise AgentCliError(...)` | Pythonic, no `ctx.error()` method |
| Context | Opt-in via `ctx: agentcli.Context` | Most commands don't need it |
| Required deps | `docstring-parser` only | Tiny pure-Python dep; startup time matters for CLIs |
| Internal types | `dataclasses` | Stdlib, no external deps |
| Default format | Pretty (TTY) / TOON (non-TTY) | Humans get color, agents get efficiency |
| TOON | Built-in encoder | No Python TOON package exists, < 300 lines |
| Parser | Custom | argparse can't handle dynamic schemas |
| Async support | Detect + asyncio.run() | `app()` is sync, wraps async via asyncio.to_thread |
| Help system | Internal AST | Multiple renderers, not public API (Effect CLI idea) |
| Wizard mode | Auto-generated from params | Zero extra code, every command gets it free (Effect CLI idea) |
| Nested config | Recursive expansion → options | All fields become --prefix.field options (Effect CLI idea) |
| Fallback prompts | Param(prompt="..."), sync | Interactive UX when flags omitted (Effect CLI idea) |
| Prompts | Synchronous API | Matches Python CLI conventions (questionary, click.prompt) |
| Auto-correction | Levenshtein, threshold=2 | Better UX for typos, max 3 suggestions (Effect CLI idea) |
| Config layering | CLI → env → prompt → config → default | Clear priority chain (Effect CLI idea) |
| Config file keys | snake_case (matching Python params) | Not kebab-case CLI flags |
| Min Python | 3.11 | StrEnum, tomllib, Self, 3.10 EOL Oct 2026 |
| HTTP integration | Deferred to v2 | Python has FastAPI; focus on CLI + agents |
| Token pagination | Deferred to v2 | Nice-to-have, not essential for MVP |
| --filter | Deferred to v1.1 | Reduces v1 scope |
| OpenAPI import | Deferred to v1.1 | Powerful for API-as-CLI, but complex; uses stdlib only (incur idea) |
| CliConfig object | v1, expanded in v1.1 | Centralizes parsing behavior; `autocorrect_threshold` kwarg kept as shorthand (Effect CLI idea) |

---

## What Makes a Python Developer Choose agentcli?

1. **Structured output with zero effort**: Return a dict → get TOON/JSON/YAML. No `print()` parsing.
2. **Agent discoverability**: `--llms` generates manifests. `--mcp` starts MCP server. No config.
3. **CTAs**: `return Result(data, cta=[...])` — agents know what to do next.
4. **Token efficiency**: TOON saves 40-60% on tokens vs JSON. Matters for cost and context.
5. **Wizard mode for free**: Every command gets `--wizard` automatically. No extra code.
6. **Middleware**: No other Python CLI framework has `@app.use` onion middleware.
7. **Near-zero dependencies**: One tiny pure-Python dep. Faster import than Click, Typer, or cyclopts.
8. **Nested config objects**: Dataclasses expand to dot-notation flags and reconstruct automatically.
9. **Future-proof**: As AI agents become primary CLI consumers, agentcli is ready. Others aren't.
