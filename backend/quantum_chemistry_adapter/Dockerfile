FROM python:3.11-slim

RUN python -m pip install --no-cache-dir "numpy<2" pyscf==2.8.0 openfermion==1.7.1

WORKDIR /app
RUN mkdir -p /inputs
COPY compute.py /app/compute.py
COPY guardrails.py /app/guardrails.py

ENTRYPOINT ["python", "/app/compute.py"]
