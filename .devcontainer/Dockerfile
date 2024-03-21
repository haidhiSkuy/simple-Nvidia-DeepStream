FROM nvcr.io/nvidia/deepstream:6.4-triton-multiarch 

RUN apt-get update
RUN /opt/nvidia/deepstream/deepstream-6.4/user_deepstream_python_apps_install.sh --build-bindings -r master
RUN apt-get install libglib2.0 libglib2.0-dev libssl-dev -y

# REDIS 
RUN apt install lsb-release curl gpg -y 
RUN apt-get install language-pack-id -y
RUN curl -fsSL https://packages.redis.io/gpg | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
RUN echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/redis.list
RUN apt-get install redis -y 

ENV LANGUAGE=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
RUN locale-gen en_US.UTF-8
RUN dpkg-reconfigure locales

