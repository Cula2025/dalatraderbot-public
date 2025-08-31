# Trader Bot (Clean Start)

Minimal, ren start för backtest med Streamlit + RSI-strategi.

## Snabbstart (Windows PowerShell)

```powershell
# 1) Packa upp zip:en där du vill ha projektet
# 2) Öppna PowerShell i projektroten (mappen med requirements.txt)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip setuptools wheel
pip install -r requirements.txt

cd app
streamlit run ui.py --server.port 8502
```

Om något strular med Streamlit/yfinance, testa minimala appen:
```powershell
streamlit run ui_min.py --server.port 8503
```
```

## Struktur
```
trader-bot-clean/
├── app/
│   ├── ui.py
│   ├── ui_min.py
│   ├── strategy.py
│   ├── backtest.py
│   └── data.py
├── requirements.txt
└── README.md
```

CI retry 2025-08-31T23:29:59.9579878+02:00

CI retry 2025-08-31T23:45:08.4137838+02:00

Public CI trigger 2025-09-01T01:18:04.6303924+02:00
