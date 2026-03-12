# MASTER GOALS

## MAIN GOAL
- Build a money-making automation stack
- Current focus ONLY: AI Influencer Factory for Fiverr / gig work
- Postponed: automated cosplay pages, video channel, opportunity-research agent

## PRODUCT GOAL
One factory: intake → preview → approval → LoRA training → final batch → QA → delivery

## ARCHITECTURE
- OpenClaw = orchestration brain
- n8n = automation bus
- ComfyUI / Modal / Lightning / Kaggle = GPU workers
- Google Drive + Sheets = storage + audit trail
- Discord = team communication

## AGENTS
| Agent | Role |
|-------|------|
| Neo (main) | Orchestrator |
| Manager | Client intake, job tracking |
| Creative Lab | Persona/style direction |
| Prompt Engineer | SDXL prompt packs |
| Jordan | ComfyUI/image generation |
| Validator | QA |
| Maya | Content writing |
| Sam | Social media strategy |
| N8N Worker | Automation/delivery |
| Ops Guardian | Monitoring |
| Watchdog | Deadline alerts |
| Recovery | Failed run handling |
