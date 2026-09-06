FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ python3 python3-dev cmake ninja-build git \
    libsqlite3-dev libxml2-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt
RUN git clone --branch ns-3.41 --depth 1 https://gitlab.com/nsnam/ns-3-dev.git ns-3.41
WORKDIR /opt/ns-3.41
COPY main/contention_scaling.cc scratch/main_contention.cc
COPY main/separation_sweep.cc scratch/main_separation.cc
COPY additional/contention_scaling.cc scratch/short_contention.cc
COPY additional/asymmetric_overlap.cc scratch/overlapping.cc
COPY additional/rate_overhead_validation.cc scratch/rate_overhead.cc
COPY additional/dynamic_udp_validation.cc scratch/dynamic.cc
RUN ./ns3 configure --disable-examples --disable-tests \
    --enable-modules wifi,internet,mobility,applications,flow-monitor,traffic-control -d release \
    && ./ns3 build scratch/main_contention scratch/main_separation scratch/short_contention \
    scratch/overlapping scratch/rate_overhead scratch/dynamic
COPY run_packets.py /opt/run_packets.py
ENTRYPOINT ["python3", "/opt/run_packets.py"]
