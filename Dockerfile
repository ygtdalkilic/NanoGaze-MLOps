FROM python:3.13-slim

# Install Node.js 20
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install MongoDB MCP server
RUN npm install -g mongodb-mcp-server

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV REPORTS_DIR=/app/reports
ENV DASHBOARD_PORT=8080

EXPOSE 8080

CMD ["python", "run.py", "--skip-agent"]
