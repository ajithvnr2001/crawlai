from openai import OpenAI
import json

client = OpenAI(
  base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
  api_key=os.getenv("NVIDIA_API_KEY")
)

def test_extraction():
    url = "https://forum.rclone.org/t/error-when-multiple-instances-of-rclone-running-all-with-the-rc-flag/25856/7"
    prompt = f"Extract technical documentation from {url} into a JSON object with 'title', 'content' (markdown), and 'code_snippets'.\n\nHTML:\n<html><body><h1>Sample</h1></body></html>"
    
    print("Testing NVIDIA with Direct OpenAI Client (Non-Streaming)...")
    try:
        completion = client.chat.completions.create(
            model="stepfun-ai/step-3.5-flash",
            messages=[{"role":"user","content":prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        print("Success!")
        print(f"Raw Content: {completion.choices[0].message.content}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_extraction()
