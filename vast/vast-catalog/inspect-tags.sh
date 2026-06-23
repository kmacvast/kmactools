export AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY" \
export AWS_SECRET_ACCESS_KEY="YOUR_SECRET_ACCESS_KEY" \

echo "Lising the tags over S3:"

aws s3api get-object-tagging \
  --endpoint-url http://172.200.202.3 \
  --bucket kmacs-vast-catalog-test-bucket \
  --key linux-2.6.11/Documentation/fujitsu/frv/session_162.tmp \
  --no-verify-ssl

echo "Lising the file over NFS:"

ls -l /mnt/kmacs-root/vast-catalog/linux-2.6.11/Documentation/fujitsu/frv/session_162.tmp


