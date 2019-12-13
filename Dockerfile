#
# This docker file will configure an environment into which the Matlab compiler
# runtime will be installed and in which stand-alone Matlab routines (such as
# those created with Matlab's deploytool) can be executed.
#
# See http://www.mathworks.com/products/compiler/mcr/ for more info.


# First start with a python runtime
FROM flywheel/python:dcmtk.latest

# Now we'll grab and install the matlab MCR for 2015b
RUN apt-get -qq update && apt-get -qq install -y \
     unzip \
     xorg \
     wget \
     curl && \
     mkdir /mcr-install && \
     mkdir /opt/mcr && \
     cd /mcr-install && \
     wget http://ssd.mathworks.com/supportfiles/downloads/R2015b/deployment_files/R2015b/installers/glnxa64/MCR_R2015b_glnxa64_installer.zip && \
     cd /mcr-install && \
     unzip -q MCR_R2015b_glnxa64_installer.zip && \
     ./install -destinationFolder /opt/mcr -agreeToLicense yes -mode silent && \
     cd / && \
     rm -rf mcr-install && \
     pip3 install --upgrade pip

# Really weird bug, setting LD_LIBRARY_PATH breaks pip, so run all the pip stuff before setting that.
COPY requirements.txt ./requirements.txt
RUN pip3 install -r requirements.txt

RUN rm -rf /root/.cache/pip && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Configure environment variables for MCR
ENV LD_LIBRARY_PATH /opt/mcr/v90/runtime/glnxa64:/opt/mcr/v90/bin/glnxa64:/opt/mcr/v90/sys/os/glnxa64:/opt/mcr/v90/extern/bin/glnxa64

# Make directory for flywheel spec (v0)
ENV FLYWHEEL /flywheel/v0
WORKDIR ${FLYWHEEL}

# Save the environment for later use in the Run script (run.py)
RUN python3 -c 'import os, json; f = open("/tmp/gear_environ.json", "w"); json.dump(dict(os.environ), f)'

#---- Divergent from standard Gear environemnt ----#

# Copy over a required supporting directory for this particular gear
COPY libs/com.itheramedical.msotlib_beta_rev157/ ${FLYWHEEL}/libs/com.itheramedical.msotlib_beta_rev157/

# Pull in files required for runtime
COPY run_MSOT_standalone.sh ${FLYWHEEL}/run_MSOT_standalone.sh
COPY MSOT_standalone ${FLYWHEEL}/MSOT_standalone
COPY run.py ${FLYWHEEL}/run.py
