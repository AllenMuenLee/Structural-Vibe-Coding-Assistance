import os
import json
import boto3
import re
from openai import OpenAI
from dotenv import load_dotenv
import FileMng
import SymbolExt

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NOVA_SECRET_ACCESS_KEY"),
    base_url="https://api.nova.amazon.com/v1"
)

class CompilerAgent:
    def __init__(self, project_name):
        self.project_name = project_name

    def call_nova(self, data):
        SYSTEM_PROMPT = """
            You are a compiling assitance, you will be provided with the context of the current file, and you will list out commands to run the code.
            RULES:
            1. you will be provided a list import list, please provide in the following format:
                command
                command
                command
                ...
            2. provde a list of commands to install the dependencies.
            3. after, provide a list of commands to run the code.
        """

        prompt = f"""
        CONTEXT OF EXISTING FILES:
        {context}

        TASK: {data['description']}
        FILES TO GENERATE: {data['filenames']}

        Please give the raw code and comment right below the function or class definition, don't put it above
        or ask questions if the code is repeated or not clear context, please don't skip asking question even if the code is short.
        """
        response = client.chat.completions.create(
            model="nova-2-lite-v1",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": prompt
                },
            ],
            temperature=0.1,
            max_tokens=3000,
            stream=False
        )

        print(response.choices[0].message.content)
        
        return response.choices[0].message.content

if __name__ == "__main__":
    project_name = "project_1"
    agent = CodingAgent(project_name)
    filepath = project_name + "/procedure.json"
    procedure = FileMng.get_procedure(filepath)
    agent.generate_by_steps(procedure)
