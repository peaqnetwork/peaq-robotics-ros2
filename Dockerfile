FROM osrf/ros:humble-desktop

# Set working directory
WORKDIR /work

# Install system dependencies including IPFS and text editors
RUN apt-get update && apt-get install -y \
    python3-pip \
    git \
    curl \
    wget \
    nano \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required for Tether WDK integration)
# We use NodeSource for Node 20.x (works well with modern ESM + ethers v6).
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get update && apt-get install -y nodejs && \
    node --version && npm --version && \
    rm -rf /var/lib/apt/lists/*

# Install IPFS (Kubo)
RUN wget https://dist.ipfs.tech/kubo/v0.38.1/kubo_v0.38.1_linux-amd64.tar.gz && \
    tar -xvzf kubo_v0.38.1_linux-amd64.tar.gz && \
    cd kubo && \
    bash install.sh && \
    cd .. && \
    rm -rf kubo kubo_v0.38.1_linux-amd64.tar.gz

# Initialize IPFS
RUN ipfs init

# Copy requirements file
COPY requirements.txt /tmp/requirements.txt

# Upgrade the base image's pip before resolving the SDK dependency graph. The
# Ubuntu 22.04 package ships pip 22.0, whose resolver backtracks extensively on
# the current peaq SDK and Web3 dependency ranges.
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

# Source ROS2 setup in bashrc
RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV ROS_DOMAIN_ID=0

# Default command
CMD ["/bin/bash"]
