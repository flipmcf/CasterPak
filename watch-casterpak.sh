#!/bin/bash

# 1. PRE-FLIGHT: Inject tools into the running container
echo "🔧 Ensuring tools are installed in the container..."
docker exec -u 0 casterpak_server bash -c "apt-get update && apt-get install -y -qq watch tree"

# 2. CONFIG: Define our monitoring commands
# We use 'bash -c' inside the tabs to keep them open if a command fails
CMD_LOGS="docker logs -f casterpak_server"
CMD_FILES="docker exec -it casterpak_server watch -d -n 1 'tree -d -L 2 /tmp/video_input /tmp/segments'"

CMD_DB_INPUT='docker exec -it casterpak_server watch -n 1 "date +%s; sqlite3 /app/cacheDB.db '\''SELECT filename, (strftime(\"%s\", \"now\") - timestamp) || \"s\" AS age FROM inputfile ORDER BY timestamp DESC LIMIT 10;'\''"'

CMD_DB_SEGMENT='docker exec -it casterpak_server watch -n 1 "date +%s; sqlite3 /app/cacheDB.db '\''SELECT filename, (strftime(\"%s\", \"now\") - timestamp) || \"s\" AS age FROM segmentfile ORDER BY timestamp DESC LIMIT 10;'\''"'



CMD_SHELL="docker exec -it casterpak_server /bin/bash"

# 3. LAUNCH: windows 
# If you prefer separate windows instead of tabs, remove the '--tab' flags
gnome-terminal --window --title="HEARTBEAT: Logs" --geometry=80x24+0+0 -- bash -c "$CMD_LOGS" 
gnome-terminal --window --title="Filesystem" --geometry=80x24+800+0 -- bash -c "$CMD_FILES; exec bash"
gnome-terminal --window --title="DB: Input Files" --geometry=80x20+0+1550 -- bash -c "$CMD_DB_INPUT; exec bash"
gnome-terminal --window --title="DB: Segments" --geometry=80x20+800+1550 -- bash -c "$CMD_DB_SEGMENT; exec bash"
gnome-terminal --window --title="CHAOS: Manual Entry" --geometry=80x20+1600+1550 -- bash -c "$CMD_SHELL; exec bash"

echo "🚀 Command Center Launched. Happy hunting."