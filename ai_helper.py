import os
import json
import re
from openai import OpenAI


def generate_flowchart_from_description(task_description):
    """
    Send task description to Amazon Nova AI.
    Get back flowchart structure.
    """
    
    # Get API key from environment variable
    api_key = os.environ.get('NOVA_API_KEY')
    
    # Check if API key exists
    if not api_key:
        raise Exception("NOVA_API_KEY not found. Please set it first.")
    
    # Create OpenAI client pointing to Nova
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.nova.amazon.com/v1"
    )
    
    # Create the prompt for Nova
    prompt = f"""Create a flowchart for this task: {task_description}

Return ONLY a valid JSON object with this exact structure (no extra text):
{{
    "steps": [
        {{
            "id": "step1",
            "type": "start",
            "description": "Start the process",
            "next": ["step2"]
        }},
        {{
            "id": "step2",
            "type": "process",
            "description": "Do something",
            "next": ["step3"]
        }},
        {{
            "id": "step3",
            "type": "end",
            "description": "End the process",
            "next": []
        }}
    ]
}}

Make sure the flowchart makes sense for: {task_description}"""
    
    # Call Nova AI
    response = client.chat.completions.create(
        model="nova-2-lite-v1",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that creates flowcharts. Always respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=2000
    )
    
    # Get the AI's response
    ai_response = response.choices[0].message.content
    
    # Check if response is empty
    if not ai_response or ai_response.strip() == "":
        raise Exception("AI returned empty response")
    
    # Remove markdown code blocks if present
    ai_response = ai_response.strip()
    if ai_response.startswith("```"):
        # Remove ```json or ``` at start and ``` at end
        ai_response = re.sub(r'^```(?:json)?\s*\n', '', ai_response)
        ai_response = re.sub(r'\n```\s*$', '', ai_response)
    
    # Parse JSON
    try:
        flowchart_data = json.loads(ai_response)
    except json.JSONDecodeError as e:
        raise Exception(f"Could not parse JSON: {e}\nResponse: {ai_response[:200]}")
    
    return flowchart_data