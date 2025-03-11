# PyMonitor Database Migration Guide

If you're experiencing database errors like the following:

```
(sqlite3.OperationalError) table function_calls has no column named return_object_id
```

This means your database schema is out of date and needs to be migrated to the latest version.

## Automatic Migration

PyMonitor now includes automatic database migration capabilities. When you initialize monitoring, it will attempt to detect and fix schema issues automatically.

However, if you're still experiencing issues, you can use the provided migration utility.

## Using the Migration Utility

### Option 1: From Python

```python
from monitoringpy import migrate_database, check_database_schema

# Check if migration is needed
if not check_database_schema("path/to/your/monitoring.db"):
    # Perform migration
    migrate_database("path/to/your/monitoring.db")
```

### Option 2: Command Line

You can run the migration utility directly from the command line:

```bash
python -m monitoringpy.migrate_db path/to/your/monitoring.db
```

Additional options:
- `--check-only`: Only check the schema without performing migration
- `--force`: Force migration even if the schema appears up to date

## Manual Migration

If the automatic migration doesn't work, you can manually fix the database:

1. Create a backup of your database file
2. Open the database with SQLite:
   ```bash
   sqlite3 path/to/your/monitoring.db
   ```
3. Add the missing column:
   ```sql
   ALTER TABLE function_calls ADD COLUMN return_object_id VARCHAR REFERENCES objects(id);
   ```
4. Exit SQLite:
   ```
   .exit
   ```

## Starting Fresh

If you're still experiencing issues, you can start with a fresh database:

1. Rename or delete your existing database file
2. PyMonitor will create a new database with the correct schema on next run

## Troubleshooting

If you continue to experience issues:

1. Check the logs for specific error messages
2. Ensure you have write permissions to the database file and its directory
3. Try using an in-memory database for testing:
   ```python
   monitor = init_monitoring(db_path=":memory:")
   ```

For further assistance, please open an issue on the GitHub repository. 