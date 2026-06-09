import asyncio
import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_DB = os.getenv("MONGO_DB", "nanogaze_mlops")
_MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

_server_params = StdioServerParameters(
    command="mongodb-mcp-server",
    args=[],
    env={**os.environ, "MDB_MCP_CONNECTION_STRING": _MONGO_URI},
)


def _parse_docs(result) -> list:
    for item in result.content:
        text = getattr(item, "text", None)
        if not text:
            continue
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("documents", "result", "data"):
                    if isinstance(data.get(key), list):
                        return data[key]
        except (json.JSONDecodeError, TypeError):
            continue
    return []


class MCPClient:
    """Async context manager — one MCP session per pipeline run."""

    async def __aenter__(self):
        self._stdio = stdio_client(_server_params)
        read, write = await self._stdio.__aenter__()
        self._session_cm = ClientSession(read, write)
        self.session = await self._session_cm.__aenter__()
        await self.session.initialize()
        print("[MCP] MongoDB MCP session started")
        return self

    async def __aexit__(self, *args):
        await self._session_cm.__aexit__(*args)
        await self._stdio.__aexit__(*args)
        print("[MCP] MongoDB MCP session closed")

    async def find_all(self, collection: str) -> list:
        result = await self.session.call_tool("find", {
            "collection": collection,
            "database": _DB,
            "filter": {},
            "projection": {"_id": 0},
        })
        return _parse_docs(result)

    async def delete_all(self, collection: str) -> None:
        await self.session.call_tool("deleteMany", {
            "collection": collection,
            "database": _DB,
            "filter": {},
        })

    async def insert_many(self, collection: str, documents: list) -> None:
        if not documents:
            return
        try:
            await self.session.call_tool("insertMany", {
                "collection": collection,
                "database": _DB,
                "documents": documents,
            })
        except Exception:
            for doc in documents:
                await self.session.call_tool("insertOne", {
                    "collection": collection,
                    "database": _DB,
                    "document": doc,
                })
