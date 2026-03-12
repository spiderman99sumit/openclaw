#!/usr/bin/env python3
# render_openclaw_config.py
# Renders openclaw.json from secrets env file.

import os
import json

SECRETS_FILE = "/kaggle/working/.openclaw/credentials/openclaw-secrets.env"
OUTPUT_PATH = "/kaggle/working/.openclaw/openclaw.json"

def load_env(path):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def main():
    if not os.path.exists(SECRETS_FILE):
        print(f"ERROR: secrets file not found: {SECRETS_FILE}")
        return

    env = load_env(SECRETS_FILE)

    config = {
        "version": "1.0",
        "default_agent": "neo",
        "gateway": {
            "auth_token": env.get("GATEWAY_AUTH_TOKEN", ""),
            "host": env.get("N8N_HOST", "0.0.0.0"),
            "port": int(env.get("N8N_PORT", 5678))
        },
        "integrations": {
            "discord": {
                "enabled": True,
                "bot_token": env.get("DISCORD_BOT_TOKEN", ""),
                "guild_id": "1475512953154568333"
            },
            "brave_search": {
                "api_key": env.get("BRAVE_API_KEY", "")
            },
            "openrouter": {
                "api_key": env.get("OPENROUTER_API_KEY", ""),
                "model": env.get("OPENROUTER_MODEL", "")
            }
        },
        "agents": {
            "neo":            {"channel_id": "1478772230593839275"},
            "maya":           {"channel_id": "1478277461807595627"},
            "jordan":         {"channel_id": "1478277630632530030"},
            "sam":            {"channel_id": "1478277891174436960"},
            "creative-lab":   {"channel_id": "1478275763093635244"},
            "prompt-engineer":{"channel_id": "1479810885907251200"},
            "ops-guardian":   {"channel_id": "1478277286808780842"},
            "manager":        {"channel_id": "1479395533154947143"},
            "watchdog":       {"channel_id": "1479395535248162858"},
            "validator":      {"channel_id": "1479395536183230524"},
            "recovery":       {"channel_id": "1479395537458434068"},
            "n8n-worker":     {"channel_id": "1478865805306368163"}
        },
        "state_dir": env.get("OPENCLAW_STATE_DIR", "/kaggle/working/.openclaw/state")
    }

    # Check for blanks
    blanks = [k for k, v in {
        "DISCORD_BOT_TOKEN": config["integrations"]["discord"]["bot_token"],
        "GATEWAY_AUTH_TOKEN": config["gateway"]["auth_token"],
        "BRAVE_API_KEY": config["integrations"]["brave_search"]["api_key"],
        "OPENROUTER_API_KEY": config["integrations"]["openrouter"]["api_key"],
    }.items() if not v]

    with open(OUTPUT_PATH, "w") as f:
        json.dump(config, f, indent=2)

    print(f"OK: wrote {OUTPUT_PATH}")
    if blanks:
        print(f"WARN: these keys are blank — fill secrets before starting runtime: {blanks}")
    else:
        print("OK: no blanks detected")

if __name__ == "__main__":
    main()
