import sys
import json
import threading
from pathlib import Path
from typing import Dict, Any, Optional
import webview

from jarvis.agent.loop import JarvisAgent
from jarvis.config import settings
from jarvis.utils.logging import logger

class GuiApi:
    """API exposed to JavaScript frontend in PyWebView."""
    
    def __init__(self):
        self._window: Optional[webview.Window] = None
        self._agent: Optional[JarvisAgent] = None
        self._confirm_result: bool = False
        self._confirm_event = threading.Event()
        self._agent_running: bool = False
        self._stt_running: bool = False
        self._stt_lock = threading.Lock()
        
    def set_window(self, window: webview.Window) -> None:
        self._window = window
        try:
            # Initialize Jarvis agent (is_interactive=True so it halts on dangerous actions)
            self._agent = JarvisAgent(is_interactive=True)
        except Exception as e:
            logger.error(f"Failed to initialize Jarvis agent for GUI: {e}")
            
    def execute_command(self, user_input: str) -> None:
        """Called by Javascript to submit a natural language instruction."""
        if not self._agent:
            self._send_error("Agent not initialized. Please check your config/API keys.")
            return
            
        user_input = user_input.strip()
        if not user_input:
            return
            
        if self._agent_running:
            logger.warning("Agent execution in progress. Ignoring concurrent command.")
            self._send_error("Jarvis is currently processing a command. Please wait.")
            return
            
        logger.info(f"GUI Command requested: '{user_input}'")
        # Run agent in background thread to prevent UI freezing
        threading.Thread(
            target=self._run_agent_loop,
            args=(user_input,),
            daemon=True
        ).start()
        
    def set_confirmation_response(self, approved: bool) -> None:
        """Called by Javascript to submit user confirmation decision (Allow/Deny)."""
        logger.info(f"GUI confirmation received: approved={approved}")
        self._confirm_result = approved
        self._confirm_event.set()
        
    def get_learned_facts(self) -> list[str]:
        """Exposes memory facts to the JS frontend."""
        if self._agent:
            return self._agent.long_term_memory.get_facts()
        return []
        
    def get_system_diagnostics(self) -> Dict[str, Any]:
        """Exposes system info to the JS frontend."""
        from jarvis.tools.system import get_system_info
        return get_system_info()

    def start_voice_capture(self) -> None:
        """Called by JS to start Python-based voice capture (bypasses WebView2 STT permission issues)."""
        with self._stt_lock:
            if self._stt_running:
                logger.warning("Python STT already running. Ignoring concurrent start request.")
                return
            self._stt_running = True
        threading.Thread(target=self._capture_voice, daemon=True).start()

    def _capture_voice(self) -> None:
        """Capture mic audio via Python speech_recognition and send result back to JS."""
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            r.energy_threshold = 300
            r.dynamic_energy_threshold = True
            with sr.Microphone() as source:
                logger.info("Python STT: adjusting for ambient noise...")
                r.adjust_for_ambient_noise(source, duration=0.5)
                if self._window:
                    self._window.evaluate_js("window.onPySTTStatus('listening')")
                logger.info("Python STT: listening for speech...")
                try:
                    audio = r.listen(source, timeout=8, phrase_time_limit=12)
                except sr.WaitTimeoutError:
                    logger.info("Python STT: timeout — no speech detected.")
                    if self._window:
                        self._window.evaluate_js("window.onPySTTStatus('timeout')")
                    return

            if self._window:
                self._window.evaluate_js("window.onPySTTStatus('processing')")
            logger.info("Python STT: sending to Google Speech API...")
            text = r.recognize_google(audio)
            logger.info(f"Python STT: recognized text = '{text}'")
            if self._window:
                self._window.evaluate_js(f"window.onPySTTResult({json.dumps(text)})")

        except Exception as e:
            logger.error(f"Python STT error: {e}", exc_info=True)
            if self._window:
                self._window.evaluate_js(f"window.onPySTTError({json.dumps(str(e))})")
        finally:
            with self._stt_lock:
                self._stt_running = False

        
    def _run_agent_loop(self, user_input: str) -> None:
        """Asynchronous execution loop sending status events and blocking on confirmation checks."""
        self._agent_running = True
        try:
            agent_generator = self._agent.run(user_input)
            event = None
            
            while True:
                try:
                    # If the previous iteration yielded a confirmation request, we must wait for send()
                    if event is not None and event.get("type") == "confirmation_request":
                        logger.info("Python waiting for GUI confirmation modal...")
                        
                        # Bring GUI window to foreground so user sees the safety popup
                        try:
                            self._window.restore()
                        except Exception as ex:
                            logger.debug(f"Failed to restore window: {ex}")
                            
                        # Clear event and evaluate JS to show the modal in frontend
                        self._confirm_event.clear()
                        js_code = f"window.showConfirmationModal({json.dumps(event['description'])});"
                        self._window.evaluate_js(js_code)
                        
                        # Block thread until JS triggers set_confirmation_response()
                        self._confirm_event.wait()
                        
                        # 3. Resume generator sending the boolean approved response
                        event = agent_generator.send(self._confirm_result)
                    else:
                        # Standard generator step
                        event = next(agent_generator)
                    
                    # Push event payload to Javascript
                    if isinstance(event, dict):
                        self._send_event(event)
                        
                except StopIteration as stop:
                    # Reasoning successfully completed
                    final_text = stop.value
                    self._send_complete(final_text)
                    break
                except Exception as e:
                    logger.error(f"Error in GUI Agent execution: {e}", exc_info=True)
                    self._send_error(f"Runtime execution error: {str(e)}")
                    break
        finally:
            self._agent_running = False

    def _send_event(self, payload: Dict[str, Any]) -> None:
        """Helper to serialize and evaluate dynamic events in the web document."""
        if self._window:
            js = f"window.onAgentEvent({json.dumps(payload)});"
            self._window.evaluate_js(js)

    def _send_complete(self, text: str) -> None:
        """Helper to submit final complete message to frontend."""
        if self._window:
            js = f"window.onAgentComplete({json.dumps(text)});"
            self._window.evaluate_js(js)

    def _send_error(self, message: str) -> None:
        """Helper to submit error to frontend."""
        if self._window:
            js = f"window.onAgentError({json.dumps(message)});"
            self._window.evaluate_js(js)


