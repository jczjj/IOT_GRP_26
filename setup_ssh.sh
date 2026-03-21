#!/bin/bash
# V12.4 - Universal SSH & Security Setup
# Run as: sdn_service

echo "🔒 Initializing SSH Security for sdn_service..."

# 1. Ensure .ssh directory exists with correct permissions
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# 2. Setup Authorized Keys (For INCOMING transfers)
# Replace the string below with your actual id_ed25519.pub content
PUB_KEY="YOUR_PUBLIC_KEY_CONTENT_HERE"

echo "$PUB_KEY" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
echo "🔑 Public key added to authorized_keys."

# 3. Setup Private Key (For OUTGOING transfers)
# Ensure your private key file (e.g., id_ed25519) is placed in ~/.ssh/
# If you don't have one, generate it with: ssh-keygen -t ed25519 -N ""
if [ -f ~/.ssh/id_ed25519 ]; then
    chmod 600 ~/.ssh/id_ed25519
    echo "🔑 Private key permissions secured (600)."
else
    echo "⚠️ Warning: No private key (id_ed25519) found in ~/.ssh/"
fi

# 4. Create the Automation Config
# This allows nodes to connect to each other (10.42.x.1) without prompts
cat <<EOF > ~/.ssh/config
Host 10.42.*
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    IdentityFile ~/.ssh/id_ed25519
    BatchMode yes
    ConnectTimeout 5
EOF

chmod 600 ~/.ssh/config
echo "⚙️ SSH Config created for 10.42.* subnet."

echo "------------------------------------------------"
echo "✅ SSH SETUP COMPLETE."
echo "Test with: ssh -o BatchMode=yes 10.42.0.1 'echo success'"
echo "------------------------------------------------"