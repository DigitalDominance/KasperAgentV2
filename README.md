
# KasperAI Bot

## Description
KasperAI is a Telegram bot that integrates:
- Blockchain (Kaspa/KRC20) functionality.
- AI interactions via OpenAI API.
- Text-to-Speech (TTS) using ElevenLabs.

## Features
- Assign credits based on deposits.
- AI and TTS interaction with credit deduction.
- Real-time blockchain wallet monitoring.

## Deployment
1. Install dependencies: `pip install -r requirements.txt`.
2. Set environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `ELEVEN_LABS_API_KEY`
3. Run locally: `python main.py`.
4. Deploy on Heroku using the provided `Procfile`.

## Directory Structure
- `main.py`: Core bot logic.
- `db_manager.py`: MongoDB management.
- `wallet_backend.py`: Blockchain wallet integration.
- `wallet/`: Contains Kaspa wallet files (e.g., `kaspa.js`, `kaspa_bg.wasm`).

## Future Improvements
- Add notifications for successful transactions.
- Expand AI features based on community feedback.

---
