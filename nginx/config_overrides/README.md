# Nginx Configuration Overrides

This directory contains optional configuration templates for the CasterPak Nginx container. 

By default, the production Nginx image is built with strict, performance-optimized timeouts. However, when debugging long-running transcodes (like the initial FFmpeg multi-output generation), those strict timeouts will kill the connection prematurely.

## The "Inactive Config" Pattern
To avoid accidentally shipping debug settings to production, we use the inactive config pattern:
* Files ending in `.inactive` are tracked by Git and ignored by Nginx.
* Files ending in `.conf` are ignored by Git but loaded by Nginx at runtime.

The main `nginx.conf` contains the following directive:
`include /etc/nginx/config_overrides/*.conf;`

## How to Enable Dev Mode (Timeouts)
To activate the extended timeouts (e.g., 600s), you just need to rename the template and reload Nginx inside the running container. 

You do not need to rebuild the image. Just run this from your host machine:

```bash
docker exec casterpak_nginx bash -c "cp /etc/nginx/config_overrides/timeouts.conf.inactive /etc/nginx/config_overrides/timeouts.conf && nginx -s reload"


