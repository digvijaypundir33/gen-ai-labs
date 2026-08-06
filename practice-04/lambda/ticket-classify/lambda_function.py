from typing import Literal

from pydantic import BaseModel
from strands import Agent
from strands.models.bedrock import BedrockModel


class TicketClassification(BaseModel):
    category: Literal["technical", "billing", "feature", "other"]
    urgency: Literal["low", "medium", "high", "critical"]
    reasoning: str


_model = BedrockModel(model_id="amazon.nova-lite-v1:0", region_name="us-east-1")
_agent = Agent(
    model=_model,
    system_prompt=(
        "You are a support ticket triage assistant. Classify the ticket's category "
        "and urgency, and briefly explain why."
    ),
)


def lambda_handler(event, context):
    subject = event.get("subject", "")
    description = event.get("description", "")

    result = _agent(
        f"Subject: {subject}\nDescription: {description}",
        structured_output_model=TicketClassification,
    )
    classification = result.structured_output

    return {
        "category": classification.category,
        "urgency": classification.urgency,
        "reasoning": classification.reasoning,
    }
