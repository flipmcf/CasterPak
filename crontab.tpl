#cleanup unused segment files every 5 minutes
*/5 * * * * %py-interpreter% -m cleanup.cleaner >> /var/log/casterpak.log
