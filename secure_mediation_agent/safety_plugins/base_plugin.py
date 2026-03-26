# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Base plugin interface - Simplified version for compatibility."""

from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class CallbackContext:
    """Context passed to callbacks."""
    pass


class BasePlugin:
    """Base class for ADK plugins."""

    def __init__(self, name: str):
        """Initialize plugin.

        Args:
            name: Plugin name
        """
        self.name = name

    async def on_user_message_callback(self, invocation_context, user_message):
        """Called when user message is received.

        Args:
            invocation_context: Invocation context
            user_message: User message content

        Returns:
            Modified message or None
        """
        return None

    async def before_run_callback(self, invocation_context):
        """Called before agent run.

        Args:
            invocation_context: Invocation context

        Returns:
            Modified content or None
        """
        return None

    async def before_tool_callback(self, tool, tool_args, tool_context):
        """Called before tool execution.

        Args:
            tool: Tool instance
            tool_args: Tool arguments
            tool_context: Tool context

        Returns:
            Modified args or None
        """
        return None

    async def after_tool_callback(self, tool, tool_args, tool_context, result):
        """Called after tool execution.

        Args:
            tool: Tool instance
            tool_args: Tool arguments
            tool_context: Tool context
            result: Tool result

        Returns:
            Modified result or None
        """
        return None

    async def after_model_callback(self, callback_context, llm_response):
        """Called after model response.

        Args:
            callback_context: Callback context
            llm_response: LLM response

        Returns:
            Modified response or None
        """
        return None
