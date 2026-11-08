FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
# Python依存ライブラリと、Playwright用のChromiumをインストール
RUN pip install --no-cache-dir -r requirements.txt && playwright install --with-deps chromium
COPY app ./app
