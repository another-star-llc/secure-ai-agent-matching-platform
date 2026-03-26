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

"""Shared utilities for plan management and parsing."""

import json
import os
from datetime import datetime
from pathlib import Path


async def load_plan_from_artifact(
    plan_id: str,
    artifacts_dir: str = "secure_mediation_agent/artifacts/plans",
) -> str:
    """Load a plan from the artifacts directory.

    Args:
        plan_id: Plan identifier to load.
        artifacts_dir: Directory where plan artifacts are stored.

    Returns:
        JSON string with plan content or error.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Convert to absolute path relative to project root
    if not os.path.isabs(artifacts_dir):
        current_dir = Path(__file__).parent.parent.parent
        artifacts_dir = current_dir / artifacts_dir
    else:
        artifacts_dir = Path(artifacts_dir)

    if not artifacts_dir.exists():
        return json.dumps({
            "error": f"Artifacts directory not found: {artifacts_dir}",
            "success": False,
        }, ensure_ascii=False)

    # Find the most recent plan file with the given plan_id
    plan_files = list(artifacts_dir.glob(f"{plan_id}_*.md"))

    if not plan_files:
        return json.dumps({
            "error": f"No plan files found for plan_id: {plan_id}",
            "success": False,
            "searched_in": str(artifacts_dir),
        }, ensure_ascii=False)

    # Sort by modification time (most recent first)
    latest_plan = max(plan_files, key=lambda p: p.stat().st_mtime)

    try:
        with open(latest_plan, 'r', encoding='utf-8') as f:
            plan_content = f.read()

        logger.info(f"=� Loaded plan from {latest_plan}")

        return json.dumps({
            "plan_id": plan_id,
            "file_path": str(latest_plan),
            "content": plan_content,
            "loaded_at": datetime.now().isoformat(),
            "success": True,
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error loading plan {latest_plan}: {e}")
        return json.dumps({
            "error": f"Failed to load plan: {str(e)}",
            "file_path": str(latest_plan),
            "success": False,
        }, ensure_ascii=False)


async def parse_plan_for_step(
    plan_content: str,
    step_id: str,
) -> str:
    """Parse plan content and extract information for a specific step.

    Args:
        plan_content: Full plan content (markdown).
        step_id: Step identifier to extract (e.g., "step_1", "Step 1").

    Returns:
        JSON string with parsed step information.
    """
    import re

    # Try to find the step in the markdown
    # Look for patterns like "#### Step 1:", "## Step 1:", "Step 1:", etc.
    step_patterns = [
        rf"####\s*{step_id}[:\s]+(.*?)(?=####|\n##|\Z)",
        rf"###\s*{step_id}[:\s]+(.*?)(?=###|\n##|\Z)",
        rf"##\s*{step_id}[:\s]+(.*?)(?=##|\Z)",
        rf"{step_id}[:\s]+(.*?)(?=\n(?:Step|##)|\Z)",
    ]

    step_info = None
    for pattern in step_patterns:
        match = re.search(pattern, plan_content, re.IGNORECASE | re.DOTALL)
        if match:
            step_info = match.group(1).strip()
            break

    if not step_info:
        return json.dumps({
            "error": f"Step {step_id} not found in plan",
            "success": False,
        }, ensure_ascii=False)

    # Extract structured information
    result = {
        "step_id": step_id,
        "raw_content": step_info,
        "success": True,
    }

    # Extract agent name
    agent_match = re.search(r'\*\*(?:�S)?(?:Agent|������)[:\s]*\*\*\s*`?([^`\n]+)`?', step_info, re.IGNORECASE)
    if agent_match:
        result["expected_agent"] = agent_match.group(1).strip()

    # Extract input description
    input_match = re.search(r'\*\*(?:Input|e�)[:\s]*\*\*\s*(.+?)(?=\*\*|$)', step_info, re.DOTALL | re.IGNORECASE)
    if input_match:
        result["expected_input"] = input_match.group(1).strip()

    # Extract expected output
    output_match = re.search(r'\*\*(?:Expected Output|�U����)[:\s]*\*\*\s*(.+?)(?=\*\*|$)', step_info, re.DOTALL | re.IGNORECASE)
    if output_match:
        result["expected_output"] = output_match.group(1).strip()

    # Extract dependencies
    deps_match = re.search(r'\*\*(?:Dependencies|�X��)[:\s]*\*\*\s*(.+?)(?=\*\*|$)', step_info, re.DOTALL | re.IGNORECASE)
    if deps_match:
        deps_text = deps_match.group(1).strip()
        # Try to parse comma-separated or "Step X, Step Y" format
        result["dependencies"] = [d.strip() for d in re.findall(r'(?:Step\s*\d+|step_\d+|jW|None)', deps_text, re.IGNORECASE)]

    return json.dumps(result, indent=2, ensure_ascii=False)


async def load_all_conversations(
    plan_id: str,
    conversations_dir: str = "secure_mediation_agent/artifacts/conversations",
) -> str:
    """Load all conversation histories for a given plan_id.

    Args:
        plan_id: Plan identifier to load conversations for.
        conversations_dir: Directory where conversation artifacts are stored.

    Returns:
        JSON string with all conversation histories or error.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Fix common incorrect paths (LLM sometimes passes wrong paths)
    if conversations_dir in ["conversations/", "conversations", "artifacts/conversations"]:
        conversations_dir = "secure_mediation_agent/artifacts/conversations"
        logger.info(f"🔧 Corrected conversations_dir to: {conversations_dir}")

    # Convert to absolute path relative to project root
    if not os.path.isabs(conversations_dir):
        current_dir = Path(__file__).parent.parent.parent
        conversations_dir = current_dir / conversations_dir
    else:
        conversations_dir = Path(conversations_dir)

    # Get plan-specific conversation directory
    plan_conversations_dir = conversations_dir / plan_id

    if not plan_conversations_dir.exists():
        return json.dumps({
            "error": f"No conversations found for plan_id: {plan_id}",
            "success": False,
            "searched_in": str(plan_conversations_dir),
        }, ensure_ascii=False)

    # Find all conversation JSON files
    conversation_files = list(plan_conversations_dir.glob("*.json"))

    if not conversation_files:
        return json.dumps({
            "error": f"No conversation files found in: {plan_conversations_dir}",
            "success": False,
        }, ensure_ascii=False)

    # Load all conversations
    conversations = []
    for conv_file in sorted(conversation_files):
        try:
            with open(conv_file, 'r', encoding='utf-8') as f:
                conversation_data = json.load(f)
                conversations.append(conversation_data)
        except Exception as e:
            logger.warning(f"Failed to load conversation file {conv_file}: {e}")

    logger.info(f"📚 Loaded {len(conversations)} conversation histories for plan {plan_id}")

    return json.dumps({
        "plan_id": plan_id,
        "total_conversations": len(conversations),
        "conversations": conversations,
        "loaded_from": str(plan_conversations_dir),
        "loaded_at": datetime.now().isoformat(),
        "success": True,
    }, indent=2, ensure_ascii=False)
