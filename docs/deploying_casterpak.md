
This is more of a diary than docs.  This is not authoritative.

AWS: use the Casterpak Instance template: CasterPak (lt-0343b94cb9216cffe) and launch an instance.

below is how you build a casterpak server.  It's advised you take a snapshot after this is done.

ssh ubuntu@<ip-of-instance>

sudo apt update

sudo apt remove $(dpkg --get-selections docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc | cut -f1)

# Add Docker's official GPG key:
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update

sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

## Now, test that docker is running
sudo systemctl status docker  (write something to assert you get a good answer.)

sudo usermod -aG docker ubuntu

## get casterpak
git clone https://github.com/flipmcf/CasterPak.git

cd CasterPak

Follow instructions in readme for installation.