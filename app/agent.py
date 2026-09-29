# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from app.a2ui_utils import a2ui_callback
from app.tools import (
    calculate_training_zones,
    generate_achievement_badge,
    generate_workout_video,
    get_outdoor_training_conditions,
    get_workout_details,
    log_workout,
    search_workouts,
)

# Load Agent Engine resource name or sandbox from deployment_metadata.json
metadata_path = Path(__file__).parent.parent / "deployment_metadata.json"
remote_agent_runtime_id = None
sandbox_resource_name = None

if metadata_path.exists():
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            remote_agent_runtime_id = metadata.get("remote_agent_runtime_id")
            sandbox_resource_name = metadata.get("sandbox_resource_name")
    except Exception:
        pass

# Extract Memory Bank ID from remote_agent_runtime_id
memory_bank_id = remote_agent_runtime_id.split("/")[-1] if remote_agent_runtime_id else None
if memory_bank_id:
    os.environ.setdefault("GOOGLE_CLOUD_AGENT_ENGINE_ID", memory_bank_id)

code_executor = None
if sandbox_resource_name:
    code_executor = AgentEngineSandboxCodeExecutor(sandbox_resource_name=sandbox_resource_name)
elif remote_agent_runtime_id:
    code_executor = AgentEngineSandboxCodeExecutor(agent_engine_resource_name=remote_agent_runtime_id)


async def generate_memories_callback(callback_context: CallbackContext):
    """Sends session events to Vertex AI Memory Bank after each turn to extract durable user facts."""
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        print(f"Memory bank callback note: {e}")
    return None


def memory_service_builder():
    """Builds VertexAiMemoryBankService for deployed Agent Platform container."""
    return VertexAiMemoryBankService(
        project="qwiklabs-gcp-02-c53b8191d8d2",
        location="us-east1",
        agent_engine_id=memory_bank_id or "810874432322011136",
    )


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are an expert Multi-Sport AI Fitness Coach helping athletes across running, cycling, "
        "swimming, weightlifting, and triathlon. Use your Firestore tools (`search_workouts`, `get_workout_details`, "
        "`log_workout`), calculation tools (`calculate_training_zones`), live weather API (`get_outdoor_training_conditions`), "
        "and image generation tool (`generate_achievement_badge`) to manage workout routines, compute heart rate zones, "
        "check outdoor training weather, and reward athlete achievements with custom badge artwork. "
        "You remember user fitness goals, stated preferences, medical conditions, and progress across sessions. "
        "You can also safely run Python code in a sandbox for advanced data analysis or fitness calculations."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Output an A2UI JSON array containing BOTH a 'beginRendering' message (with 'surfaceId' and 'root') "
        "and a 'surfaceUpdate' message. "
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        get_weather,
        get_current_time,
        search_workouts,
        get_workout_details,
        log_workout,
        calculate_training_zones,
        get_outdoor_training_conditions,
        generate_achievement_badge,
        generate_workout_video,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
    code_executor=code_executor,
)


app = App(
    root_agent=root_agent,
    name="app",
)




