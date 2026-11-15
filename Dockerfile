FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken

WORKDIR /app

COPY requirements.txt .
# Bake the tokenizer into the image so a run never depends on downloading it.
RUN pip install -r requirements.txt \
 && python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"

COPY kbsync/ kbsync/
COPY main.py ask.py ./

RUN useradd --create-home app && chown -R app /app
USER app

# `docker run IMAGE`          -> python main.py
# `docker run IMAGE main.py`  -> python main.py   (the form used in the brief)
# `docker run IMAGE ask.py "How do I add a YouTube video?"`
ENTRYPOINT ["python"]
CMD ["main.py"]
