"""Dynamic prompt library with learning-based updates.

Manages prompt templates that can be improved through learning.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..analyzers.context_builder import RepositoryContext
from .logger import AuditLogger


class PromptLibrary:
    """Manages dynamic prompt templates that improve through learning.

    Responsibilities:
    - Store and retrieve prompt templates
    - Apply improvements from learning system
    - Track prompt evolution history
    - Version control for prompts
    """

    def __init__(
        self,
        prompts_file: str,
        logger: AuditLogger,
        context: Optional[RepositoryContext] = None,
    ):
        """Initialize prompt library.

        Args:
            prompts_file: Path to JSON file storing prompts
            logger: Audit logger instance
            context: Optional repository context to enhance prompts
        """
        self.prompts_file = Path(prompts_file)
        self.logger = logger
        self.context = context
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

    def get_prompt(
        self, prompt_id: str, additional_context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Get a prompt template by ID, optionally enhanced with context.

        Args:
            prompt_id: Prompt identifier
            additional_context: Additional context variables to include

        Returns:
            Prompt template string with context, or None if not found
        """
        if prompt_id not in self.prompts:
            return None

        template = self.prompts[prompt_id]["template"]

        # Enhance with repository context if available
        if self.context:
            context_section = self._build_context_section(additional_context)
            if context_section:
                template = f"{template}\n\n{context_section}"

        return template

    def _build_context_section(
        self, additional_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build context section to append to prompts.

        Args:
            additional_context: Additional context variables

        Returns:
            Formatted context section
        """
        if not self.context:
            return ""

        sections = []

        # Add code style context
        sections.append("**Repository Context:**")
        sections.append(f"- Language: {self.context.code_style.language}")
        if self.context.code_style.version:
            sections.append(f"- Version: {self.context.code_style.version}")
        if self.context.code_style.formatter:
            sections.append(f"- Formatter: {self.context.code_style.formatter}")
        if self.context.code_style.uses_type_hints:
            sections.append("- Uses type hints")

        # Add architecture context
        if self.context.architecture.framework:
            sections.append(f"- Framework: {self.context.architecture.framework}")
        if self.context.architecture.testing_framework:
            sections.append(f"- Testing: {self.context.architecture.testing_framework}")
        if self.context.architecture.design_patterns:
            patterns = ", ".join(self.context.architecture.design_patterns[:3])
            sections.append(f"- Design patterns: {patterns}")

        # Add domain context
        sections.append(f"- Project type: {self.context.domain.project_type}")
        sections.append(f"- Domain: {self.context.domain.domain}")

        # Add historical context if relevant
        if self.context.historical.successful_patterns:
            patterns = ", ".join(self.context.historical.successful_patterns[:3])
            sections.append(f"- Successful patterns: {patterns}")

        # Add additional context
        if additional_context:
            sections.append("\n**Task-Specific Context:**")
            for key, value in additional_context.items():
                sections.append(f"- {key}: {value}")

        return "\n".join(sections)

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

    def set_context(self, context: RepositoryContext):
        """Set or update repository context.

        Args:
            context: Repository context to use for prompt enhancement
        """
        self.context = context
        self.logger.info("prompt_library_context_updated")

    def track_prompt_effectiveness(
        self,
        prompt_id: str,
        success: bool,
        execution_time: float,
        tokens_used: int,
        feedback: Optional[str] = None,
    ):
        """Track effectiveness of a prompt for learning.

        Args:
            prompt_id: Prompt identifier
            success: Whether the prompt led to successful outcome
            execution_time: Time taken to complete task
            tokens_used: Number of tokens used
            feedback: Optional feedback about the prompt
        """
        if prompt_id not in self.prompts:
            return

        if "effectiveness" not in self.prompts[prompt_id]:
            self.prompts[prompt_id]["effectiveness"] = {
                "total_uses": 0,
                "successes": 0,
                "failures": 0,
                "avg_execution_time": 0.0,
                "avg_tokens_used": 0,
                "feedback_log": [],
            }

        stats = self.prompts[prompt_id]["effectiveness"]
        stats["total_uses"] += 1

        if success:
            stats["successes"] += 1
        else:
            stats["failures"] += 1

        # Update running averages
        total = stats["total_uses"]
        stats["avg_execution_time"] = (
            stats["avg_execution_time"] * (total - 1) + execution_time
        ) / total
        stats["avg_tokens_used"] = (
            stats["avg_tokens_used"] * (total - 1) + tokens_used
        ) / total

        # Log feedback
        if feedback:
            stats["feedback_log"].append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "success": success,
                    "feedback": feedback,
                }
            )
            # Keep only last 10 feedback entries
            stats["feedback_log"] = stats["feedback_log"][-10:]

        self._save_prompts()
        self.logger.info(
            "prompt_effectiveness_tracked",
            prompt_id=prompt_id,
            success=success,
            total_uses=stats["total_uses"],
            success_rate=stats["successes"] / total,
        )

    def get_prompt_statistics(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get effectiveness statistics for a prompt.

        Args:
            prompt_id: Prompt identifier

        Returns:
            Dictionary with statistics, or None if not found
        """
        if prompt_id not in self.prompts:
            return None

        if "effectiveness" not in self.prompts[prompt_id]:
            return {
                "total_uses": 0,
                "success_rate": 0.0,
                "avg_execution_time": 0.0,
                "avg_tokens_used": 0,
            }

        stats = self.prompts[prompt_id]["effectiveness"]
        total = stats["total_uses"]
        success_rate = stats["successes"] / total if total > 0 else 0.0

        return {
            "total_uses": total,
            "success_rate": success_rate,
            "successes": stats["successes"],
            "failures": stats["failures"],
            "avg_execution_time": stats["avg_execution_time"],
            "avg_tokens_used": stats["avg_tokens_used"],
            "recent_feedback": stats["feedback_log"][-3:],  # Last 3 feedback entries
        }
