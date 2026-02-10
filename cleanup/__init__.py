# cleanup/__init__.py
import threading
import time
from cleanup import cleaner
import random

def start_maintenance_loop(interval=300, server=None):
    """
    Launched by Gunicorn Master. 
    Runs the cleanup.run() logic every 'interval' seconds.
    """

    def loop():
        if server:
            server.log.info(f"Cleanup: Background thread initiated - cleanup will run every {interval} seconds.")

        while True:
            try:
                # Execute the actual file/DB cleanup logic
                server.log.debug("Cleanup: Starting cleanup pass.")
                cleaner.run_cleanup()

                #avoid potential 'sync ups' with other processes by adding a random jitter to the sleep interval
                jitter = random.uniform(0, 5)
                time.sleep(interval + jitter)

            except Exception as e:
                if server:
                    server.log.error(f"Cleanup: Loop encountered an error: {e}")
                else:
                    print(f"Cleanup: Error: {e}")
                time.sleep(30) # wait before retrying
                        

    # daemon=True ensures the thread dies when the main process exits
    t = threading.Thread(target=loop, daemon=True)
    t.start()