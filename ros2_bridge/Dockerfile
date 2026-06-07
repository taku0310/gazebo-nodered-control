FROM ros:humble-ros-base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install --no-install-recommends -y \
        python3-colcon-common-extensions \
        python3-paho-mqtt \
        ros-humble-rmw-cyclonedds-cpp \
        ros-humble-geometry-msgs \
        ros-humble-nav-msgs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ws
COPY ws/src ./src

# Build the workspace once at image build time so container start is fast.
RUN . /opt/ros/humble/setup.sh \
    && colcon build --symlink-install

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "mqtt_ros2_bridge", "bridge.launch.py"]
