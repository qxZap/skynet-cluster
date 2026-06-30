FROM python:3.11-slim
WORKDIR /
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
# context is ./cluster; land it as the importable package /cluster
COPY . /cluster
EXPOSE 8080
CMD ["uvicorn", "cluster.app:app", "--host", "0.0.0.0", "--port", "8080"]
