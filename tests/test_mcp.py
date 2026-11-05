"""Exercise real MCP stdio messages, including a tool that logs progress."""
import asyncio
import os
import sys
from datetime import timedelta


def test_stdio_initialize_list_and_call(tmp_path, caplog):
    import pytest
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    gh = tmp_path / "gh"
    gh.write_text('''#!/usr/bin/env python3
import json, sys
endpoint = next(arg for arg in sys.argv if arg.startswith("/repos/"))
if "/git/ref/" in endpoint:
    result = {"object": {"sha": "commit"}}
elif "/git/commits/" in endpoint:
    result = {"tree": {"sha": "tree"}}
elif "/git/trees/" in endpoint:
    result = {"tree": [{"path": "main.py", "type": "blob"}], "truncated": False}
elif endpoint.endswith("/languages"):
    result = {"Python": 10}
else:
    result = {"default_branch": "main"}
print(json.dumps(result))
''')
    gh.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    async def check():
        params = StdioServerParameters(command=sys.executable, args=["-c", "from acta.cli import app; app()", "mcp"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "acta-ergo-sum"
                tools = await session.list_tools()
                assert {tool.name for tool in tools.tools} == {
                    "deep_analyze_repo", "get_repo_structure", "get_repo_key_files", "get_repo_evolution"}
                result = await session.call_tool("get_repo_structure", {"repo": "alice/demo"})
                assert not result.isError
                assert "main.py" in result.content[0].text
    asyncio.run(check())
    assert not any("Failed to parse JSONRPC" in record.message for record in caplog.records)
