#
# This docker file will configure an environment into which the Matlab compiler
# runtime will be installed and in which stand-alone Matlab routines (such as
# those created with Matlab's deploytool) can be executed.
#



# First start with a python runtime
FROM flywheel/fsl-base:5.0.9-trusty

# This is setting things up for python
RUN apt-get -qq update && apt-get -qq install -y \
    software-properties-common \
    python3-numpy \
    libreadline-gplv2-dev libncursesw5-dev libssl-dev  libsqlite3-dev tk-dev libgdbm-dev libc6-dev libbz2-dev libffi-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY b02b0.cnf /flywheel/v0/b02b0.cnf
COPY requirements.txt ./requirements.txt
RUN pip3 install -r requirements.txt && rm -rf /root/.cache/pip


# Make directory for flywheel spec (v0)
ENV FLYWHEEL /flywheel/v0
WORKDIR ${FLYWHEEL}

# Save the environment for later use in the Run script (run.py)
RUN python3 -c 'import os, json; f = open("/tmp/gear_environ.json", "w"); json.dump(dict(os.environ), f)'

COPY run.py ${FLYWHEEL}/run.py
