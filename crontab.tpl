#cleanup unused segment files every 5 minutes
*/5 * * * * %py-interpreter% %install%/cleanup.py >> /var/log/casterpak.log
