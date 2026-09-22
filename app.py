import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bloomberg_monitor.app import app as flask_app

# Try importing Gradio to mount on Hugging Face Spaces (free tier without credit card)
try:
    import gradio as gr
    from starlette.middleware.wsgi import WSGIMiddleware

    # Create empty blocks and mount Flask app on Starlette/FastAPI
    with gr.Blocks(title="Bloomberg China News Intelligence") as demo:
        gr.HTML("""
        <style>
            body, html { margin: 0; padding: 0; height: 100%; overflow: hidden; }
            iframe { width: 100vw; height: 100vh; border: none; }
        </style>
        <iframe src="/app/"></iframe>
        """)

    # Mount Flask under /app/
    demo.app.mount("/app", WSGIMiddleware(flask_app))
    # Also mount static assets
    demo.app.mount("/static", WSGIMiddleware(flask_app))
    demo.app.mount("/api", WSGIMiddleware(flask_app))

    if __name__ == "__main__":
        demo.launch(server_name="0.0.0.0", server_port=7860)

except ImportError:
    # Fallback to standard Flask launcher
    if __name__ == "__main__":
        port = int(os.environ.get("PORT", 7860))
        flask_app.run(host="0.0.0.0", port=port)
