import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from graph import build_graph

CHECKPOINT_DB = "data/checkpoints.db"
Path("data").mkdir(exist_ok=True)

# ─── FastAPI Lifecycle ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as saver:
            print(f"✓ SQLite checkpointer → {CHECKPOINT_DB}")
            app.state.graph = build_graph(saver)
            app.state.saver = saver
            yield
    except Exception as e:
        from langgraph.checkpoint.memory import MemorySaver
        saver = MemorySaver()
        print(f"✗ SQLite failed ({e}), using MemorySaver")
        app.state.graph = build_graph(saver)
        app.state.saver = saver
        yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost", "https://multi-agent-scheduler.netlify.app/"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

# ─── Endpoints ───────────────────────────────────────────────────────────────

class ChatReq(BaseModel):
    message: str

@app.post("/api/chat")
def chat(req: ChatReq):
    config = {"configurable": {"thread_id": "default"}}

    result = app.state.graph.invoke(
        {"messages": [HumanMessage(content=req.message)], "intent": None},
        config=config,
    )

    # Format messages for the frontend
    out = []
    for m in result["messages"]:
        entry = {"type": m.type, "content": getattr(m, "content", "")}
        if m.type == "ai" and getattr(m, "tool_calls", None): 
            entry["tool_calls"] = m.tool_calls
        if hasattr(m, "name") and m.name: 
            entry["name"] = m.name
        out.append(entry)

    return {"messages": out}

@app.get("/api/messages")
async def get_messages():
    """Load previous messages on page refresh."""
    try:
        config = {"configurable": {"thread_id": "default"}}
        raw = []

        # Handle different langgraph checkpoint versions
        if hasattr(app.state.saver, "aget"):
            checkpoint = await app.state.saver.aget(config)
            if checkpoint and "channel_values" in checkpoint:
                raw = checkpoint["channel_values"].get("messages", [])
        elif hasattr(app.state.saver, "aget_tuple"):
            tup = await app.state.saver.aget_tuple(config)
            if tup:
                raw = tup.checkpoint.get("channel_values", {}).get("messages", [])

        # Use the EXACT same formatting logic as /api/chat
# Use the EXACT same formatting logic as /api/chat
        out = []
        for m in raw:
            entry = {"type": m.type, "content": getattr(m, "content", "")}
            if m.type == "ai" and getattr(m, "tool_calls", None):
                entry["tool_calls"] = m.tool_calls
            if hasattr(m, "name") and m.name:
                entry["name"] = m.name
            out.append(entry)
        return {"messages": out}

    except Exception as e:
        # Print error to terminal so we can see if something breaks
        print(f"Error loading messages: {e}")
        return {"messages": []}