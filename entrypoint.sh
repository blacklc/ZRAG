#!/bin/sh
set -e

echo "=== 应用配置迁移 ==="
python3 manage.py migrate --no-input

echo "=== 收集静态文件 ==="
python3 manage.py collectstatic --no-input

echo "=== 启动服务 ==="
exec "$@"
