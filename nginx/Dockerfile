FROM nginx:alpine

# Remove the generic config
RUN rm /etc/nginx/conf.d/default.conf

# Copy your specific config from the local conf.d folder
COPY conf.d/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80