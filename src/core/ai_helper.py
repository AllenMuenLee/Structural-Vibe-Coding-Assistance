import os
import json
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def generate_flowchart_from_description(task_description, project_name):
    """
    Send task description to Amazon Nova AI.
    Get back flowchart structure.
    """
    print("start")
    # Get API key from environment variable
    api_key = os.getenv("NOVA_API_KEY")
    
    # Check if API key exists
    if not api_key:
        raise Exception("NOVA_API_KEY not found. Please set it first.")
    
    # Create OpenAI client pointing to Nova
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.nova.amazon.com/v1",
        default_headers={"Accept-Encoding": "gzip, deflate"},  # Disable zstd
        timeout=90.0
    )
    
    # Create the prompt for Nova
    prompt = f"""Create a software structure for this task: {task_description}
    Each node should describe one and only one function in detail.
    The software structure should be tree like.
    One parent a node, there can be multiple root nodes.
    Don't run application in any node.
    Please create files only when necessary. Slightly larger file is fine, but still separate the functionality if needed.
    Tree Structure can have multiple layers and multiple nodes under each node.
    Tree Structure should be as detail as possible pls idiot (create as many nodes as possible that describe all functionalities pls)
    You must create a main file with a valid main method otherwise cannot run the program (main, index.html, or other commonly seen file name for the running file), pls check this always, even if the description doesnt explicitly says to do so
    
    Return ONLY a valid JSON object with this exact structure (no extra text), like this example (this is just an example):
    {{
        "framework": "Any framework that's applicable",
        "nodes": [
            {{
                "id": "initialize project",
                "description": "install dependencies",
                "filenames": [],
                "files_to_import": [],
                "command": ["initialize the project"],
                "children": []
            }},
            {{
                "id": "function 1",
                "description": "function1 does this",
                "filenames": ["file1.extension"],
                "files_to_import": [],
                "command": [],
                "parent": ["integrate project"],
                "children": []
            }},
            {{
                "id": "function 2",
                "description": "function2 does this",
                "filenames": ["file1.extension"],
                "files_to_import": [],
                "command": ["install an api"],
                "parent": ["integrate project"],
                "children": []
            }},
            {{
                "id": "function 3",
                "description": "function 3 does this",
                "filenames": ["example.extension"],
                "files_to_import": ["file1.extension"],
                "command": [],
                "parent": ["integrate project"],
                "children": []
            }},
            {{
                "id": "integrate project",
                "description": "Integrate function 1, function 2, and function 3",
                "filenames": ["file1.extension"],
                "files_to_import": [],
                "command": [],
                "children": ["function 1", "function 2", "function 3"]
            }}
        ]
    }}
    The example shows a tree of depth 2, add more depth if necessary.
    - "framework": comma-separated list of tools/languages needed for the ENTIRE project
    - "filenames": list of files needed for each individual node"""

    system_prompt = f"""You are a helpful assistant that creates detailed software structure tree with file information. Always respond with valid JSON only.
    For each node you create, the must follow this rule:
    1. list a list of commands to for installing library or set up enviroment.
    2. You must perform all project initialization directly within the root directry. Initialization commands should use parameters like --yes to skip all of the buliding process.
    3. NO cd, mkdir, rmdir commands (avoid all commands that create, delete, or modify a filepath or name)
    4. 1 function per node, but different node can work on the same files, so that a single files can contain multiple functions, but not necessary, and remember each file serve with purposes. If two files have similar functionalities, they can be in the same file, otherwise dont.
    5. Each node describe the function to implement in detail.
    6. Review the structure, make sure it efficiently use each file's existing functions if created previously.
    9. The strucutre should be tree like, usually the file that integrates each functions is the parent node, with each functions as its child node.
    10. Don't run the application in any node.
    11. You must create a main file with a valid main method otherwise cannot run the program (main, index.html, or other commonly seen file name for the running file), pls check this always, even if the description doesnt explicitly says to do so
    12. in each descriptions, be clear about what the file's role is in the project, and how is it gonna work with other files, functions, or classes.
    """
    
    # Call Nova AI
    response = client.chat.completions.create(
        model="nova-pro-v1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=1500
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


def generate_flowchart_edit_from_description(task_description, existing_flowchart):
    """
    Update an existing flowchart based on the user's description.
    Returns a full updated flowchart JSON object.
    """
    api_key = os.getenv("NOVA_API_KEY")
    if not api_key:
        raise Exception("NOVA_API_KEY not found. Please set it first.")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.nova.amazon.com/v1",
        default_headers={"Accept-Encoding": "gzip, deflate"},
        timeout=90.0
    )

    existing_json = json.dumps(existing_flowchart or {}, indent=2)
    prompt = f"""
    USER REQUEST:
    {task_description}

    EXISTING FLOWCHART JSON:
    {existing_json}

    Update the flowchart according to the user's request.
    - Preserve existing node IDs when possible.
    - Only modify what is necessary to satisfy the request.
    - Return ONLY a valid JSON object (no extra text).
    - Keep the same structure as the existing flowchart.
    """

    system_prompt = (
        "You are a helpful assistant that edits software flowcharts. "
        "Return valid JSON only."
    )

    response = client.chat.completions.create(
        model="nova-pro-v1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4,
        max_tokens=2000
    )

    ai_response = (response.choices[0].message.content or "").strip()
    if not ai_response:
        raise Exception("AI returned empty response")

    if ai_response.startswith("```"):
        ai_response = re.sub(r'^```(?:json)?\s*\n', '', ai_response)
        ai_response = re.sub(r'\n```\s*$', '', ai_response)

    return json.loads(ai_response)