import http.server
import socket
import socketserver
import uuid

# ---- Async Job Queue for slow local LLM responses ----
# POST /api/command  → returns {"job_id": "xxx"} immediately
# GET  /api/result?id=xxx → returns {"status":"pending"} or {"status":"done","response":"..."}
_jobs: dict = {}   # job_id -> {"status": "pending"|"done"|"error", "response": str}
_jobs_lock = threading.Lock()

def _run_agent_job(job_id: str, user_input: str) -> None:
    """Runs the Jarvis agent in a background thread and stores the result in _jobs."""
    try:
        from jarvis.agent.loop import JarvisAgent
        agent = JarvisAgent(is_interactive=False)
        agent_generator = agent.run(user_input)
        final_text = ""
        while True:
            try:
                next(agent_generator)
            except StopIteration as stop:
                final_text = stop.value
                break
        with _jobs_lock:
            _jobs[job_id] = {"status": "done", "response": final_text}
        logger.info(f"Job {job_id} completed.")
    except Exception as ex:
        logger.error(f"Job {job_id} failed: {ex}", exc_info=True)
        with _jobs_lock:
            _jobs[job_id] = {"status": "error", "response": f"Agent error: {str(ex)}"}

def find_free_port() -> int:
    """Finds an available free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def run_local_server(directory: Path, port: int) -> None:
    """Runs a minimal HTTP server serving the directory forever on localhost."""
    class LocalHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
        def log_message(self, format, *args):
            pass # Suppress logging console pollution
            
        def _send_json(self, code: int, payload: dict):
            body = json.dumps(payload).encode('utf-8')
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            
        def do_GET(self):
            if self.path == "/api/diagnostics":
                try:
                    from jarvis.tools.system import get_system_info
                    info = get_system_info()
                    self._send_json(200, info)
                except Exception as ex:
                    logger.error(f"Error executing diagnostics GET: {ex}", exc_info=True)
                    self._send_json(500, {"error": str(ex)})
            elif self.path == "/api/facts":
                try:
                    from jarvis.agent.loop import JarvisAgent
                    agent = JarvisAgent(is_interactive=False)
                    facts = agent.long_term_memory.get_facts()
                    self._send_json(200, facts)
                except Exception as ex:
                    logger.error(f"Error executing memory facts GET: {ex}", exc_info=True)
                    self._send_json(500, {"error": str(ex)})
            elif self.path.startswith("/api/result"):
                # Poll for job result: GET /api/result?id=JOB_ID
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                job_id = qs.get("id", [None])[0]
                if not job_id:
                    self._send_json(400, {"error": "Missing job id"})
                    return
                with _jobs_lock:
                    job = _jobs.get(job_id)
                if job is None:
                    self._send_json(404, {"error": "Unknown job id"})
                elif job["status"] == "pending":
                    self._send_json(200, {"status": "pending"})
                elif job["status"] == "done":
                    # Clean up finished job
                    with _jobs_lock:
                        _jobs.pop(job_id, None)
                    self._send_json(200, {"status": "done", "response": job["response"]})
                else:  # error
                    with _jobs_lock:
                        _jobs.pop(job_id, None)
                    self._send_json(200, {"status": "error", "response": job["response"]})
            else:
                super().do_GET()

        def do_POST(self):
            if self.path == "/api/command":
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                try:
                    data = json.loads(post_data.decode('utf-8'))
                    user_input = data.get("command", "").strip()
                    if not user_input:
                        self._send_json(400, {"error": "Empty command"})
                        return

                    # Create job and return job_id immediately (no blocking!)
                    job_id = str(uuid.uuid4())
                    with _jobs_lock:
                        _jobs[job_id] = {"status": "pending", "response": ""}
                    
                    threading.Thread(
                        target=_run_agent_job,
                        args=(job_id, user_input),
                        daemon=True
                    ).start()
                    
                    logger.info(f"Queued job {job_id} for command: '{user_input}'")
                    self._send_json(200, {"status": "queued", "job_id": job_id})

                except Exception as ex:
                    logger.error(f"Error queuing command: {ex}", exc_info=True)
                    self._send_json(500, {"error": str(ex)})
            else:
                self.send_response(404)
                self.end_headers()
            
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), LocalHandler) as httpd:
        print(f"\n[HUD Web Server] Running at: http://127.0.0.1:{port}/index.html\n")
        sys.stdout.flush()
        logger.info(f"Local GUI server running at http://127.0.0.1:{port}")
        httpd.serve_forever()


def start_gui() -> None:
    """Launches the PyWebView GUI application."""
    web_dir = Path(__file__).parent / "web"
    
    if not web_dir.exists():
        raise FileNotFoundError(f"Frontend assets not found at '{web_dir}'")
        
    # Bind server to a free port to avoid system conflicts
    port = find_free_port()
    
    # Run the server inside a daemon thread
    server_thread = threading.Thread(
        target=run_local_server,
        args=(web_dir, port),
        daemon=True
    )
    server_thread.start()
    
    # Load via localhost HTTP to grant full secure-context browser speech API access
    url = f"http://127.0.0.1:{port}/index.html"
    
    api = GuiApi()
    window = webview.create_window(
        title="Jarvis AI Assistant",
        url=url,
        js_api=api,
        width=1050,
        height=750,
        resizable=True,
        min_size=(850, 600),
        background_color="#09090b"  # Dark charcoal theme background
    )
    api.set_window(window)
    
    def on_webview_ready():
        try:
            webview_control = window.native.webview
            if webview_control and hasattr(webview_control, "CoreWebView2") and webview_control.CoreWebView2:
                def on_permission_requested(sender, args):
                    try:
                        # Auto-approve permission requests (Microphone, Camera, Clipboard, etc.)
                        args.State = 1  # CoreWebView2PermissionState.Allow
                        args.Handled = True
                        logger.info(f"CoreWebView2 auto-granted permission: {args.PermissionKind}")
                    except Exception as ex:
                        logger.warning(f"Error in CoreWebView2.PermissionRequested callback: {ex}")
                
                webview_control.CoreWebView2.PermissionRequested += on_permission_requested
                logger.info("Successfully subscribed WebView2 CoreWebView2.PermissionRequested event.")
        except Exception as e:
            logger.warning(f"Could not hook CoreWebView2.PermissionRequested (non-Windows or dotnet issue): {e}")

    window.events.shown += on_webview_ready
    
    logger.info("Initializing Jarvis Desktop GUI runtime...")
    # Start webview loop with devtools debugging active
    webview.start(debug=True)
