from __future__ import annotations

import unittest
from typing import Annotated, Literal

from agentcli import App, Context, Param, Result
from agentcli.testing import CliRunner


class AgentCliTests(unittest.TestCase):
    def test_basic_command(self) -> None:
        app = App("demo", version="1.0.0")

        @app.command
        def greet(name: str) -> dict[str, str]:
            return {"message": f"hello {name}"}

        result = CliRunner(app).invoke(["greet", "world", "--json"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.data, {"message": "hello world"})

    def test_env_resolution(self) -> None:
        app = App("deploy")

        @app.command
        def deploy(
            env: str, *, token: Annotated[str, Param(env="DEPLOY_TOKEN")]
        ) -> dict[str, str]:
            return {"env": env, "token": token}

        result = CliRunner(app).invoke(
            ["deploy", "staging", "--json"], env={"DEPLOY_TOKEN": "secret"}
        )
        self.assertEqual(result.data["token"], "secret")

    def test_missing_argument(self) -> None:
        app = App("demo")

        @app.command
        def greet(name: str) -> dict[str, str]:
            return {"message": name}

        result = CliRunner(app).invoke(["greet", "--json"])
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.error.code, "MISSING_ARG")

    def test_llms_manifest(self) -> None:
        app = App("demo", version="1.0.0", description="Demo app")

        @app.command
        def greet(name: str) -> dict[str, str]:
            return {"message": name}

        result = CliRunner(app).invoke(["--llms"])
        self.assertIn("| Command |", result.output)
        self.assertIn("demo greet", result.output)

    def test_mounts_and_middleware(self) -> None:
        app = App("gh")
        pr = App("pr")
        app.mount(pr)

        @app.use
        async def root_middleware(ctx: Context, next_call):
            ctx.state["root"] = True
            return await next_call()

        @pr.command
        def list_(ctx: Context) -> dict[str, bool]:
            return {"root": bool(ctx.state.get("root"))}

        result = CliRunner(app).invoke(["pr", "list", "--json"])
        self.assertEqual(result.data, {"root": True})

    def test_async_and_streaming(self) -> None:
        app = App("logs")

        @app.command
        async def tail(*, follow: bool = False):
            for line in ["a", "b"]:
                yield {"line": line, "follow": follow}

        result = CliRunner(app).invoke(["tail", "--follow", "--format", "jsonl"])
        self.assertIn('"line": "a"', result.output)
        self.assertIn('"line": "b"', result.output)

    def test_wizard_schema_non_tty(self) -> None:
        app = App("deploy")

        @app.command
        def run(
            env: Annotated[
                Literal["staging", "production"], Param(help="Target environment")
            ],
            *,
            force: bool = False,
        ) -> dict[str, str]:
            return {"env": env, "force": str(force)}

        result = CliRunner(app).invoke(["run", "--wizard", "--json"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("parameters", result.output)

    def test_result_cta_verbose(self) -> None:
        app = App("deploy")

        @app.command
        def run() -> Result:
            return Result({"ok": True}, cta=["deploy status"])

        result = CliRunner(app).invoke(["run", "--json", "--verbose"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("deploy status", result.output)

    def test_default_command_bare_decorator(self) -> None:
        app = App("fetch", description="Fetch things")

        @app.default
        def fetch_cases(*, limit: int = 10) -> dict[str, int]:
            return {"fetched": limit}

        result = CliRunner(app).invoke(["--limit", "5", "--json"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.data, {"fetched": 5})

    def test_default_command_no_args(self) -> None:
        app = App("cases")

        @app.default
        def list_cases() -> dict[str, str]:
            return {"status": "ok"}

        result = CliRunner(app).invoke(["--json"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.data, {"status": "ok"})

    def test_default_command_with_subcommands(self) -> None:
        """Default runs when no sub-command matches, sub-commands still work."""
        app = App("eval")

        @app.default
        def run_eval(case: str = "all") -> dict[str, str]:
            return {"case": case}

        @app.command
        def show() -> dict[str, str]:
            return {"action": "show"}

        # No args → default
        result = CliRunner(app).invoke(["--json"])
        self.assertEqual(result.data, {"case": "all"})

        # Positional arg → default with value
        result = CliRunner(app).invoke(["mibc-001", "--json"])
        self.assertEqual(result.data, {"case": "mibc-001"})

        # Sub-command → show
        result = CliRunner(app).invoke(["show", "--json"])
        self.assertEqual(result.data, {"action": "show"})

    def test_default_on_mounted_subapp(self) -> None:
        """@app.default works on sub-apps mounted via app.mount()."""
        root = App("ev")
        fetch = App("fetch")
        root.mount(fetch)

        @fetch.default
        def fetch_cases(*, limit: int = 20) -> dict[str, int]:
            return {"limit": limit}

        result = CliRunner(root).invoke(["fetch", "--json"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.data, {"limit": 20})

        result = CliRunner(root).invoke(["fetch", "--limit", "5", "--json"])
        self.assertEqual(result.data, {"limit": 5})


if __name__ == "__main__":
    unittest.main()
