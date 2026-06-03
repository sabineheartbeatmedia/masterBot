# Agent Lab Bot — Kundenpaket

Dieses Paket enthält den kompletten Code für den Agent Lab Bot. Folge der mitgelieferten .docx-Anleitung Schritt für Schritt.

## Was ist drin

```
agent-lab-kundenpaket/
├── bot.py                  # Telegram-Bot (Hauptdatei)
├── daily_run.py            # Täglicher Scan (Cron)
├── weekly_scout.py         # Wöchentliche AI-News (Cron)
├── lab.py                  # CLI-Einstieg
├── requirements.txt        # Python-Abhängigkeiten
├── Procfile                # Railway-Deployment
├── .env.example            # Vorlage für deine API-Keys
├── agent/                  # Agent-Framework (Tool-Calling Loop)
└── lab/                    # Logik-Module
    ├── scanner.py          # ⚠️ HIER deine Agents eintragen (AGENT_FILES)
    ├── researcher.py
    ├── analyzer.py
    ├── applier.py
    ├── tracker.py
    ├── bloat_monitor.py
    └── web_scout.py
```

## Schnellstart

1. `.env.example` zu `.env` kopieren und Keys eintragen
2. In `lab/scanner.py` deine eigenen Agents in `AGENT_FILES` eintragen (Beispiel ist drin)
3. `pip install -r requirements.txt`
4. `python bot.py`
5. In Telegram `/start` an deinen Bot schicken

Vollständige Anleitung: siehe `anleitung-agent-lab-bot.docx`.
