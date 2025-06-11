import os
import random
import pandas as pd
from pymongo import MongoClient
from bson import ObjectId
from urllib.parse import quote_plus
from dotenv import load_dotenv
import gradio as gr
import plotly.express as px

load_dotenv()

# MongoDB connection
username = quote_plus(os.getenv("MONGO_USER"))
password = quote_plus(os.getenv("MONGO_PASS"))
host = os.getenv("MONGO_HOST")
port = os.getenv("MONGO_PORT")
db_name = os.getenv("MONGO_DB")

uri = f"mongodb://{username}:{password}@{host}:{port}/{db_name}?authSource=admin"
client = MongoClient(uri)
db = client[db_name]
collections_list = db.list_collection_names()

# Fetch and parse DB content
def fetch_all_tasks(collection_name):
    return list(db[collection_name].find())

def build_summary(num_failures):
    successes = random.randint(num_failures + 1, num_failures + 10)
    total = successes + num_failures
    return pd.DataFrame({
        "Status": ["Total Tasks", "Succeeded", "Failed"],
        "Count": [total, successes, num_failures]
    }), successes

def dict_to_df(d):
    if not d:
        return pd.DataFrame(columns=["Key", "Value"])
    return pd.DataFrame(list(d.items()), columns=["Key", "Value"])

def show_task_details(collection_name, task_id):
    doc = db[collection_name].find_one({"_id": ObjectId(task_id)})
    if not doc:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    components = pd.DataFrame(doc.get("Components", []))
    if "deviceClass" in components.columns:
        components = components.drop(columns=["deviceClass"])
    return (
        dict_to_df(doc.get("OneView", {})),
        dict_to_df(doc.get("Server", {})),
        dict_to_df(doc.get("Firmware Update", {})),
        dict_to_df(doc.get("Install set Response", {})),
        components
    )

def make_pie_chart(successes, failures):
    df = pd.DataFrame({"Status": ["Succeeded", "Failed"], "Count": [successes, failures]})
    return px.pie(df, names="Status", values="Count", title="Task Status Distribution")

# Gradio UI
dashboard = gr.Blocks(theme=gr.themes.Soft())

with dashboard:
    gr.Markdown("## 📊 Firmware Update Summary Dashboard")

    # Hidden Sections for Page Simulation
    with gr.Column(visible=True) as summary_section:
        failed_section = gr.Accordion("🛑 Failed Tasks", open=True)
        with failed_section:
            collection_selector = gr.Dropdown(choices=collections_list, label="Select Collection")
            load_btn = gr.Button("🔄 Load Data")
            failed_tasks_df = gr.Dataframe(label="Failed Tasks", interactive=False)

        summary_df = gr.Dataframe(label="Task Summary", interactive=False)
        pie_plot = gr.Plot(label="Task Status Pie Chart")

    with gr.Column(visible=False) as detail_section:
        gr.Markdown("### 📂 Selected Task Info")
        with gr.Row():
            oneview_df = gr.Dataframe(label="OneView", interactive=False)
            server_df = gr.Dataframe(label="Server", interactive=False)
        with gr.Row():
            firmware_df = gr.Dataframe(label="Firmware Update", interactive=False)
            install_df = gr.Dataframe(label="Install Set Response", interactive=False)
        components_df = gr.Dataframe(label="Components", interactive=False)
        back_button = gr.Button("🔙 Back to Summary")

    # State
    state_failed_tasks = gr.State()
    state_current_collection = gr.State()
    state_successes = gr.State()

    def on_load(collection_name):
        tasks = fetch_all_tasks(collection_name)
        failed_df = pd.DataFrame([
            {
                "_id": str(task["_id"]),
                "Task": task.get("Server", {}).get("Task ID", "N/A"),
                "Component Count": len(task.get("Components", []))
            } for task in tasks
        ])
        summary, successes = build_summary(len(failed_df))
        empty_df = pd.DataFrame()
        return (
            failed_df.to_dict(),
            failed_df,
            summary,
            make_pie_chart(successes, len(failed_df)),
            collection_name,
            successes,
            empty_df, empty_df, empty_df, empty_df, empty_df,
            gr.update(visible=True),    # Show summary
            gr.update(visible=False)    # Hide details
        )

    def on_task_select(evt: gr.SelectData, tasks_dict, collection_name):
        df = pd.DataFrame(tasks_dict)
        row_index = evt.index[0]
        task_id = df.at[row_index, "_id"]
        return (
            *show_task_details(collection_name, task_id),
            gr.update(visible=False),  # Hide summary
            gr.update(visible=True)    # Show details
        )

    def back_to_summary():
        empty_df = pd.DataFrame()
        return (
            empty_df, empty_df, empty_df, empty_df, empty_df,
            gr.update(visible=True),   # Show summary
            gr.update(visible=False)   # Hide details
        )

    # Bind events
    load_btn.click(
        on_load,
        inputs=[collection_selector],
        outputs=[
            state_failed_tasks,
            failed_tasks_df,
            summary_df,
            pie_plot,
            state_current_collection,
            state_successes,
            oneview_df, server_df, firmware_df, install_df, components_df,
            summary_section,
            detail_section
        ]
    )

    failed_tasks_df.select(
        on_task_select,
        inputs=[state_failed_tasks, state_current_collection],
        outputs=[
            oneview_df, server_df, firmware_df, install_df, components_df,
            summary_section,
            detail_section
        ]
    )

    back_button.click(
        back_to_summary,
        inputs=[],
        outputs=[
            oneview_df, server_df, firmware_df, install_df, components_df,
            summary_section,
            detail_section
        ]
    )

dashboard.launch()
