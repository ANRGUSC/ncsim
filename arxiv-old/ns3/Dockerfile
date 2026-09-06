FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# Build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ python3 python3-dev cmake ninja-build git \
    libsqlite3-dev libxml2-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Clone ns-3.41 (minimal, single branch)
WORKDIR /opt
RUN git clone --branch ns-3.41 --depth 1 \
    https://gitlab.com/nsnam/ns-3-dev.git ns-3.41

WORKDIR /opt/ns-3.41

# Copy simulation sources into ns-3 scratch directory
COPY contention_scaling.cc scratch/contention_scaling.cc
COPY separation_sweep.cc scratch/separation_sweep.cc

# Build ns-3 (only wifi + internet modules, Release mode)
RUN ./ns3 configure --disable-examples --disable-tests \
    --enable-modules wifi,internet,mobility,applications,flow-monitor \
    -d release \
    && ./ns3 build scratch/contention_scaling \
    && ./ns3 build scratch/separation_sweep

# Results directory (mount point)
RUN mkdir -p /results

COPY run_experiments.sh /opt/run_experiments.sh
RUN chmod +x /opt/run_experiments.sh

ENTRYPOINT ["/opt/run_experiments.sh"]
