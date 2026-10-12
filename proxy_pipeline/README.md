# Proxy Pipeline Setup & Workflow

This folder contains the standalone Proxy-Based Meta & Ninja generation system:

## Files:
1. `create_ninja_emails.py`: Generates disposable emails via TempMail Ninja using US Residential Proxy (`proxy.h143.xyz:8080`) and saves to `ninja_created_accounts.txt`.
2. `create_meta_accounts.py`: Pure-request Meta account creator using US Residential Proxy. Validates, receives OTP, activates account without Captcha, and saves directly to `meta.csv`.
3. `NINJA.py`: Core Socket.IO client supporting automatic residential proxy session rotation.
4. `config.json`: Master configuration containing `ninja_proxy` settings.
5. `meta.csv`: Target account pool storing verified Meta accounts `(Email, Password, Username, CreatedAt, Status)`.

## Workflow:
1. Run `python create_ninja_emails.py [count]` to generate emails into the pool.
2. Run `python create_meta_accounts.py [count]` to register and verify Meta accounts into `meta.csv`.
3. The main automation bot takes accounts from `meta.csv`, pairs them with usernames from Telegram bot tasks, and executes the Instagram login/2FA tasks on the emulators!
