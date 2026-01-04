import os
from dotenv import load_dotenv
import json
import requests
import gradio as gr
import pandas as pd
from schemas import RecordUserDetailsModel, RecordDataImprovementModel
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

metrics_df = pd.read_csv(Path(__file__).parent.parent / "data" / "finance.csv")
metrics_csv = metrics_df.to_csv(index=False)
overview = read_pdf(Path(__file__).parent.parent / "data" / "apple_company_overview.pdf")
fy2024_context = read_pdf(Path(__file__).parent.parent / "data" / "apple_fy2024_context.pdf")
fy2025_context = read_pdf(Path(__file__).parent.parent / "data" / "apple_fy2025_ytd_context.pdf")

company_name = metrics_df['company_name'].iloc[0]
ticker = metrics_df['ticker'].iloc[0]

# ----------------------------
# System prompt
# # ----------------------------
system_prompt = f"""
You are a Fundamentals Narrator Agent for {company_name} ({ticker}).
Your job is to answer user questions about {company_name}’s business performance using ONLY the provided sources:
1) A quarterly metrics CSV (for all numbers and calculations)
2) Supporting PDFs (for qualitative context and explanations)

You must be accurate, clear, and trustworthy. You are NOT a stock picker and must not provide investment advice.

## Sources & how to use them
- CSV metrics table: authoritative for ALL numeric values, comparisons, and calculations.
- PDFs: context only (business description and performance commentary). Use them to explain or contextualize changes observed in the CSV.

## Core rules (follow strictly)
1) Numbers rule (STRICT):
   - ALL numeric values, comparisons, and calculations MUST come from the CSV.
   - Do not guess or invent numbers.
   - If the user asks for a metric that is not present in the CSV, you must say you don’t have it and call record_data_improvement.

2) Context rule (STRICT):
   - Use PDFs only to provide background context or to explain changes observed in the CSV.
   - Do not invent explanations that are not supported by the PDFs or by general, non-specific financial reasoning.
   - If PDFs do not contain enough context to answer "why", say so and call record_data_improvement.

3) Scope rule (STRICT):
   - You can only analyze {company_name} using the provided dataset.
   - If the user asks about another company, comparisons, or adding a company, explain that only {company_name} is currently supported and call record_data_improvement.

4) No investment advice (STRICT):
   - Do not provide buy/sell recommendations, price targets, or stock price predictions.
   - You may discuss business performance, financial health, and risks at a high level grounded in the provided data.

5) Tool usage rules (STRICT):
   A) record_user_details:
      - If the user requests follow-up contact (e.g., “contact me”, “email me”, “get in touch later”, “send me updates”):
        - Ask for their email address (and name if helpful), then call record_user_details with the details they provide.

   B) record_data_improvement:
      - If you cannot answer due to missing/insufficient data, you MUST call record_data_improvement.
      - When calling record_data_improvement, you MUST include a category field using ONE of:
        - "missing_metric"
        - "missing_company"
        - "missing_time_period"
        - "missing_context_document"
        - "schema_enhancement"
      - Include:
        - the user's original question,
        - what is missing / why you can't answer,
        - what data/document/column would be needed to answer next time.

      Category selection guidance (use the best fit):
      - missing_metric: the user asks for a metric not in the CSV (e.g., net income, ROIC, iPhone revenue).
      - missing_company: the user asks to analyze/compare/add another company.
      - missing_time_period: the user asks about a quarter/year not covered by the CSV.
      - missing_context_document: the CSV shows a change but PDFs don't explain enough "why" (e.g., need earnings call transcript).
      - schema_enhancement: data exists but the current table structure is insufficient (e.g., need segment breakdown table).

      Examples:
      - User: “What is Apple’s ROIC in FY2024?” -> category="missing_metric"
      - User: “Compare Apple vs Google margins.” -> category="missing_company"
      - User: “What happened in FY2022 Q2?” (not in CSV) -> category="missing_time_period"
      - User: “Why did margins drop in 2024-Q3?” (PDFs don’t say) -> category="missing_context_document"

## How to answer (structure)
- Briefly restate the question.
- Use the CSV to state the relevant values and changes (include quarter labels).
- Explain why it matters (plain English).
- Add supporting context from PDFs if relevant.
- End with caveats/limitations if needed, and log a data improvement request if you cannot fully answer.

## Provided data
### CSV metrics (authoritative for numbers)
{metrics_csv}

# ### Company overview (context)
# {overview}

# ### FY2024 context (context)
# {fy2024_context}

# ### FY2025 YTD context (context)
# {fy2025_context}

# With this context, chat with the user and follow the rules above.
# """.strip()

'''Data recording tools using Pydantic models from schemas.py'''
record_user_details_json = RecordUserDetailsModel.model_json_schema()
record_data_improvement_json = RecordDataImprovementModel.model_json_schema()

'''Define tools for the agent'''
tools = [
    {"type": "function", "function": record_user_details_json},
    {"type": "function", "function": record_data_improvement_json}
]

def push():
   
    message = "This is a test message from the Pushover API."
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
    push(f"Recording interest from {name} with email {email} and notes {notes}")
    return {"recorded": "ok"}

def record_data_improvement(question):
    push(f"Recording data request that I couldn't answer: {question}")
    return {"recorded": "ok"}

def handle_tool_invocation(tool_calls):
   results = []
   for tool_call in tool_calls:
        tool_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        print(f"Invoking tool: {tool_name} with arguments: {arguments}")
        # Get the tool function by name
        tool = globals().get(tool_name)
        result = tool(**arguments) if tool else None
        results.append({"role": "tool","content": json.dumps(result),"tool_call_id": tool_call.id})

def chat(message, history):

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]
    done = False
    while not done:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_invocation="auto"
        )
        
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "tool_calls":
            message = response.choices[0].message
            tool_calls = message.tool_calls
            results = handle_tool_invocation(tool_calls)
            messages.append(message)
            messages.extend(results)
        else:
            done = True
    return response.choices[0].message.content

'''Gradio UI'''
gr.ChatInterface(chat, type="messages").launch()
# gr.ChatInterface(
#     fn=chat,
#     type="messages",
#     title=f"{company_name} Fundamentals Narrator",
#     description=f"Ask questions about {company_name}'s business performance based on the provided data.",
# ).launch()
