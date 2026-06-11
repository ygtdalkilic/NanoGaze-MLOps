import json
import os
import re
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_DB = os.getenv("MONGO_DB", "apex_telemetry")
_MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")


def _to_standard_uri(uri: str) -> str:
    """mongodb-mcp-server can't parse mongodb+srv:// — resolve it to a standard
    multi-host mongodb:// string via DNS (same as the driver does internally)."""
    if not uri.startswith("mongodb+srv://"):
        return uri
    import dns.resolver

    rest = uri[len("mongodb+srv://"):]
    creds, _, tail = rest.partition("@")
    host = tail.split("/")[0].split("?")[0]

    srv = dns.resolver.resolve(f"_mongodb._tcp.{host}", "SRV")
    hosts = ",".join(f"{r.target.to_text().rstrip('.')}:{r.port}" for r in srv)

    opts = ""
    try:
        txt = dns.resolver.resolve(host, "TXT")
        opts = "".join(b.decode() for r in txt for b in r.strings)
    except Exception:
        pass

    params = "ssl=true" + (f"&{opts}" if opts else "") + "&retryWrites=true&w=majority"
    std = f"mongodb://{creds}@{hosts}/?{params}"
    print(f"[MCP] resolved srv -> mongodb://***@{hosts}/?{params}", flush=True)
    return std


_server_params = StdioServerParameters(
    command="mongodb-mcp-server",
    args=[],
    env={**os.environ, "MDB_MCP_CONNECTION_STRING": _to_standard_uri(_MONGO_URI)},
)


_ENVELOPE = re.compile(r"<untrusted-user-data-[0-9a-f-]+>\s*(.*?)\s*</untrusted-user-data-[0-9a-f-]+>", re.DOTALL)


def _parse_docs(result) -> list:
    for item in result.content:
        text = getattr(item, "text", None)
        if not text:
            continue
        for candidate in _ENVELOPE.findall(text) + [text]:
            try:
                data = json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("documents", "result", "data"):
                    if isinstance(data.get(key), list):
                        return data[key]
    return []


class MCPClient:
    """Async context manager — one MongoDB MCP session per run."""

    async def __aenter__(self):
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(_server_params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        print("[MCP] MongoDB MCP session connected")
        return self

    async def __aexit__(self, *args):
        try:
            await self._stack.aclose()
        except (RuntimeError, BaseExceptionGroup):
            pass  # anyio task-scope cleanup noise on loop teardown — work is already done
        print("[MCP] MongoDB MCP session closed")

    async def _call(self, tool: str, args: dict):
        result = await self.session.call_tool(tool, args)
        if getattr(result, "isError", False):
            texts = [getattr(i, "text", "") for i in result.content]
            raise RuntimeError(f"MCP {tool} failed: {' '.join(texts)}")
        return result

    async def find_all(self, collection: str) -> list:
        result = await self._call("find", {
            "collection": collection,
            "database": _DB,
            "filter": {},
            "projection": {"_id": 0},
            "limit": 1000,
        })
        return _parse_docs(result)

    async def delete_all(self, collection: str) -> None:
        await self._call("delete-many", {
            "collection": collection,
            "database": _DB,
            "filter": {},
        })

    async def insert_many(self, collection: str, documents: list) -> None:
        if not documents:
            return
        await self._call("insert-many", {
            "collection": collection,
            "database": _DB,
            "documents": documents,
        })

    async def upsert(self, collection: str, filter: dict, update: dict) -> None:
        await self._call("update-many", {
            "collection": collection,
            "database": _DB,
            "filter": filter,
            "update": update,
            "upsert": True,
        })
