"""DeepEval custom judge backed by Bedrock Converse (spike V-7: uses the ambient credentials, no special profile needed here)."""
import json, re
import boto3
from deepeval.models import DeepEvalBaseLLM

JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"


class BedrockJudge(DeepEvalBaseLLM):
    def __init__(self, model_id=JUDGE_MODEL, region="us-west-2"):
        self.model_id = model_id
        self.client = boto3.client("bedrock-runtime", region_name=region)

    def load_model(self):
        return self.client

    def generate(self, prompt: str, schema=None):
        r = self.client.converse(modelId=self.model_id, messages=[{"role": "user", "content": [{"text": prompt}]}],
                                 inferenceConfig={"maxTokens": 1500, "temperature": 0})
        text = r["output"]["message"]["content"][0]["text"]
        if schema is None:
            return text
        m = re.search(r"\{.*\}", text, re.S)
        return schema(**json.loads(m.group(0)))

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)

    def get_model_name(self):
        return f"bedrock:{self.model_id}"
