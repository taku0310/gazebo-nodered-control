FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install --no-install-recommends -y \
        ros-humble-gazebo-ros-pkgs \
        ros-humble-gazebo-plugins \
        ros-humble-rmw-cyclonedds-cpp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /sim
COPY worlds /sim/worlds
COPY launch /sim/launch
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash", "-lc", "ros2 launch /sim/launch/gazebo.launch.py"]
