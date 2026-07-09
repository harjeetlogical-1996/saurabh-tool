FROM python:3.12-slim

WORKDIR /app

# Install deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY server.py oauth.py db.py pages.py mailer.py chat.py billing.py razorpay_pay.py admin.py blog_posts.py google_api.py bing_api.py start.py ./
COPY plugin ./plugin
COPY assets ./assets

# Railway provides $PORT; default 8000 locally
ENV PORT=8000
EXPOSE 8000

CMD ["python", "start.py"]
