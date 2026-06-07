FROM nodered/node-red:3.1

USER root
RUN cd /usr/src/node-red \
 && npm install --no-audit --no-fund --no-update-notifier \
        node-red-dashboard@3.6.5 \
 && chown -R node-red:root /usr/src/node-red/node_modules
USER node-red
