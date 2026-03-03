#!/bin/bash
# Database Backup Script
# Backs up elderly_monitoring.db with timestamp

cd "/home/yztan120/Application Server"

DB_FILE="elderly_monitoring.db"
BACKUP_DIR="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/elderly_monitoring_${TIMESTAMP}.db"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Check if database exists
if [ ! -f "$DB_FILE" ]; then
    echo "✗ Database not found: $DB_FILE"
    exit 1
fi

# Get database size
DB_SIZE=$(du -h "$DB_FILE" | cut -f1)

echo "📁 Backing up database..."
echo "   Source: $DB_FILE ($DB_SIZE)"
echo "   Target: $BACKUP_FILE"

# Create backup using SQLite backup command
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"

if [ $? -eq 0 ]; then
    echo "✓ Backup successful!"
    
    # Show backup info
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "   Backup size: $BACKUP_SIZE"
    
    # List recent backups
    echo ""
    echo "Recent backups:"
    ls -lth "$BACKUP_DIR" | head -6
    
    # Delete backups older than 7 days
    echo ""
    echo "Cleaning old backups (>7 days)..."
    find "$BACKUP_DIR" -name "elderly_monitoring_*.db" -mtime +7 -delete
    
    REMAINING=$(ls -1 "$BACKUP_DIR" | wc -l)
    echo "✓ Backup complete. $REMAINING backup(s) retained."
else
    echo "✗ Backup failed!"
    exit 1
fi
