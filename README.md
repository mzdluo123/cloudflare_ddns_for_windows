# cloudflare_ddns_for_windows
自用的cloudflare ddns脚本，支持Windows

在[cloudflare-ddns-client](https://github.com/LINKIWI/cloudflare-ddns-client)的基础上根据个人情况进行了一定的修改

打包exe方法

`pyinstaller -p .\venv\Lib\site-packages -F main.py`