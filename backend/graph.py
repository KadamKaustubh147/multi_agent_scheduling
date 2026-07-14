import os
from datetime import date
from typing import Optional, Annotated
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from tools import ALL_TOOLS

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ─── Graph state ─────────────────────────────────────────────────────────────

class State(dict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: Optional[str]  # "general" | "booking" | None

# ─── LLMs (one per role so prompts don't clash) ─────────────────────────────

_triage_llm  = ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL, temperature=0)
_general_llm = ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL, temperature=0.7)
_booking_llm = ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL, temperature=0.2).bind_tools(ALL_TOOLS)

# ─── Prompts ─────────────────────────────────────────────────────────────────

TRIAGE_SYS  = 'Classify the user message. Return ONLY JSON: {"intent":"general"|"booking","reasoning":"..."}'
GENERAL_SYS = "Friendly assistant. Keep replies short. If user wants to book, tell them to ask."

BOOKING_SYS = (
    f"You book appointments. Today is {date.today().isoformat()}. Slots: 09:00-17:00 hourly.\n\n"
    "CRITICAL RULES (NEVER BREAK THESE):\n"
    "1. NEVER invent, guess, or use placeholder emails (like user@example.com). If you don't have the user's email, ASK FOR IT.\n"
    "2. You MUST have a valid email from the user BEFORE calling reserve_slot.\n"
    "3. When calling send_booking_notification, the 'details' argument MUST be a valid JSON string "
    'containing the keys "date", "time", and "id". Example: details=\'{"date": "2025-07-14", "time": "11:00", "id": 1}\'\n\n'
    "WORKFLOW:\n"
    "1) Get date -> call check_availability\n"
    "2) If taken, negotiate alternatives\n"
    "3) Ask user for email -> call reserve_slot(date, time, email)\n"
    "4) Call send_booking_notification(email, details) using the exact JSON string format.\n\n"
    "Be concise."
)

# ─── Nodes ───────────────────────────────────────────────────────────────────

def triage_node(state: State) -> dict:
    """Classify intent. If general, answer directly. If booking, hand off."""
    msgs = [SystemMessage(content=TRIAGE_SYS)] + list(state["messages"])
    
    try:
        from pydantic import BaseModel as B, Field as F
        class Result(B):
            intent: str
            reasoning: str = F(default="")
        out = _triage_llm.with_structured_output(Result).invoke(msgs)
        intent = out.intent
    except Exception:
        # Keyword fallback if structured parsing fails
        last = state["messages"][-1].content.lower() if state["messages"] else ""
        kws = ["book", "schedule", "appointment", "available", "reserve", "slot"]
        intent = "booking" if any(k in last for k in kws) else "general"

    if intent == "general":
        resp = _general_llm.invoke([SystemMessage(content=GENERAL_SYS)] + list(state["messages"]))
        return {"messages": [resp], "intent": "general"}
    
    return {"intent": "booking"}


def booking_node(state: State) -> dict:
    """Booking specialist — may call tools or reply directly."""
    resp = _booking_llm.invoke([SystemMessage(content=BOOKING_SYS)] + list(state["messages"]))
    return {"messages": [resp]}


def route_after_triage(state: State) -> str:
    return "booking" if state.get("intent") == "booking" else END

# ─── Build graph ─────────────────────────────────────────────────────────────

def build_graph(checkpointer):
    tool_node = ToolNode(ALL_TOOLS)

    g = StateGraph(State)
    g.add_node("triage",  triage_node)
    g.add_node("booking", booking_node)
    g.add_node("tools",   tool_node)

    g.add_edge(START, "triage")
    g.add_conditional_edges("triage",  route_after_triage, {"booking": "booking", END: END})
    g.add_conditional_edges("booking", tools_condition,    {"tools": "tools",   END: END})
    g.add_edge("tools", "booking")

    return g.compile(checkpointer=checkpointer)