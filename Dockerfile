FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PORT=8402
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# The repo root is the mcp_server package (it uses relative imports).
COPY . /app/mcp_server
RUN useradd -r -u 10001 app && mkdir -p /app/mcp_server/data && chown -R app /app/mcp_server/data
USER app
EXPOSE 8402
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'])"
CMD ["sh", "-c", "exec uvicorn mcp_server.server:app --host 0.0.0.0 --port ${PORT}"]
