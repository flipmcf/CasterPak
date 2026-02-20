
Remember, this is a "publish to production" move.   Don't leave any debug stuff in, or 
after making sure the container passes all tests on your local dev enviornment

Build the container(s)

```
docker compose build nginx
docker compose build casterpak
```

(optionally) Refresh login tokens to docker hub
```
docker login
```

```
docker push flipmcf/casterpak-nginx:latest
```