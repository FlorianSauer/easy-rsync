# easy-rsync

Config-File based rsync script. 

Can be used to copy multiple folders to multiple hosts with one single command and one single configuration file.

With easy-rsync you do not need to craft multiple complicated rsync commands and put them into one bash-file.
You can now craft a single (less complicated) configuration file and start multiple rsync-subprocesses with easy-rsync.


### Usage

`python3 easy-rsync.py /path/to/config/file.conf <optional arguments passed to all rsync subprocesses>`


### Development Background

easy-rsync was developed as a hobby-project in my free time. If you have any issues or suggestions for improvement feel 
free to open an issue/pull request :)