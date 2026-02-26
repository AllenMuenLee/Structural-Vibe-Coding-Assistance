import os
import json
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def generate_flowchart_from_description(task_description):
    """
    Send task description to Amazon Nova AI.
    Get back flowchart structure.
    """
    
    # Get API key from environment variable
    api_key = os.getenv("NOVA_API_KEY")
    
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
include id, type, description, filenames, files_to_import, and next step for each step.
Return ONLY a valid JSON object with this exact structure (no extra text):
{{
    "framework": "Python, Flask, SQLite",
    "steps": [
        {{
            "id": "step1",
            "type": "start",
            "description": "Start the process",
            "filenames": [],
            "files_to_import": [],
            "next": ["step2"]
        }},
        {{
            "id": "step2",
            "type": "process",
            "description": "Do something",
            "filenames": ["library.py"],
            "files_to_import": [],
            "next": ["step3"]
        }},
        {{
            "id": "step3",
            "type": "process",
            "description": "Do something",
            "filenames": ["example.py"],
            "files_to_import": ["library.py"],
            "next": ["step4"]
        }},
        {{
            "id": "step4",
            "type": "end",
            "description": "End the process",
            "filenames": [],
            "files_to_import": []
            "next": []
        }}
    ]
}}

- "framework": comma-separated list of tools/languages needed for the ENTIRE project
- "filenames": list of files needed for each individual step

Make sure the flowchart makes sense for: {task_description}"""
    
    # Call Nova AI
    response = client.chat.completions.create(
        model="nova-pro-v1",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that creates detailed flowcharts with file information. Always respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=2000
    )
    print(prompt)
    
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
    
    flowchart_data = json.loads(ai_response)
    
    return flowchart_data