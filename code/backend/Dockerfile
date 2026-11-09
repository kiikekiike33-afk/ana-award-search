FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
# Python依存ライブラリのインストール（不要なPlaywright/Chromiumを外してイメージを大幅軽量化）
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
