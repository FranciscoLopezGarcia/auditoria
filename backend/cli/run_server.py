"""
run_server.py — Levantar servidor.

    python run_server.py
    python run_server.py --port 3000 --reload
"""

import argparse
import uvicorn


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    args = p.parse_args()

    print(f"\n  Server:  http://localhost:{args.port}")
    print(f"  Docs:    http://localhost:{args.port}/docs")
    print(f"  Health:  http://localhost:{args.port}/api/v1/health\n")

    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
