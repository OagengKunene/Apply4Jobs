import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="ApplyAtlas application agent")
    parser.add_argument("command", choices=["serve", "token", "campaign"])
    parser.add_argument("--port", type=int, default=int(os.getenv("APPLYATLAS_PORT", "8000")))
    parser.add_argument("--config", default="campaign.json")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.command == "token":
        from .api import owner_token
        from .store import Store
        store = Store(Path(os.getenv("APPLYATLAS_DATA_DIR", "./data")))
        print(owner_token(store.root))
    elif args.command == "serve":
        import uvicorn

        from .api import create_app
        os.environ["APPLYATLAS_PORT"] = str(args.port)
        print("ApplyAtlas: open http://localhost:" + str(args.port))
        print("Retrieve your local owner token in another terminal: applyatlas token")
        uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
    else:
        from .browser import BrowserExecutor
        from .connectors import discover
        from .graph import Engine
        from .models import DiscoveryRequest
        from .store import Store
        store = Store(Path(os.getenv("APPLYATLAS_DATA_DIR", "./data")))
        engine = Engine(store, BrowserExecutor(store.root))
        try:
            while True:
                config = json.loads(Path(args.config).read_text())
                candidate_id = config["candidate_id"]
                for source in config["sources"]:
                    try:
                        jobs = discover(DiscoveryRequest.model_validate(source))
                    except Exception as exc:
                        store.event(None, "campaign", "Discovery failed: " + type(exc).__name__)
                        continue
                    for job in jobs:
                        store.save_job(job)
                        try:
                            engine.run(candidate_id, job.id)
                        except Exception as exc:
                            store.event(None, "campaign", "Run failed: " + type(exc).__name__)
                if args.once:
                    break
                time.sleep(max(300, int(config.get("interval_seconds", 1800))))
        finally:
            engine.close()


if __name__ == "__main__":
    main()
