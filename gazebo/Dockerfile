FROM ros:humble-ros-base

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    DISPLAY=:1 \
    LIBGL_ALWAYS_SOFTWARE=1 \
    OGRE_RTT_MODE=Copy

# Add OSRF Gazebo apt repository, then install Harmonic + ros_gz +
# the headless desktop stack (Xvfb + x11vnc + noVNC).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg lsb-release ca-certificates \
    && curl -sSL https://packages.osrfoundation.org/gazebo.gpg \
        -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/gazebo-stable.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        gz-harmonic \
        ros-humble-ros-gzharmonic \
        ros-humble-rmw-cyclonedds-cpp \
        xvfb x11vnc novnc websockify x11-utils \
        libgl1 libglu1-mesa libgl1-mesa-dri \
        procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /sim
COPY worlds /sim/worlds
COPY launch /sim/launch
COPY config /sim/config
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "/sim/launch/gazebo.launch.py"]
