#!/bin/bash
# scripts/cleanup.sh
# Cleanup script to remove all resources

set -e

echo "=== RAG Application Cleanup ==="
echo "WARNING: This will delete all resources!"
read -p "Are you sure? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Cleanup cancelled"
    exit 0
fi

# Delete Kubernetes resources
echo "Deleting Kubernetes resources..."
kubectl delete namespace rag-application --ignore-not-found=true

# Destroy Terraform infrastructure
echo "Destroying Azure infrastructure..."
cd terraform
terraform destroy -auto-approve

echo "=== Cleanup Complete ==="
