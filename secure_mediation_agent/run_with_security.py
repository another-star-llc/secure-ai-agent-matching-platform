#!/usr/bin/env python3
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

"""Run Secure Mediation Agent with A2A Security Judge Plugin."""

import asyncio
import logging
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from google.adk import runners
from google.adk.cli import fast_api

# Import the main agent
import agent as agent_module
secure_mediator = agent_module.secure_mediator

# Import security plugin
try:
    import security.custom_judge as judge_module
    a2a_security_judge = judge_module.a2a_security_judge
    SECURITY_ENABLED = a2a_security_judge is not None
except ImportError as e:
    logging.warning(f"⚠️  Could not import security plugin: {e}")
    a2a_security_judge = None
    SECURITY_ENABLED = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_secure_runner():
    """Create a runner with security plugins enabled."""
    plugins = []

    if SECURITY_ENABLED:
        plugins.append(a2a_security_judge)
        logger.info("✅ A2A Security Judge Plugin ENABLED")
        logger.info("   - Monitoring A2A agent calls")
        logger.info("   - Detecting indirect prompt injection")
        logger.info("   - Validating plan adherence")
    else:
        logger.warning("⚠️  A2A Security Judge Plugin DISABLED")
        logger.warning("   Install safety_plugins to enable security monitoring")

    # Create runner with plugins
    runner = runners.InMemoryRunner(
        agent=secure_mediator,
        plugins=plugins
    )

    return runner


def main():
    """Main entry point."""
    logger.info("🛡️  Starting Secure Mediation Agent with Security Monitoring...")

    # Create runner
    runner = create_secure_runner()

    # Start FastAPI server
    logger.info("🌐 Starting Web UI on http://localhost:8000")

    # Use ADK's built-in FastAPI server
    import uvicorn
    from google.adk.cli.fast_api import create_app

    app = create_app(
        agent=secure_mediator,
        runner=runner,
        app_name="secure_mediation_agent",
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )


if __name__ == "__main__":
    main()
