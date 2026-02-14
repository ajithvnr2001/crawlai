from openai import OpenAI
import json

client = OpenAI(
  base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
  api_key=os.getenv("NVIDIA_API_KEY")
)

completion = client.chat.completions.create(
  model="stepfun-ai/step-3.5-flash",
  messages=[{"role":"user","content":"how are you"}],
  temperature=1,
  top_p=0.9,
  max_tokens=16384,
  stream=True
)


for chunk in completion:
  if not getattr(chunk, "choices", None):
    continue
  reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
  if reasoning:
    print(reasoning, end="")
  if chunk.choices[0].delta.content:
    print(chunk.choices[0].delta.content, end="")

