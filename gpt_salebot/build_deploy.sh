#!/bin/bash
set -e

ECR_REPO_NAME="gpt-salebot"

AWS_REGION="eu-central-1"
AWS_ACCOUNT_ID="982081093733"
IMAGE_TAG="latest"
LAMBDA_FUNCTION_NAME="gpt-salebot"
echo 1
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
echo 2
docker build -t $ECR_REPO_NAME .

docker tag $ECR_REPO_NAME:$IMAGE_TAG $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG

docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG

aws lambda update-function-code \
  --region $AWS_REGION \
  --function-name $LAMBDA_FUNCTION_NAME \
  --image-uri $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG

echo "Lambda function $LAMBDA_FUNCTION_NAME updated to use image $ECR_REPO_NAME:$IMAGE_TAG"