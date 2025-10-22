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

# Install Python dependencies
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Source ROS2 setup in bashrc
RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV ROS_DOMAIN_ID=0

# Default command
CMD ["/bin/bash"]
