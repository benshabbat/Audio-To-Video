import os
import threading
from dotenv import load_dotenv

load_dotenv()

from web import create_app
from core.jobs import cleanup_old_jobs, cleanup_loop

app = create_app()

if __name__ == "__main__":
    cleanup_old_jobs()
    threading.Thread(target=cleanup_loop, daemon=True).start()
    # Debug is opt-in: the Werkzeug debugger allows remote code execution to
    # anyone who can reach it, which is a real risk combined with host="0.0.0.0".
    debug_mode = os.getenv("FLASK_DEBUG", "false").strip().lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000, threaded=True)
