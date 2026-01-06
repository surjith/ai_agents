import os
import gradio as gr

# Import your agent from the agents package
from agents.agent import FundamentalsAgent

# Optional: ensure relative paths resolve from repo root
ROOT_DIR = os.path.dirname(__file__)
os.chdir(ROOT_DIR)

agent = FundamentalsAgent()

# Set the initial welcome message
initial_history = [{"role": "assistant", "content": f"Welcome 👋! I am a company fundamentals narrator for {agent.company_name}. How can I help you today?"}]

demo = gr.ChatInterface(
    fn=agent.chat,
    title=f"{agent.company_name} Fundamentals Narrator",
    description=f"Ask questions about {agent.company_name}'s business performance based on the provided data.",
    chatbot=gr.Chatbot(value=initial_history, height="auto")
).launch()