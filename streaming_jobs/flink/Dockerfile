FROM flink:1.18.1-scala_2.12-java11

USER root
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends python3 python3-pip && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/bin/python3 /usr/bin/python && \
    pip install --no-cache-dir apache-flink==1.18.1
USER flink
