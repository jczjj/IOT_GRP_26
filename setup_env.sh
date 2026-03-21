#!/bin/bash
# V12.4 - Universal Environment Setup
# Usage: sudo bash setup_env.sh

echo "🚀 Starting SDN Service Infrastructure Setup..."

# 1. Create the sdn_service user if it doesn't exist
if id "sdn_service" &>/dev/null; then
    echo "✅ User 'sdn_service' already exists."
else
    sudo adduser --disabled-password --gecos "" sdn_service
    echo "👤 User 'sdn_service' created."
fi

# 2. Assign Groups
# dialout: Required for LoRa/Serial port access (/dev/ttyUSB0)
# sudo: Required for administrative tasks
sudo usermod -aG sudo,dialout sdn_service
echo "👥 Groups assigned: sudo, dialout."

# 3. Configure Passwordless Sudo
# This allows sdn_service to run nmcli, rsync, and iw commands without a prompt
echo "sdn_service ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/sdn_service
sudo chmod 0440 /etc/sudoers.d/sdn_service
echo "🔑 Passwordless sudo configured."

# 4. Create Directory Structure
# Uniform paths for both Server and Clients
BASE_DIR="/home/sdn_service/poc"
subdirs=(
    "$BASE_DIR/python_script"
    "$BASE_DIR/file_transfer/receive"
    "$BASE_DIR/file_transfer/archive" # Primarily used by Node 0 (Server)
)

for dir in "${subdirs[@]}"; do
    sudo mkdir -p "$dir"
    echo "📁 Created: $dir"
done

# 5. Set Ownership and Permissions
sudo chown -R sdn_service:sdn_service /home/sdn_service/poc
sudo chmod -R 755 /home/sdn_service/poc
echo "🔒 Permissions set for sdn_service."

# 6. Finalize SSH Directory
sudo -u sdn_service mkdir -p /home/sdn_service/.ssh
sudo -u sdn_service chmod 700 /home/sdn_service/.ssh
echo "📂 SSH directory initialized."

echo "------------------------------------------------"
echo "✅ SETUP COMPLETE. Please log in as sdn_service."
echo "Command: sudo su - sdn_service"
echo "------------------------------------------------"