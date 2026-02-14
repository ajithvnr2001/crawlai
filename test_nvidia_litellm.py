import asyncio
import litellm
import time

NVIDIA_CONFIG = {
    "api_key": os.getenv("NVIDIA_API_KEY"),
    "base_url": os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    "model": os.getenv("NVIDIA_MODEL", "openai/stepfun-ai/step-3.5-flash") 
}

async def test_extraction():
    url = "https://forum.rclone.org/t/error-when-multiple-instances-of-rclone-running-all-with-the-rc-flag/25856/7"
    html_sample = "<html><body><h1>Sample Rclone Topic</h1><p>I am having trouble with multiple instances.</p></body></html>"
    
    prompt = f"""Extract core technical documentation from this page: {url}
    Provide a JSON object with:
    - title: Page title
    - content: Main technical content in markdown
    - code_snippets: List of any rclone commands or configs found
    
    HTML Content:
    {html_sample}
    """
    
    print(f"Testing Model: {NVIDIA_CONFIG['model']}")
    print(f"Base URL: {NVIDIA_CONFIG['base_url']}")
    
    try:
        # Test 1: With openai/ prefix
        print("\n--- Test 1: With 'openai/' prefix ---")
        response = await litellm.acompletion(
            model=NVIDIA_CONFIG["model"],
            messages=[{"role": "user", "content": prompt}],
            api_key=NVIDIA_CONFIG["api_key"],
            base_url=NVIDIA_CONFIG["base_url"],
            temperature=0.1
        )
        print("Success!")
        print(f"Content: {response.choices[0].message.content[:100]}...")
    except Exception as e:
        print(f"Test 1 Failed: {e}")

    try:
        # Test 2: Without openai/ prefix (direct model name)
        print("\n--- Test 2: Without prefix, with custom_llm_provider='openai' ---")
        response = await litellm.acompletion(
            model="stepfun-ai/step-3.5-flash",
            messages=[{"role": "user", "content": prompt}],
            api_key=NVIDIA_CONFIG["api_key"],
            base_url=NVIDIA_CONFIG["base_url"],
            custom_llm_provider="openai",
            temperature=0.1
        )
        print("Success!")
        print(f"Content: {response.choices[0].message.content[:100]}...")
    except Exception as e:
        print(f"Test 2 Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_extraction())
