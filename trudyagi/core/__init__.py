"""
trudyagi/core/__init__.py — package marker

Exposes the main entry points for the orchestrator.
"""

from .state import TaskState, new_task_id, list_all_tasks, VALID_STATES  # noqa: F401
from .llm_client import LLMClient, load_role_prompt  # noqa: F401
from .demo_llm import DemoLLMClient  # noqa: F401
from .orchestrator import run_pipeline  # noqa: F401
from . import worklog  # noqa: F401
