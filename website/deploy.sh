#!/bin/zsh
# EverKB 备案展示页部署脚本
# 用法: ./deploy.sh user@server_ip [目标目录]
# 示例: ./deploy.sh root@1.2.3.4 /var/www/everkb

set -e

# ===== 配置区（改成你自己的，或通过参数传入）=====
SERVER=${1:-"user@your_server_ip"}          # 服务器 SSH 地址
REMOTE_DIR=${2:-"/var/www/everkb"}          # nginx 静态文件根目录
# ================================================

LOCAL_FILE="$(cd "$(dirname "$0")" && pwd)/index.html"

if [ ! -f "$LOCAL_FILE" ]; then
  echo "错误: 找不到 $LOCAL_FILE"
  exit 1
fi

echo "部署 $LOCAL_FILE -> $SERVER:$REMOTE_DIR"

# 确保远程目录存在，然后上传（rsync 增量，秒传）
ssh "$SERVER" "mkdir -p $REMOTE_DIR"
rsync -avz --chmod=D755,F644 "$LOCAL_FILE" "$SERVER:$REMOTE_DIR/index.html"

echo ""
echo "完成。访问 http://你的域名/ 检查页面是否正常。"
