FROM python:3

ADD Crawler.py /

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

CMD [ "python", "-u", "./Crawler.py" ]