"""Dynamic prompt library with learning-based updates.

Manages prompt templates that can be improved through learning.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from .logger import AuditLogger


class PromptLibrary:
    """Manages dynamic prompt templates that improve through learning.

    Responsibilities:
    - Store and retrieve prompt templates
    - Apply improvements from learning system
    - Track prompt evolution history
    - Version control for prompts
    """

    def __init__(self, prompts_file: str, logger: AuditLogger):
        """Initialize prompt library.

        Args:
            prompts_file: Path to JSON file storing prompts
            logger: Audit logger instance
        """
        self.prompts_file = Path(prompts_file)
        self.logger = logger
        self.prompts: Dict[str, Dict] = {}
        self._load_prompts()

    def _load_prompts(self):
        """Load prompts from file."""
        if self.prompts_file.exists():
            with open(self.prompts_file, "r") as f:
                self.prompts = json.load(f)
            self.logger.info(
                "prompts_loaded",
                count=len(self.prompts),
                file=str(self.prompts_file),
            )
        else:
            # Initialize with default prompts
            self.prompts = self._get_default_prompts()
            self._save_prompts()

    def _save_prompts(self):
        """Save prompts to file."""
        self.prompts_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.prompts_file, "w") as f:
            json.dump(self.prompts, f, indent=2)

    def _get_default_prompts(self) -> Dict[str, Dict]:
        """Get default prompt templates."""
        return {
            "issue_analysis": {
                "template": """Analyze this GitHub issue and determine its actionability:

Issue #{issue_number}: {title}

Description:
{body}

Labels: {labels}

Provide analysis:
1. Is this actionable? (yes/no with confidence)
2. Estimated complexity (0-10)
3. What needs to be done?
4. Any risks or concerns?
""",
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "improvements": [],
            }
        }

    def get_prompt(self, prompt_id: str) -> Optional[str]:
        """Get a prompt template by ID.

        Args:
            prompt_id: Prompt identifier

        Returns:
            Prompt template string, or None if not found
        """
        if prompt_id in self.prompts:
            return self.prompts[prompt_id]["template"]
        return None

    def update_prompt(self, prompt_id: str, new_template: str, improvement_reason: str):
        """Update a prompt template with improvements.

        Args:
            prompt_id: Prompt to update
            new_template: New template string
            improvement_reason: Why this improvement was made
        """
        if prompt_id not in self.prompts:
            # Create new prompt
            self.prompts[prompt_id] = {
                "template": new_template,
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "improvements": [],
            }
        else:
            # Update existing
            old_template = self.prompts[prompt_id]["template"]
            self.prompts[prompt_id]["template"] = new_template
            self.prompts[prompt_id]["version"] += 1
            self.prompts[prompt_id]["updated_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            self.prompts[prompt_id]["improvements"].append(
                {
                    "version": self.prompts[prompt_id]["version"],
                    "reason": improvement_reason,
                    "previous_template": old_template,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        self._save_prompts()
        self.logger.info(
            "prompt_updated",
            prompt_id=prompt_id,
            version=self.prompts[prompt_id]["version"],
            reason=improvement_reason,
        )

    def get_prompt_history(self, prompt_id: str) -> list:
        """Get improvement history for a prompt.

        Args:
            prompt_id: Prompt identifier

        Returns:
            List of improvements
        """
        if prompt_id in self.prompts:
            return self.prompts[prompt_id].get("improvements", [])
        return []

    def rollback_prompt(self, prompt_id: str, version: int) -> bool:
        """Rollback a prompt to a previous version.

        Args:
            prompt_id: Prompt identifier
            version: Version number to rollback to

        Returns:
            True if successful
        """
        if prompt_id not in self.prompts:
            return False

        improvements = self.prompts[prompt_id].get("improvements", [])
        for improvement in improvements:
            if improvement["version"] == version:
                self.prompts[prompt_id]["template"] = improvement["previous_template"]
                self.prompts[prompt_id]["version"] = version
                self.prompts[prompt_id]["updated_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                self._save_prompts()
                self.logger.info(
                    "prompt_rolled_back", prompt_id=prompt_id, version=version
                )
                return True

        return False
