#!/bin/bash
# =============================================================================
# Secure Database Restore Script for NU AI Assistant
# =============================================================================
# Usage: ./restore_backup.sh <backup_file_path>
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
MONGO_CONTAINER_NAME="${MONGO_CONTAINER_NAME:-nu-ai-mongodb}"
MONGO_USER="${MONGO_ROOT_USER:-admin}"
MONGO_PASSWORD="${MONGO_ROOT_PASSWORD:-}"
MONGO_DATABASE="${MONGO_DATABASE:-nu_ai_db}"
MONGO_AUTH_DB="${MONGO_AUTH_DB:-admin}"
BACKUP_ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-}"
BACKUP_ENCRYPTION_ENABLED="${BACKUP_ENCRYPTION_ENABLED:-true}"
TEMP_RESTORE_DIR="${TEMP_RESTORE_DIR:-/tmp/mongodb_restore}"

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

validate_backup_file() {
    local backup_file="$1"
    
    if [[ ! -f "${backup_file}" ]]; then
        log_error "Backup file not found: ${backup_file}"
        exit 1
    fi
    
    # Check if file is encrypted
    if file "${backup_file}" | grep -q "openssl enc" || [[ "${backup_file}" == *.enc ]]; then
        if [[ -z "${BACKUP_ENCRYPTION_KEY}" ]]; then
            log_error "Encrypted backup requires BACKUP_ENCRYPTION_KEY"
            exit 1
        fi
        IS_ENCRYPTED=true
        log_info "Detected encrypted backup"
    else
        IS_ENCRYPTED=false
        log_info "Detected unencrypted backup"
    fi
}

decrypt_backup() {
    local encrypted_file="$1"
    local output_file="$2"
    
    log_info "Decrypting backup..."
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \
        -in "${encrypted_file}" \
        -out "${output_file}" \
        -pass "pass:${BACKUP_ENCRYPTION_KEY}" 2>/dev/null || {
        log_error "Decryption failed. Invalid key or corrupted file."
        exit 1
    }
    log_info "✓ Decryption successful"
}

verify_backup_integrity() {
    local backup_file="$1"
    
    log_info "Verifying backup integrity..."
    
    if tar -tzf "${backup_file}" &>/dev/null; then
        log_info "✓ Backup integrity verified"
        return 0
    else
        log_error "Backup integrity check FAILED"
        return 1
    fi
}

restore_backup() {
    local backup_file="$1"
    
    # Create temp directory
    mkdir -p "${TEMP_RESTORE_DIR}"
    
    # Extract backup
    log_info "Extracting backup..."
    tar -xzf "${backup_file}" -C "${TEMP_RESTORE_DIR}"
    
    # Find the backup directory
    local backup_dir=$(find "${TEMP_RESTORE_DIR}" -type d -name "${BACKUP_PREFIX:-nu_ai_backup}_*" | head -1)
    
    if [[ -z "${backup_dir}" ]]; then
        log_error "Could not find backup directory in archive"
        exit 1
    fi
    
    log_info "Backup directory: ${backup_dir}"
    
    # Copy backup to container
    log_info "Copying backup to container..."
    docker cp "${backup_dir}/." "${MONGO_CONTAINER_NAME}:/data/restore/"
    
    # Restore database
    log_info "Restoring database..."
    docker exec "${MONGO_CONTAINER_NAME}" mongorestore \
        --username "${MONGO_USER}" \
        --password "${MONGO_PASSWORD}" \
        --authenticationDatabase "${MONGO_AUTH_DB}" \
        --db "${MONGO_DATABASE}" \
        --drop \
        "/data/restore/${MONGO_DATABASE}" 2>/dev/null || {
        log_error "Restore failed"
        exit 1
    }
    
    # Clean up
    docker exec "${MONGO_CONTAINER_NAME}" rm -rf "/data/restore"
    rm -rf "${TEMP_RESTORE_DIR}"
    
    log_info "✓ Database restored successfully"
}

main() {
    local backup_file="${1:-}"
    
    if [[ -z "${backup_file}" ]]; then
        echo "Usage: $0 <backup_file_path>"
        echo ""
        echo "Examples:"
        echo "  $0 /backups/daily/nu_ai_backup_daily_20241201_120000.tar.gz"
        echo "  $0 /backups/daily/nu_ai_backup_daily_20241201_120000.tar.gz.enc"
        exit 1
    fi
    
    log_info "=========================================="
    log_info "Starting Database Restore"
    log_info "=========================================="
    
    validate_backup_file "${backup_file}"
    
    local decrypted_file="${TEMP_RESTORE_DIR}/restore_backup.tar.gz"
    
    if [[ "${IS_ENCRYPTED}" == true ]]; then
        decrypt_backup "${backup_file}" "${decrypted_file}"
        backup_file="${decrypted_file}"
    fi
    
    verify_backup_integrity "${backup_file}"
    
    # Confirmation for production
    echo -e "${YELLOW}"
    read -p "WARNING: This will OVERWRITE the current database. Continue? (yes/no): " confirmation
    echo -e "${NC}"
    
    if [[ "${confirmation}" != "yes" ]]; then
        log_info "Restore cancelled"
        exit 0
    fi
    
    restore_backup "${backup_file}"
    
    log_info "=========================================="
    log_info "Restore completed successfully"
    log_info "=========================================="
}

main "$@"