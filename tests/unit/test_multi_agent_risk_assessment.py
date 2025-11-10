"""Unit tests for multi-agent risk assessment."""

import unittest
from unittest.mock import MagicMock, Mock

from src.core.logger import AuditLogger
from src.integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentResponse,
)
from src.safety.guards import Operation, OperationType, RiskLevel
from src.safety.multi_agent_risk_assessor import MultiAgentRiskAssessor, RiskAssessment


class TestMultiAgentRiskAssessor(unittest.TestCase):
    """Test cases for MultiAgentRiskAssessor."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)
        self.assessor = MultiAgentRiskAssessor(
            multi_agent_client=self.multi_agent_client,
            logger=self.logger,
        )

    def test_initialization(self):
        """Test assessor initialization."""
        self.assertIsNotNone(self.assessor.multi_agent_client)
        self.assertIsNotNone(self.assessor.logger)

    def test_assess_operation_success(self):
        """Test successful operation assessment."""
        operation = Operation(
            operation_type=OperationType.FILE_DELETION,
            description="Delete temporary files",
            files=["temp1.txt", "temp2.txt"],
        )

        # Mock multi-agent response
        mock_response = MultiAgentResponse(
            providers=["anthropic", "openai"],
            responses={
                "anthropic": "Risk Level: LOW\nThis is a safe operation.",
                "openai": "Risk Level: LOW\nMinimal risk detected.",
            },
            strategy="all",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )
        self.multi_agent_client.query.return_value = mock_response

        assessment = self.assessor.assess_operation(operation)

        # Should return LOW risk with consensus
        self.assertEqual(assessment.risk_level, RiskLevel.LOW)
        self.assertGreater(assessment.consensus_strength, 0.5)
        self.assertIsNotNone(assessment.rationale)

    def test_assess_operation_high_risk(self):
        """Test assessment of high-risk operation."""
        operation = Operation(
            operation_type=OperationType.PROTECTED_FILE_ACCESS,
            description="Modify production config",
            files=["config/production/database.yaml"],
        )

        # Mock high-risk response
        mock_response = MultiAgentResponse(
            providers=["anthropic", "openai"],
            responses={
                "anthropic": "Risk Level: HIGH\nModifying production config is risky.",
                "openai": "Risk Level: HIGH\nHigh risk of production outage.",
            },
            strategy="all",
            total_tokens=1500,
            total_cost=0.02,
            success=True,
        )
        self.multi_agent_client.query.return_value = mock_response

        assessment = self.assessor.assess_operation(operation)

        # Should return HIGH risk (or CRITICAL due to safety-first if "dangerous" detected)
        # Safety-first approach may elevate to CRITICAL
        self.assertIn(assessment.risk_level, [RiskLevel.HIGH, RiskLevel.CRITICAL])

    def test_assess_operation_failure(self):
        """Test assessment when multi-agent query fails."""
        operation = Operation(
            operation_type=OperationType.FILE_MODIFICATION,
            description="Update code",
            files=["src/app.py"],
        )

        # Mock failed response
        mock_response = MultiAgentResponse(
            providers=[],
            responses={},
            strategy="all",
            total_tokens=0,
            total_cost=0.0,
            success=False,
            error="Timeout",
        )
        self.multi_agent_client.query.return_value = mock_response

        assessment = self.assessor.assess_operation(operation)

        # Should default to CRITICAL on failure (safety-first)
        self.assertEqual(assessment.risk_level, RiskLevel.CRITICAL)
        self.assertIn("failed", assessment.rationale.lower())

    def test_extract_risk_level_critical(self):
        """Test extracting CRITICAL risk level."""
        text = "This operation is CRITICAL and very dangerous!"
        risk = self.assessor._extract_risk_level(text)
        self.assertEqual(risk, "CRITICAL")

    def test_extract_risk_level_high(self):
        """Test extracting HIGH risk level."""
        text = "This has HIGH RISK potential"
        risk = self.assessor._extract_risk_level(text)
        self.assertEqual(risk, "HIGH")

    def test_extract_risk_level_medium(self):
        """Test extracting MEDIUM risk level."""
        text = "MEDIUM risk level detected"
        risk = self.assessor._extract_risk_level(text)
        self.assertEqual(risk, "MEDIUM")

    def test_extract_risk_level_low(self):
        """Test extracting LOW risk level (default)."""
        text = "This looks safe"
        risk = self.assessor._extract_risk_level(text)
        self.assertEqual(risk, "LOW")

    def test_build_consensus_unanimous(self):
        """Test building consensus when all providers agree."""
        votes = {
            "anthropic": "HIGH",
            "openai": "HIGH",
            "deepseek": "HIGH",
        }

        consensus = self.assessor._build_consensus(votes)

        self.assertEqual(consensus["level"], RiskLevel.HIGH)
        self.assertEqual(consensus["consensus_strength"], 1.0)
        self.assertTrue(consensus["unanimous"])

    def test_build_consensus_split(self):
        """Test building consensus with split votes."""
        votes = {
            "anthropic": "HIGH",
            "openai": "MEDIUM",
            "deepseek": "LOW",
        }

        consensus = self.assessor._build_consensus(votes)

        # Should use most conservative (HIGH)
        self.assertEqual(consensus["level"], RiskLevel.HIGH)
        self.assertLess(consensus["consensus_strength"], 1.0)
        self.assertFalse(consensus["unanimous"])

    def test_build_consensus_safety_first(self):
        """Test that consensus uses safety-first approach."""
        votes = {
            "anthropic": "LOW",
            "openai": "LOW",
            "deepseek": "CRITICAL",  # One provider says critical
        }

        consensus = self.assessor._build_consensus(votes)

        # Should be CRITICAL (most conservative)
        self.assertEqual(consensus["level"], RiskLevel.CRITICAL)

    def test_extract_impacts(self):
        """Test extracting potential impacts from responses."""
        mock_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """
Potential Impacts:
- Data loss possible
- Service downtime
- User disruption
                """
            },
            strategy="all",
            total_tokens=100,
            total_cost=0.001,
            success=True,
        )

        impacts = self.assessor._extract_impacts(mock_response)

        # Should extract impact items
        self.assertGreater(len(impacts), 0)

    def test_risk_assessment_to_dict(self):
        """Test RiskAssessment to_dict conversion."""
        operation = Operation(
            operation_type=OperationType.FILE_DELETION,
            description="Test",
            files=["test.py"],
        )

        assessment = RiskAssessment(
            operation=operation,
            risk_level=RiskLevel.MEDIUM,
            consensus_strength=0.66,
            provider_votes={"anthropic": "MEDIUM"},
            rationale="Test rationale",
        )

        assessment_dict = assessment.to_dict()

        self.assertEqual(assessment_dict["risk_level"], "medium")
        self.assertEqual(assessment_dict["consensus_strength"], 0.66)
        self.assertIn("operation", assessment_dict)


if __name__ == "__main__":
    unittest.main()
