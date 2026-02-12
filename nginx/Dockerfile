FROM nginx:alpine

#note that the context for this build is the root of the project, so we can copy from any subfolder.

# Remove the generic config
RUN rm /etc/nginx/conf.d/default.conf

# Copy your specific config from the local conf.d folder
COPY ./nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf

# Testing pages to verify HLS streaming
COPY ./tests/html/ /etc/nginx/html/testing/

EXPOSE 80