@echo off
echo Deploying quant-stock-pro to cloud server...
scp C:/Users/Administrator/Desktop/python\ test/quant-stock-pro/server.py root@159.75.103.100:/root/quant-stock-pro/server.py
scp C:/Users/Administrator/Desktop/python\ test/quant-stock-pro/static/index.html root@159.75.103.100:/root/quant-stock-pro/static/index.html
ssh root@159.75.103.100 "sudo systemctl restart quant-stock"
echo Done!
pause
