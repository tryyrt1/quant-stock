@echo off
echo Deploying quant-stock-pro to cloud server...
scp C:/Users/Administrator/Desktop/python\ test/quant-stock-pro/server.py root@YOUR_SERVER_IP:/root/quant-stock-pro/server.py
scp C:/Users/Administrator/Desktop/python\ test/quant-stock-pro/static/index.html root@YOUR_SERVER_IP:/root/quant-stock-pro/static/index.html
ssh root@YOUR_SERVER_IP "sudo systemctl restart quant-stock"
echo Done!
pause
