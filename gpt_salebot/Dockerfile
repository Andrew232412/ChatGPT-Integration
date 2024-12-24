FROM --platform=linux/arm64 debian:bookworm

RUN apt-get -y update
RUN apt-get -y upgrade

RUN apt-get -y install python3-pip python3-dev python3-setuptools

COPY ./requirements.txt ./

RUN pip3 install -r ./requirements.txt --break-system-packages

COPY . ./

RUN chmod +x src/entrypoint.sh

ENTRYPOINT ["src/entrypoint.sh"]
CMD ["src.main.handler"]