#!/bin/bash
# setup.sh - CasterPak Configuration Wizard

if [ -f .env ]; then
    read -p ".env already exists. Overwrite? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "--- CasterPak Setup Wizard ---"

# 1. Input Type

read -p "Input Type [filesystem, http, ftp, scp, rsync] (default: filesystem): " input_type

input_type=${input_type:-filesystem}



if [ "$input_type" == "filesystem" ]; then

    read -p "Local path to videos (default: ~/Videos): " video_path

    video_path=${video_path:-~/Videos}

fi



# 2. Cache Input

read -p "Cache input video files? (y/n, default: n): " cache_input

if [[ $cache_input =~ ^[Yy]$ ]]; then cache_input="True"; else cache_input="False"; fi



# 3. Server Name

read -p "Server Name for manifests (default: localhost): " servername

servername=${servername:-localhost}



# Write to .env

cat <<EOF > .env

CASTERPAK_INPUT_INPUT_TYPE=$input_type

CASTERPAK_FILESYSTEM_CACHE_INPUT=$cache_input

CASTERPAK_OUTPUT_SERVERNAME=$servername

HOST_VIDEO_PATH=$video_path

APP_PORT=5000

EOF



echo "Done! You can now run 'docker-compose up -d'"
