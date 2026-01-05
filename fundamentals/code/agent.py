import os
from dotenv import load_dotenv
import json
import requests
import gradio as gr
import pandas as pd
from schemas import RecordUserDetailsModel, RecordDataImprovementModel
from system_prompt import SystemPrompt
from pathlib import Path
from PyPDF2 import PdfReader
from openai import OpenAI


"""Initialize environment variables and API clients."""
load_dotenv(override=True)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pushover_user_key = os.getenv("PUSHOVER_USER")
pushover_app_token = os.getenv("PUSHOVER_TOKEN")
pushover_url = "https://api.pushover.net/1/messages.json"

'''Loading data'''

def read_pdf(path: str) -> str:
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"
    return text.strip()


'''Data recording tools using Pydantic models from schemas.py'''
record_user_details_json = RecordUserDetailsModel.model_json_schema()
record_data_improvement_json = RecordDataImprovementModel.model_json_schema()

'''Define tools for the agent (OpenAI function/tool format)'''
# Each function entry must include a `name`, `description`, and `parameters` (JSON Schema).
# We reuse the Pydantic-generated JSON schema as the `parameters` value.
tools = [
    {
        "type": "function",
        "function": {
            "name": "record_user_details",
            "description": "Record a user's contact details (email, name, notes) for follow-up.",
            "parameters": record_user_details_json,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_data_improvement",
            "description": "Record a request for missing or improved data, including a category.",
            "parameters": record_data_improvement_json,
        },
    },
]

def push(message: str = "This is a test message from the Pushover API."):
    """Send a message via Pushover (defaults to a test message)."""
    data = {
        "user": pushover_user_key,
        "token": pushover_app_token,
        "message": message,
    }

    response = requests.post(pushover_url, data=data)

    if response.status_code == 200:
        print("Message sent successfully!")
    else:
        print(f"Failed to send message. Status code: {response.status_code}")
        print(f"Response: {response.text}")


def record_user_details(email, name="Name not provided", notes="No notes"):
    try:        
        validated = RecordUserDetailsModel.model_validate({"email": email, "name": name, "notes": notes})        
    except Exception as e:
        return {"error": f"Invalid input: {e}"}
    
    data = validated.model_dump()
    msg = f"Recording interest from {data['name']} with email {data['email']} and notes {data['notes']}"
    push(msg)
    return {"recorded": "ok", "data": data}

def record_data_improvement(question, category=None, details=None):
    msg = f"Recording data request that I couldn't answer: {question}"
    if category:
        msg += f" | category: {category}"
    if details:
        msg += f" | details: {details}"
    push(msg)
    return {"recorded": "ok"}


def handle_tool_invocation(tool_calls):
    """Execute model-requested tool calls and return tool output messages to append to the conversation."""
    results = []
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments)
        except Exception as e:
            print(f"Failed to parse tool arguments for {tool_name}: {e}")
            arguments = {}

        print(f"Invoking tool: {tool_name} with arguments: {arguments}")
        tool = globals().get(tool_name)
        try:
            result = tool(**arguments) if tool else {"error": "tool not found"}
        except Exception as e:
            result = {"error": str(e)}

        # Represent tool output as a message the model can see
        results.append({"role": "tool","content": json.dumps(result),"tool_call_id": tool_call.id})

    return results

class FundamentalsAgent:
    def __init__(self):
        self.system_prompt_builder = SystemPrompt()
        metrics_df = pd.read_csv(Path(__file__).parent.parent / "data" / "finance.csv")
        self.company_name = metrics_df['company_name'].iloc[0]
        self.ticker = metrics_df['ticker'].iloc[0]

        metrics_csv = metrics_df.to_csv(index=False)
        overview = read_pdf(Path(__file__).parent.parent / "data" / "apple_company_overview.pdf")
        fy2024_context = read_pdf(Path(__file__).parent.parent / "data" / "apple_fy2024_context.pdf")
        fy2025_context = read_pdf(Path(__file__).parent.parent / "data" / "apple_fy2025_ytd_context.pdf")
        
        self.system_prompt = self.system_prompt_builder.BuildSystemPrompt(
            company_name=self.company_name,
            ticker=self.ticker,
            metrics_csv=metrics_csv,
            overview=overview,
            fy2024_context=fy2024_context,
            fy2025_context=fy2025_context,
        )

    def chat(self, message, history):

        messages = [{"role": "system", "content": self.system_prompt}] + history + [{"role": "user", "content": message}]
        done = False
        final_content = None
        while not done:        
            response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                tools=tools
            )        
            finish_reason = response.choices[0].finish_reason
            if finish_reason == "tool_calls":
                message = response.choices[0].message
                # Add the assistant's message (may be empty when it triggers tool calls)
                # assistant_message = {"role": "assistant", "content": msg_obj.content or ""}
                tool_calls = message.tool_calls
                results = handle_tool_invocation(tool_calls)
                messages.append(message)
                messages.extend(results)
            else:
                done = True

        return response.choices[0].message.content

if __name__ == "__main__":
    agent = FundamentalsAgent()  
    '''Gradio UI'''
    gr.ChatInterface(fn=agent.chat, title=f"{agent.company_name} Fundamentals Narrator", description=f"Ask questions about {agent.company_name}'s business performance based on the provided data.").launch()
