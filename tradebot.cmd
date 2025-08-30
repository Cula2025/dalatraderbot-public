@echo off
REM === Startar Tradebot UI ===
cd /d C:\trader-bot-clean
call .venv\Scripts\activate.bat
python -m streamlit run app\ui.py --server.port 8502
