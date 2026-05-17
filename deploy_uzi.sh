#!/bin/bash
set -e

echo "=== 1. 安装 UZI-Skill ==="
cd /home/ubuntu
if [ -d UZI-Skill ]; then
  cd UZI-Skill && git pull
else
  git clone https://github.com/tryyrt1/UZI-Skill.git
fi
cd UZI-Skill && pip3 install -r requirements.txt -q

echo "=== 2. 创建 uzi 报告目录 ==="
mkdir -p /home/ubuntu/quant-stock/static/uzi
mkdir -p /home/ubuntu/UZI-Skill/skills/deep-analysis/scripts/reports

echo "=== 3. 更新 server.py ==="
sed -i 's|UZI_SKILL_DIR =.*|UZI_SKILL_DIR = "/home/ubuntu/UZI-Skill"|' /home/ubuntu/quant-stock/server.py
sed -i 's|UZI_PYTHON = .python.|UZI_PYTHON = "python3"|' /home/ubuntu/quant-stock/server.py
# 确保 import subprocess 存在
grep -q 'import subprocess' /home/ubuntu/quant-stock/server.py || sed -i '2s/$/, subprocess/' /home/ubuntu/quant-stock/server.py

echo "=== 4. 重启服务 ==="
sudo supervisorctl restart quant-stock

echo "=== 部署完成 ==="
