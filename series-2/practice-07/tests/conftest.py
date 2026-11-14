import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeBedrockRuntime:
    """Stands in for boto3's bedrock-runtime client. Counts calls and returns a canned reply."""

    def __init__(self, text="ok", input_tokens=100, output_tokens=20, reasoning_first=False):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.reasoning_first = reasoning_first
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        content = [{"text": self.text}]
        if self.reasoning_first:
            content.insert(0, {"reasoningContent": {"reasoningText": {"text": "thinking..."}}})
        return {
            "output": {"message": {"role": "assistant", "content": content}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": self.input_tokens, "outputTokens": self.output_tokens},
        }
