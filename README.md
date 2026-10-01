# METINSTA 🚀

AutoMetaInstaBot & Multi-Emulator Dashboard for Instagram automation, Telegram bot task coordination, 2FA management, and Google Sheets sync.

---

## ✨ Features

- **Multi-Worker Instagram Automation**: Playwright and Meta API integration with cookie session support.
- **Multi-Emulator GUI Dashboard**: CustomTkinter interface supporting LDPlayer, MuMu, and custom ADB ports.
- **Telegram Bot Task Coordination**: Telethon client for automated task receipt and reward verification.
- **2FA & OTP Management**: Automated TOTP generation using PyOTP.
- **Email Services**: Integrations for TempMail Ninja, Mail CX, and Mail TD.
- **Google Sheets Integration**: Automatic sync of credentials and execution status via Google Service Accounts & Webhooks.
- **Captcha Solving**: 2Captcha automated bypass.

---

## 📋 Requirements

- Python 3.10+
- Google Chrome or Chromium
- (Optional) Android Emulator: LDPlayer 9 / MuMu Player 12

---

## 🛠️ Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Maanik-99/METINSTA.git
   cd METINSTA
   ```

2. **Install dependencies:**
   ```bash
   install.bat
   ```
   *Or install manually via pip:*
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

3. **Configure Settings:**
   - Copy `config.example.json` to `config.json`:
     ```bash
     copy config.example.json config.json
     ```
   - Update your Telegram credentials, Google Sheets ID, and 2Captcha API keys in `config.json`.
   - If using Google Sheets, copy `service_account.example.json` to `service_account.json` and insert your service account credentials.
   - (Optional) Populate `images/` directory with verification photos if needed.

---

## 🚀 Usage

### Multi-Emulator GUI Dashboard
Run via batch script:
```bash
run_gui.bat
```
Or with python:
```bash
python insta_emulator_gui.py
```

### CLI Bot
Run via batch script:
```bash
run_cli.bat
```
Or with python:
```bash
python autometainstabot.py
```

---

## 🔒 Security & Privacy

Never commit your `config.json`, `credentials.csv`, `service_account.json`, or `*.session` files to public repositories. Ensure they remain listed in `.gitignore`.
