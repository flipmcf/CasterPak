#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
#cleanup unused segment files every 5 minutes
*/5 * * * * %py-interpreter% -m cleanup.cleaner >> /var/log/casterpak.log
