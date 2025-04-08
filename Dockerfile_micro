FROM registry.cells.es/docker/payara/micro:6.2025.2-jdk21

ARG NEW_UID=1000
ARG NEW_GID=1000

USER root

# Change UID and GID for payara user to allow NFS mount
RUN addgroup -g $NEW_GID badassfish
RUN adduser -D -h ${PAYARA_HOME} -H -s /bin/bash badassfish -u $NEW_UID -G badassfish && \
    echo badassfish:badassfish | chpasswd

# Fix permissions
RUN find / -user payara -exec chown -R badassfish:badassfish {} \;

USER badassfish