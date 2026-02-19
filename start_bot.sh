#!/bin/bash
cd /home/deploy/telegrambot
source /home/deploy/telegrambot/venv/bin/activate
pip install requirements.txt
python3 bot.py
