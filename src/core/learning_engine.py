"""Main learning engine that orchestrates the learning loop.

Coordinates pattern detection, multi-agent analysis, and improvement application.
"""

from dataclasses import asdict
from typing import Any, Dict, List

from ..integrations.multi_agent_coder_client import MultiAgentCoderClient
from .database import Database
from .logger import AuditLogger
from .multi_agent_learning import MultiAgentLearning
from .pattern_detector import FailurePattern, PatternDetector
from .prompt_library import PromptLibrary


class LearningEngine:
    """Main learning engine that coordinates the learning loop.

    Responsibilities:
    - Detect failure patterns
    - Trigger multi-agent analysis
    - Apply improvements
    - Track learning effectiveness
    - Manage learning cycles
    """

    def __init__(
        self,
        database: Database,
        multi_agent_client: MultiAgentCoderClient,
        prompt_library: PromptLibrary,
        logger: AuditLogger,
        min_pattern_occurrences: int = 3,
        auto_apply_improvements: bool = False,
    ):
        """Initialize learning engine.

        Args:
            database: Database for analytics
            multi_agent_client: Client for multi-agent analysis
            prompt_library: Library for managing prompts
            logger: Audit logger
            min_pattern_occurrences: Minimum failures to trigger learning
            auto_apply_improvements: Whether to automatically apply improvements
        """
        self.database = database
        self.prompt_library = prompt_library
        self.logger = logger
        self.auto_apply = auto_apply_improvements

        # Initialize components
        self.pattern_detector = PatternDetector(
            database=database,
            logger=logger,
            min_occurrences=min_pattern_occurrences,
        )

        self.multi_agent_learning = MultiAgentLearning(
            multi_agent_client=multi_agent_client,
            logger=logger,
        )

        self.learning_history: List[Dict[str, Any]] = []

    def run_learning_cycle(self) -> Dict[str, Any]:
        """Run one complete learning cycle.

        Returns:
            Dictionary with cycle results
        """
        self.logger.info("learning_cycle_started")

        cycle_results = {
            "patterns_detected": 0,
            "patterns_analyzed": 0,
            "improvements_generated": 0,
            "improvements_applied": 0,
            "total_cost": 0.0,
            "total_tokens": 0,
        }

        # Step 1: Detect patterns
        patterns = self.pattern_detector.detect_patterns()
        cycle_results["patterns_detected"] = len(patterns)

        if not patterns:
            self.logger.info("learning_cycle_completed", result="no_patterns_found")
            return cycle_results

        # Step 2: Analyze high-priority patterns
        for pattern in patterns:
            if not self.pattern_detector.should_trigger_learning(pattern):
                continue

            try:
                # Perform root cause analysis
                root_cause = self.multi_agent_learning.analyze_root_cause(pattern)
                cycle_results["total_cost"] += root_cause.cost
                cycle_results["total_tokens"] += root_cause.tokens_used

                # Synthesize learning
                lesson = self.multi_agent_learning.synthesize_learning(
                    pattern, root_cause
                )
                cycle_results["total_cost"] += lesson.cost
                cycle_results["total_tokens"] += lesson.tokens_used

                # Generate improvements
                current_prompts = {
                    "issue_analysis": self.prompt_library.get_prompt("issue_analysis")
                }
                improvements = self.multi_agent_learning.generate_improvements(
                    pattern, lesson, current_prompts
                )
                cycle_results["total_cost"] += improvements.cost
                cycle_results["total_tokens"] += improvements.tokens_used
                cycle_results["improvements_generated"] += 1

                # Apply improvements if auto-apply is enabled
                if self.auto_apply:
                    applied = self._apply_improvements(pattern, improvements)
                    if applied:
                        cycle_results["improvements_applied"] += 1

                # Record in history
                self.learning_history.append(
                    {
                        "pattern_id": pattern.pattern_id,
                        "root_cause": asdict(root_cause),
                        "lesson": asdict(lesson),
                        "improvements": asdict(improvements),
                    }
                )

                cycle_results["patterns_analyzed"] += 1

            except Exception as e:
                self.logger.error(
                    "learning_cycle_error",
                    pattern_id=pattern.pattern_id,
                    error=str(e),
                    exc_info=True,
                )

        self.logger.info(
            "learning_cycle_completed",
            patterns_analyzed=cycle_results["patterns_analyzed"],
            improvements_generated=cycle_results["improvements_generated"],
            total_cost=cycle_results["total_cost"],
        )

        return cycle_results

    def _apply_improvements(self, pattern: FailurePattern, improvements: Any) -> bool:
        """Apply improvements from learning.

        Args:
            pattern: Pattern that triggered learning
            improvements: Generated improvements

        Returns:
            True if successfully applied
        """
        try:
            # Apply prompt improvements
            for prompt_id, new_prompt in improvements.prompt_improvements.items():
                self.prompt_library.update_prompt(
                    prompt_id=prompt_id,
                    new_template=new_prompt,
                    improvement_reason=f"Learning from pattern {pattern.pattern_id}",
                )

            self.logger.info(
                "improvements_applied",
                pattern_id=pattern.pattern_id,
                prompt_updates=len(improvements.prompt_improvements),
            )
            return True

        except Exception as e:
            self.logger.error(
                "improvement_application_failed",
                pattern_id=pattern.pattern_id,
                error=str(e),
            )
            return False

    def get_patterns_summary(self) -> Dict[str, Any]:
        """Get summary of current failure patterns.

        Returns:
            Dictionary with pattern statistics
        """
        patterns = self.pattern_detector.detect_patterns()

        by_severity = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for pattern in patterns:
            by_severity[pattern.severity] += 1

        return {
            "total_patterns": len(patterns),
            "by_severity": by_severity,
            "patterns_needing_attention": sum(
                1 for p in patterns if self.pattern_detector.should_trigger_learning(p)
            ),
        }

    def get_learning_history(self) -> List[Dict[str, Any]]:
        """Get history of learning cycles.

        Returns:
            List of learning records
        """
        return self.learning_history
