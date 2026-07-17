"""
Multisource Candidate Matching Platform — Server Launcher
----------------------------------------------------------
Usage:
  python run_server.py
  python run_server.py --port 8080
  python run_server.py --reload
"""

import argparse
import os
import sys
from pathlib import Path

# Load .env
_root = Path(__file__).parent
_env  = _root / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
        print(f"[Startup] Loaded .env")
    except ImportError:
        pass
else:
    print(f"[Startup] Warning: .env not found. Copy .env.example → .env and set GEMINI_API_KEY.")

# Warn if API key missing
_key = os.getenv("GEMINI_API_KEY", "")
if not _key or _key == "your_gemini_api_key_here":
    print("[Startup] WARNING: GEMINI_API_KEY not set — LLM enrichment will fail.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host",      default="0.0.0.0")
    parser.add_argument("--port",      default=8001, type=int)
    parser.add_argument("--reload",    action="store_true")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    print(f"\n{'='*58}")
    print(f"  Multisource Candidate Matching Platform  v1.0")
    print(f"{'='*58}")
    print(f"  API Docs : http://localhost:{args.port}/api/docs")
    print(f"  Web UI   : http://localhost:{args.port}/ui/")
    print(f"  Health   : http://localhost:{args.port}/health")
    print(f"{'='*58}\n")

    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )

if __name__ == "__main__":
    main()
