# syntax=docker/dockerfile:1
# Training sandbox image. Built by the platform (CI / `make sandbox-build`), never by agents.
# PyTorch 2.14.1 + CUDA 12.6 is the newest line that still supports Pascal GPUs (GTX 10xx):
# PyTorch 2.15 dropped cu126 wheels. Move to a newer CUDA tag once the server GPU is Turing or newer.
FROM pytorch/pytorch:2.14.1-cuda12.6-cudnn9-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/harness \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp \
    TORCH_HOME=/tmp/torch

COPY requirements.txt /opt/harness/requirements.txt
# The base image is Ubuntu 24.04 with torch pip-installed into the system Python (PEP 668 marks it
# "externally managed"). This image has one purpose and never apt-installs Python packages later,
# so installing next to torch is safe.
RUN pip install --no-cache-dir --break-system-packages -r /opt/harness/requirements.txt

COPY harness /opt/harness/harness
COPY configs /opt/harness/configs
COPY examples /opt/harness/examples

# Unprivileged runtime user. /workspace/out is pre-created so a fresh named volume inherits its owner.
RUN groupadd --system --gid 10001 sandbox \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /tmp --shell /usr/sbin/nologin sandbox \
 && mkdir -p /workspace/out \
 && chown 10001:10001 /workspace/out

WORKDIR /workspace
USER 10001:10001
ENTRYPOINT ["python", "-m", "harness.train"]
CMD ["--help"]
